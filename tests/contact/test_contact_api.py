#!/usr/bin/env python3
"""Tests for ops/sost-contact-api.py — real HTTP server + local fake SMTP sink.

Run:  python3 tests/contact/test_contact_api.py -v
No network access, no real mailbox: SMTP goes to tests/contact/fake_smtp.py on 127.0.0.1.
The recipient used here is a placeholder test address, never the production inbox.
"""
import email
import email.policy
import http.client
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fake_smtp import FakeSMTP  # noqa: E402

spec = importlib.util.spec_from_file_location('contact_api', os.path.join(ROOT, 'ops', 'sost-contact-api.py'))
capi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capi)

TEST_TO = 'inbox-under-test@example.org'
TEST_FROM = 'mailbox-under-test@example.org'
ORIGIN = 'https://sostcore.com'


def write_config(smtp_port, **over):
    vals = dict(listen_host='127.0.0.1', listen_port=0, mail_to=TEST_TO, mail_from=TEST_FROM,
                smtp_host='127.0.0.1', smtp_port=smtp_port, smtp_security='none',
                smtp_user='u', smtp_password='p', smtp_timeout=5,
                allowed_origins='https://sostcore.com,https://www.sostcore.com',
                ip_sends_per_10min=3, ip_sends_per_day=20, ip_requests_per_10min=30,
                global_sends_per_hour=30, global_sends_per_day=200)
    vals.update(over)
    fd, path = tempfile.mkstemp(suffix='.conf')
    with os.fdopen(fd, 'w') as fh:
        fh.write('[contact]\n' + ''.join('%s = %s\n' % kv for kv in vals.items()))
    return path


class Base(unittest.TestCase):
    cfg_over = {}

    def setUp(self):
        self.smtp = FakeSMTP()
        self.cfg_path = write_config(self.smtp.port, **self.cfg_over)
        self.cfg = capi.Config(self.cfg_path)
        self.logs = []
        self.svc = capi.ContactService(self.cfg, log=self.logs.append)
        self.httpd = capi.ThreadingHTTPServer(('127.0.0.1', 0), capi.make_handler(self.svc))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.ip_counter = 0

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.smtp.close()
        os.unlink(self.cfg_path)

    def req(self, method='POST', body=None, headers=None, path='/api/contact', ip='203.0.113.7', raw=None):
        h = {'Origin': ORIGIN, 'Content-Type': 'application/json', 'X-Real-IP': ip}
        h.update(headers or {})
        h = {k: v for k, v in h.items() if v is not None}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b'')
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        c.request(method, path, body=data if method not in ('GET', 'HEAD') or data else None, headers=h)
        r = c.getresponse()
        text = r.read().decode()
        c.close()
        try:
            obj = json.loads(text) if text else {}
        except ValueError:
            obj = {'_raw': text}
        return r.status, obj, text, dict(r.getheaders())

    def form(self, **kw):
        d = {'name': 'Ana', 'email': 'ana@example.com', 'subject': 'Listing question',
             'message': 'Hello SOST team,\nquestion about listing.', 'website': '',
             'idempotency_key': uuid.uuid4().hex}
        d.update(kw)
        return d

    def assertNoSecrets(self, text, headers=None):
        blob = text + json.dumps(headers or {})
        for s in (TEST_TO, TEST_FROM, '127.0.0.1', 'smtp', 'Traceback', '/etc/', 'password'):
            self.assertNotIn(s.lower(), blob.lower(), 'response leaks %r' % s)


class TestHappyPath(Base):
    def test_valid_submit_sends_one_plain_text_mail(self):
        st, obj, text, hdr = self.req(body=self.form())
        self.assertEqual(st, 200)
        self.assertEqual(obj, {'ok': True, 'message': 'Your message has been sent.'})
        self.assertNoSecrets(text, hdr)
        self.assertEqual(len(self.smtp.messages), 1)
        m = self.smtp.messages[0]
        self.assertEqual(m['mail_from'], TEST_FROM)
        self.assertEqual(m['rcpt_to'], [TEST_TO])
        msg = email.message_from_bytes(m['data'], policy=email.policy.default)
        self.assertEqual(msg['To'], TEST_TO)
        self.assertIn(TEST_FROM, msg['From'])
        self.assertEqual(msg['Reply-To'], 'ana@example.com')
        self.assertIsNone(msg['Cc']); self.assertIsNone(msg['Bcc'])
        self.assertEqual(msg['Subject'], '[sostcore.com contact] Listing question')
        self.assertEqual(msg.get_content_type(), 'text/plain')
        self.assertFalse(msg.is_multipart())
        body = msg.get_content()
        self.assertTrue(body.startswith('From website contact form'), body[:40])
        for s in ('From website contact form', 'Name: Ana', 'Visitor email: ana@example.com',
                  'Subject: Listing question', 'question about listing.'):
            self.assertIn(s, body)

    def test_form_urlencoded_and_optional_name(self):
        from urllib.parse import urlencode
        raw = urlencode({'email': 'b@example.net', 'subject': 'Hi', 'message': 'Body'}).encode()
        st, obj, _, _ = self.req(raw=raw, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual((st, obj['ok']), (200, True))
        self.assertIn('Name: (not given)', email.message_from_bytes(
            self.smtp.messages[0]['data'], policy=email.policy.default).get_content())

    def test_logs_hold_no_content(self):
        self.req(body=self.form(name='SecretName', email='visitor@example.com',
                                subject='TopSecretSubject', message='VeryPrivateBody'))
        joined = '\n'.join(self.logs)
        for s in ('SecretName', 'visitor@example.com', 'TopSecretSubject', 'VeryPrivateBody',
                  '203.0.113.7', TEST_TO):
            self.assertNotIn(s, joined)
        self.assertIn('contact sent', joined)

    def test_client_cannot_choose_recipient(self):
        st, obj, _, _ = self.req(body=self.form(to='attacker@evil.example', cc='x@evil.example',
                                                bcc='y@evil.example', **{'from': 'z@evil.example'}))
        self.assertEqual(st, 200)
        m = self.smtp.messages[0]
        self.assertEqual(m['rcpt_to'], [TEST_TO])
        self.assertNotIn(b'evil.example', m['data'])


class TestRejections(Base):
    def assertRejected(self, st, obj, text, hdr, status=400):
        self.assertEqual(st, status)
        self.assertFalse(obj.get('ok'))
        self.assertNoSecrets(text, hdr)
        self.assertEqual(self.smtp.messages, [])

    def test_empty_form(self):
        self.assertRejected(*self.req(body={}))
        self.assertRejected(*self.req(body=self.form(email='', subject='', message='')))
        self.assertRejected(*self.req(raw=b''), status=400)

    def test_missing_required_fields(self):
        for k in ('email', 'subject', 'message'):
            st, obj, text, hdr = self.req(body=self.form(**{k: '   '}))
            self.assertRejected(st, obj, text, hdr)
            self.assertEqual(obj['field'], k)

    def test_invalid_email(self):
        for bad in ('plain', 'a@b', 'a@@b.com', 'a b@c.com', '@x.com', 'a@x.c', 'a@-x.com',
                    'a..b@x.com', '.a@x.com', 'ü@x.com', 'a@x.com>', '<a@x.com>', 'a@x.com,b@y.com',
                    'x' * 65 + '@x.com', 'a@' + 'b' * 250 + '.com', 123):
            st, obj, text, hdr = self.req(body=self.form(email=bad))
            self.assertRejected(st, obj, text, hdr)

    def test_oversized(self):
        self.assertRejected(*self.req(body=self.form(message='x' * 5001)))
        self.assertRejected(*self.req(body=self.form(subject='s' * 201)))
        self.assertRejected(*self.req(body=self.form(name='n' * 101)))
        st, obj, text, hdr = self.req(raw=b'{"a":"' + b'x' * (17 * 1024) + b'"}')
        self.assertRejected(st, obj, text, hdr, status=413)
        # exactly at the limits is fine
        st, obj, _, _ = self.req(body=self.form(message='m' * 5000, subject='s' * 200, name='n' * 100))
        self.assertEqual(st, 200)

    def test_header_injection(self):
        payloads = ['x\r\nBcc: victim@evil.example', 'x\nBcc: victim@evil.example', 'x\rTo: v@evil.example',
                    'x Bcc: v@evil.example', 'x\x00y', 'x%0d%0aBcc:v@evil.example']
        for p in payloads:
            for field in ('name', 'subject'):
                st, obj, text, hdr = self.req(body=self.form(**{field: p}))
                if '%0d' in p:   # literal, harmless text (not decoded): accepted but stays one line
                    continue
                self.assertRejected(st, obj, text, hdr)
                self.assertEqual(obj['field'], field)
            st, obj, text, hdr = self.req(body=self.form(email='a@example.com' + p[1:] if p[0] == 'x' else p))
            if '%0d' not in p:
                self.assertRejected(st, obj, text, hdr)
        for m in self.smtp.messages:
            self.assertEqual(m['rcpt_to'], [TEST_TO])
            msg = email.message_from_bytes(m['data'], policy=email.policy.default)
            self.assertIsNone(msg['Bcc'])

    def test_method_not_post(self):
        for meth in ('GET', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'):
            st, obj, text, hdr = self.req(method=meth)
            self.assertEqual(st, 405, meth)
            self.assertEqual(hdr.get('Allow'), 'POST')
            self.assertNoSecrets(text, hdr)
        self.assertEqual(self.smtp.messages, [])

    def test_wrong_origin(self):
        for h in ({'Origin': 'https://evil.example'}, {'Origin': 'http://sostcore.com'},
                  {'Origin': 'https://sostcore.com.evil.example'}, {'Origin': 'null'},
                  {'Origin': None, 'Referer': 'https://evil.example/sostcore.com'},
                  {'Origin': None, 'Referer': None}):
            st, obj, text, hdr = self.req(body=self.form(), headers=h)
            self.assertRejected(st, obj, text, hdr, status=403)
        st, obj, _, _ = self.req(body=self.form(), headers={'Origin': None, 'Referer': 'https://www.sostcore.com/index.html'})
        self.assertEqual(st, 200)

    def test_bad_content_type_and_json(self):
        self.assertRejected(*self.req(raw=b'email=a', headers={'Content-Type': 'text/plain'}), status=415)
        self.assertRejected(*self.req(raw=b'{not json'))
        self.assertRejected(*self.req(raw=b'[1,2]'))
        self.assertRejected(*self.req(raw=b'\xff\xfe'))
        self.assertRejected(*self.req(body=self.form(message=['a'])))

    def test_unknown_path(self):
        st, obj, text, hdr = self.req(path='/api/other', body=self.form())
        self.assertRejected(st, obj, text, hdr, status=404)


class TestHoneypotRateDup(Base):
    def test_honeypot_fake_success_no_send(self):
        st, obj, text, hdr = self.req(body=self.form(website='http://spam.example'))
        self.assertEqual((st, obj), (200, {'ok': True, 'message': 'Your message has been sent.'}))
        self.assertEqual(self.smtp.messages, [])
        self.assertIn('contact honeypot', '\n'.join(self.logs))

    def test_rate_limit_per_ip(self):
        for i in range(3):
            st, obj, _, _ = self.req(body=self.form(subject='s%d' % i))
            self.assertEqual(st, 200)
        st, obj, text, hdr = self.req(body=self.form(subject='s4'))
        self.assertEqual(st, 429)
        self.assertEqual(obj['message'], 'Too many messages. Please try again later.')
        self.assertNoSecrets(text, hdr)
        self.assertEqual(len(self.smtp.messages), 3)
        # a different client IP is not affected
        st, _, _, _ = self.req(body=self.form(subject='other'), ip='198.51.100.9')
        self.assertEqual(st, 200)

    def test_rate_limit_window_expires(self):
        now = [1000000.0]
        self.svc.clock = lambda: now[0]
        for i in range(3):
            self.assertEqual(self.req(body=self.form(subject='a%d' % i))[0], 200)
        self.assertEqual(self.req(body=self.form(subject='a3'))[0], 429)
        now[0] += 601
        self.assertEqual(self.req(body=self.form(subject='a4'))[0], 200)

    def test_daily_limit_per_ip(self):
        now = [2000000.0]
        self.svc.clock = lambda: now[0]
        sent = 0
        for i in range(40):
            st = self.req(body=self.form(subject='d%d' % i))[0]
            sent += st == 200
            now[0] += 700   # stay clear of the 10-minute window
        self.assertEqual(sent, 20)

    def test_requests_flood_limited_even_if_invalid(self):
        codes = [self.req(body={})[0] for _ in range(31)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(codes.count(400), 30)

    def test_double_submit_same_key(self):
        f = self.form()
        a = self.req(body=f)
        b = self.req(body=f)
        self.assertEqual((a[0], b[0]), (200, 200))
        self.assertTrue(b[1]['ok'])
        self.assertEqual(len(self.smtp.messages), 1)

    def test_double_submit_new_key_same_content(self):
        self.req(body=self.form())
        self.req(body=self.form())   # new idempotency key, identical content
        self.assertEqual(len(self.smtp.messages), 1)

    def test_concurrent_double_submit(self):
        f = self.form()
        results = []
        ts = [threading.Thread(target=lambda: results.append(self.req(body=f)[0])) for _ in range(5)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(self.smtp.messages), 1)
        self.assertIn(200, results)

    def test_smtp_failure_is_generic_and_retryable(self):
        self.smtp.fail = True
        f = self.form()
        st, obj, text, hdr = self.req(body=f)
        self.assertEqual(st, 502)
        self.assertEqual(obj['message'], 'Unable to send the message. Please try again later.')
        self.assertNoSecrets(text, hdr)
        self.assertNotIn('554', text)
        self.smtp.fail = False
        st, obj, _, _ = self.req(body=f)   # same key: not marked done, so the retry sends
        self.assertEqual(st, 200)
        self.assertEqual(len(self.smtp.messages), 1)

    def test_smtp_unreachable_is_generic(self):
        self.svc.cfg.smtp_port = 1   # nothing listens there
        st, obj, text, hdr = self.req(body=self.form())
        self.assertEqual(st, 502)
        self.assertNoSecrets(text, hdr)
        self.assertIn('kind=', '\n'.join(self.logs))


class TestGlobalCap(Base):
    cfg_over = {'global_sends_per_hour': 4}

    def test_global_cap(self):
        codes = [self.req(body=self.form(subject='g%d' % i), ip='192.0.2.%d' % i)[0] for i in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 429, 429])
        self.assertEqual(len(self.smtp.messages), 4)


class TestConfig(unittest.TestCase):
    def test_bad_config_rejected(self):
        for over in ({'mail_to': ''}, {'mail_to': 'a@b'}, {'mail_from': 'x'}, {'smtp_security': 'tls13'},
                     {'smtp_host': ''}):
            p = write_config(25, **over)
            try:
                with self.assertRaises(ValueError):
                    capi.Config(p)
            finally:
                os.unlink(p)

    def test_check_config_prints_no_secrets(self):
        import io, contextlib
        p = write_config(25, smtp_password='S3cretPass')
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = capi.main(['--config', p, '--check-config'])
        finally:
            os.unlink(p)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for s in ('S3cretPass', TEST_TO, TEST_FROM):
            self.assertNotIn(s, out)

    def test_template_has_placeholders_only(self):
        with open(os.path.join(ROOT, 'deploy', 'contact', 'contact-api.conf.example')) as fh:
            t = fh.read()
        cp = __import__('configparser').ConfigParser(interpolation=None)
        cp.read_string(t)
        for k in ('mail_to', 'mail_from', 'smtp_user', 'smtp_password'):
            self.assertRegex(cp['contact'][k], r'^<[A-Z_]+>$')


if __name__ == '__main__':
    unittest.main()
