#!/usr/bin/env python3
"""SOST website contact endpoint (POST /api/contact) — see deploy/contact/README.md.

The website contact form posts here; this service relays ONE plain-text email per accepted
submission to a FIXED inbox that exists only in the server config file. The inbox address,
the sender mailbox and the SMTP credentials are never sent to the browser, never logged and
never present in this file or in any public file.

Design (stdlib only, no third-party packages):
  * POST only; JSON or application/x-www-form-urlencoded body; body <= 16 KB.
  * Fields: name (optional, <= 100), email (required, strict syntax, <= 254),
    subject (required, <= 200), message (required, <= 5000), website (honeypot),
    idempotency_key (client-generated, optional). Unknown fields are ignored; the client
    can never choose To / Cc / Bcc / From — those come from the config only.
  * CR / LF / other control characters in name, email or subject are rejected
    (mail-header injection); the email is built with email.message.EmailMessage and
    sent as text/plain, no attachments.
  * Honeypot filled -> fake success, nothing sent.
  * Origin (or, if absent, Referer) must be one of the configured site origins.
  * Rate limits: per client IP (sends per 10 min and per day, plus all requests per
    10 min) and a global send cap per hour and per day. In memory, single process.
  * Duplicate protection: the same idempotency key, or the same (ip, email, subject,
    message) within 10 minutes, returns the original success without a second email.
  * Responses are fixed JSON strings: they never echo the recipient, SMTP host, paths
    or exception text. Logs hold only metadata (result code, field lengths, a salted
    per-process hash of the IP) — never the message, the visitor's email or the name.

Config: INI file, section [contact]. Path from --config, else $CREDENTIALS_DIRECTORY/
contact.conf (systemd LoadCredential=), else /etc/sost/contact-api.conf. Template:
deploy/contact/contact-api.conf.example. Listens on 127.0.0.1:18330 by default; nginx
`location = /api/contact` proxies to it and sets X-Real-IP.
"""
import argparse
import configparser
import email.policy
import hashlib
import json
import os
import re
import secrets
import smtplib
import ssl
import sys
import threading
import time
from collections import deque
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 16 * 1024
MAX_NAME = 100
MAX_EMAIL = 254
MAX_SUBJECT = 200
MAX_MESSAGE = 5000
MAX_KEY = 100

MSG_OK = 'Your message has been sent.'
MSG_FAIL = 'Unable to send the message. Please try again later.'
MSG_INVALID = 'Please check the form fields and try again.'
MSG_RATE = 'Too many messages. Please try again later.'

# Strict, ASCII-only address syntax: dot-atom local part, hostname labels, alpha TLD.
_LOCAL = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
EMAIL_RE = re.compile(r'\A(' + _LOCAL + r')@((?:' + _LABEL + r'\.)+[A-Za-z]{2,63})\Z')
# Control characters (C0, DEL, C1) plus Unicode line/paragraph separators.
CTRL_RE = re.compile('[\x00-\x1f\x7f-\x9f\u2028\u2029]')
# Message body: keep TAB and LF (CRLF/CR normalised to LF first), reject the rest.
BODY_CTRL_RE = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f]')
KEY_RE = re.compile(r'\A[A-Za-z0-9_-]{8,%d}\Z' % MAX_KEY)


def valid_email(addr):
    if not isinstance(addr, str) or not addr or len(addr) > MAX_EMAIL:
        return False
    m = EMAIL_RE.match(addr)
    if not m:
        return False
    return len(m.group(1)) <= 64 and len(m.group(2)) <= 253


class Config:
    def __init__(self, path):
        cp = configparser.ConfigParser(interpolation=None)
        with open(path, 'r', encoding='utf-8') as fh:
            cp.read_file(fh)
        c = cp['contact']
        self.listen_host = c.get('listen_host', '127.0.0.1')
        self.listen_port = c.getint('listen_port', 18330)
        self.mail_to = c.get('mail_to', '').strip()
        self.mail_from = c.get('mail_from', '').strip()
        self.mail_from_name = c.get('mail_from_name', 'SOST website contact form').strip()
        self.subject_prefix = c.get('subject_prefix', '[sostcore.com contact]').strip()
        self.smtp_host = c.get('smtp_host', '').strip()
        self.smtp_port = c.getint('smtp_port', 465)
        self.smtp_security = c.get('smtp_security', 'ssl').strip().lower()  # ssl | starttls | none
        self.smtp_user = c.get('smtp_user', '').strip()
        self.smtp_password = c.get('smtp_password', '')
        self.smtp_timeout = c.getfloat('smtp_timeout', 15.0)
        self.allowed_origins = {o.strip().rstrip('/').lower()
                                for o in c.get('allowed_origins', 'https://sostcore.com,https://www.sostcore.com').split(',')
                                if o.strip()}
        self.trust_x_real_ip = c.getboolean('trust_x_real_ip', True)
        self.ip_per_10min = c.getint('ip_sends_per_10min', 3)
        self.ip_per_day = c.getint('ip_sends_per_day', 20)
        self.ip_requests_per_10min = c.getint('ip_requests_per_10min', 30)
        self.global_per_hour = c.getint('global_sends_per_hour', 30)
        self.global_per_day = c.getint('global_sends_per_day', 200)
        self.dup_window = c.getint('duplicate_window_seconds', 600)
        if self.smtp_security not in ('ssl', 'starttls', 'none'):
            raise ValueError('smtp_security must be ssl, starttls or none')
        for k in ('mail_to', 'mail_from'):
            if not valid_email(getattr(self, k)):
                raise ValueError('config %s is missing or invalid' % k)
        if not self.smtp_host:
            raise ValueError('config smtp_host is missing')
        if CTRL_RE.search(self.mail_from_name + self.subject_prefix):
            raise ValueError('config mail_from_name/subject_prefix contain control characters')


def default_config_path():
    cred = os.environ.get('CREDENTIALS_DIRECTORY')
    if cred and os.path.exists(os.path.join(cred, 'contact.conf')):
        return os.path.join(cred, 'contact.conf')
    return '/etc/sost/contact-api.conf'


class Limiter:
    """Sliding-window counters, in memory. Bounded: idle keys are pruned."""

    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}  # key -> deque[timestamp]

    def _prune(self, dq, now, horizon):
        while dq and dq[0] <= now - horizon:
            dq.popleft()

    def count(self, key, window, now):
        with self.lock:
            dq = self.events.get(key)
            if not dq:
                return 0
            return sum(1 for t in dq if t > now - window)

    def add(self, key, now, horizon=86400):
        with self.lock:
            dq = self.events.setdefault(key, deque())
            self._prune(dq, now, horizon)
            dq.append(now)
            if len(self.events) > 50000:  # hard bound on memory
                for k in [k for k, v in self.events.items() if not v or v[-1] <= now - horizon]:
                    del self.events[k]


class ContactService:
    def __init__(self, cfg, sender=None, clock=time.time, log=None):
        self.cfg = cfg
        self.clock = clock
        self.sender = sender or self._smtp_send
        self.limiter = Limiter()
        self.lock = threading.Lock()
        self.done_keys = {}        # idempotency key -> time of success
        self.recent_hashes = {}    # content hash -> time of success
        self.inflight = set()
        self.salt = secrets.token_bytes(16)
        self._log = log or (lambda line: print(line, file=sys.stderr, flush=True))

    # ---- logging: metadata only -------------------------------------------------
    def log(self, ip, code, **kw):
        iph = hashlib.sha256(self.salt + ip.encode()).hexdigest()[:12]
        extra = ' '.join('%s=%s' % (k, v) for k, v in sorted(kw.items()))
        self._log('contact %s ip=%s %s' % (code, iph, extra))

    # ---- request checks -----------------------------------------------------------
    def origin_ok(self, headers):
        origin = (headers.get('Origin') or '').strip().rstrip('/').lower()
        if origin:
            return origin in self.cfg.allowed_origins
        ref = (headers.get('Referer') or '').strip()
        if not ref:
            return False
        p = urlsplit(ref)
        return ('%s://%s' % (p.scheme, p.netloc)).lower() in self.cfg.allowed_origins

    @staticmethod
    def parse_body(ctype, raw):
        ctype = (ctype or '').split(';')[0].strip().lower()
        text = raw.decode('utf-8')  # UnicodeDecodeError -> invalid
        if ctype == 'application/json':
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError('not an object')
            return data
        if ctype == 'application/x-www-form-urlencoded':
            q = parse_qs(text, keep_blank_values=True, max_num_fields=20)
            return {k: v[0] for k, v in q.items()}
        raise TypeError('unsupported content type')

    @staticmethod
    def validate(data):
        def field(k):
            v = data.get(k, '')
            if v is None:
                v = ''
            if not isinstance(v, str):
                raise ValueError(k)
            return v
        name = field('name').strip()
        email = field('email').strip()
        subject = field('subject').strip()
        message = field('message').replace('\r\n', '\n').replace('\r', '\n').strip()
        # Header fields: any CR/LF/control char is an injection attempt -> reject.
        for k, v in (('name', field('name')), ('email', field('email')), ('subject', field('subject'))):
            if CTRL_RE.search(v):
                return None, k
        if len(name) > MAX_NAME:
            return None, 'name'
        if not valid_email(email):
            return None, 'email'
        if not subject or len(subject) > MAX_SUBJECT:
            return None, 'subject'
        if not message or len(message) > MAX_MESSAGE or BODY_CTRL_RE.search(message):
            return None, 'message'
        return {'name': name, 'email': email, 'subject': subject, 'message': message}, None

    # ---- email ----------------------------------------------------------------------
    def build_email(self, f):
        cfg = self.cfg
        m = EmailMessage()
        m['From'] = formataddr((cfg.mail_from_name, cfg.mail_from))
        m['To'] = cfg.mail_to
        m['Reply-To'] = f['email']
        m['Subject'] = ('%s %s' % (cfg.subject_prefix, f['subject'])).strip()
        m['Date'] = formatdate(localtime=False)
        m['Message-ID'] = make_msgid(domain=cfg.mail_from.split('@', 1)[1])
        m['Auto-Submitted'] = 'auto-generated'
        m.set_content(
            'From website contact form (sostcore.com)\n'
            '\n'
            'Name: %s\n'
            'Visitor email: %s\n'
            'Subject: %s\n'
            '\n'
            'Message:\n'
            '%s\n' % (f['name'] or '(not given)', f['email'], f['subject'], f['message']),
            subtype='plain', charset='utf-8')
        return m

    def _smtp_send(self, msg):
        cfg = self.cfg
        if cfg.smtp_security == 'ssl':
            s = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout,
                                 context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout)
        try:
            if cfg.smtp_security == 'starttls':
                s.starttls(context=ssl.create_default_context())
            if cfg.smtp_user:
                s.login(cfg.smtp_user, cfg.smtp_password)
            # Envelope is fixed from config; the visitor's address is only a Reply-To header.
            # Serialised with policy.SMTP: CRLF line ends and no ">From" mangling of the body.
            s.sendmail(cfg.mail_from, [cfg.mail_to], msg.as_bytes(policy=email.policy.SMTP))
        finally:
            try:
                s.quit()
            except Exception:
                pass

    # ---- main entry -----------------------------------------------------------------
    def handle(self, ip, headers, raw):
        """Returns (http_status, response_dict). Never raises."""
        now = self.clock()
        cfg = self.cfg
        lim = self.limiter
        if not self.origin_ok(headers):
            self.log(ip, 'reject_origin')
            return 403, {'ok': False, 'error': 'forbidden', 'message': MSG_FAIL}
        if lim.count(('req', ip), 600, now) >= cfg.ip_requests_per_10min:
            self.log(ip, 'rate_requests')
            return 429, {'ok': False, 'error': 'rate_limited', 'message': MSG_RATE}
        lim.add(('req', ip), now)
        try:
            data = self.parse_body(headers.get('Content-Type'), raw)
        except TypeError:
            self.log(ip, 'reject_ctype')
            return 415, {'ok': False, 'error': 'unsupported_media_type', 'message': MSG_FAIL}
        except (ValueError, UnicodeDecodeError):
            self.log(ip, 'reject_body')
            return 400, {'ok': False, 'error': 'invalid', 'message': MSG_INVALID}
        hp = data.get('website', '')
        if hp not in ('', None):
            # Bot: look successful, send nothing.
            self.log(ip, 'honeypot')
            return 200, {'ok': True, 'message': MSG_OK}
        try:
            fields, bad = self.validate(data)
        except ValueError as e:
            fields, bad = None, str(e)
        if not fields:
            self.log(ip, 'reject_invalid', field=bad)
            return 400, {'ok': False, 'error': 'invalid', 'field': bad, 'message': MSG_INVALID}
        key = data.get('idempotency_key') or ''
        if not isinstance(key, str) or (key and not KEY_RE.match(key)):
            key = ''
        chash = hashlib.sha256(json.dumps([ip, fields['email'].lower(), fields['subject'],
                                           fields['message']]).encode()).hexdigest()
        with self.lock:
            for d, ttl in ((self.done_keys, 86400), (self.recent_hashes, cfg.dup_window)):
                for k in [k for k, t in d.items() if t <= now - ttl]:
                    del d[k]
            if (key and key in self.done_keys) or chash in self.recent_hashes:
                self.log(ip, 'duplicate')
                return 200, {'ok': True, 'message': MSG_OK, 'duplicate': True}
            if (key and key in self.inflight) or chash in self.inflight:
                self.log(ip, 'duplicate_inflight')
                return 409, {'ok': False, 'error': 'in_progress', 'message': MSG_FAIL}
            if (lim.count(('send', ip), 600, now) >= cfg.ip_per_10min or
                    lim.count(('send', ip), 86400, now) >= cfg.ip_per_day):
                self.log(ip, 'rate_ip')
                return 429, {'ok': False, 'error': 'rate_limited', 'message': MSG_RATE}
            if (lim.count(('send', '*'), 3600, now) >= cfg.global_per_hour or
                    lim.count(('send', '*'), 86400, now) >= cfg.global_per_day):
                self.log(ip, 'rate_global')
                return 429, {'ok': False, 'error': 'rate_limited', 'message': MSG_RATE}
            if key:
                self.inflight.add(key)
            self.inflight.add(chash)
            # Reserve the slot now so concurrent requests cannot exceed the caps.
            lim.add(('send', ip), now)
            lim.add(('send', '*'), now)
        try:
            self.sender(self.build_email(fields))
        except Exception as e:  # never leak the exception text
            self.log(ip, 'smtp_error', kind=type(e).__name__)
            return 502, {'ok': False, 'error': 'send_failed', 'message': MSG_FAIL}
        finally:
            with self.lock:
                self.inflight.discard(key)
                self.inflight.discard(chash)
        with self.lock:
            if key:
                self.done_keys[key] = now
            self.recent_hashes[chash] = now
        self.log(ip, 'sent', name_len=len(fields['name']), subject_len=len(fields['subject']),
                 message_len=len(fields['message']))
        return 200, {'ok': True, 'message': MSG_OK}


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'sost-contact'
        sys_version = ''
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):  # silence default access log (it contains raw IPs/paths)
            pass

        def client_ip(self):
            peer = self.client_address[0]
            if service.cfg.trust_x_real_ip and peer in ('127.0.0.1', '::1'):
                xr = (self.headers.get('X-Real-IP') or '').strip()
                if xr and len(xr) <= 45 and re.match(r'\A[0-9A-Fa-f:.]+\Z', xr):
                    return xr
            return peer

        def reply(self, status, obj, extra=None):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
            self.close_connection = True

        def not_allowed(self):
            self.reply(405, {'ok': False, 'error': 'method_not_allowed', 'message': MSG_FAIL},
                       {'Allow': 'POST'})

        do_GET = do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = not_allowed

        def do_POST(self):
            if urlsplit(self.path).path.rstrip('/') not in ('', '/api/contact'):
                return self.reply(404, {'ok': False, 'error': 'not_found', 'message': MSG_FAIL})
            if self.headers.get('Transfer-Encoding'):
                return self.reply(411, {'ok': False, 'error': 'length_required', 'message': MSG_FAIL})
            try:
                n = int(self.headers.get('Content-Length', ''))
            except ValueError:
                return self.reply(411, {'ok': False, 'error': 'length_required', 'message': MSG_FAIL})
            if n < 0 or n > MAX_BODY:
                return self.reply(413, {'ok': False, 'error': 'too_large', 'message': MSG_FAIL})
            raw = self.rfile.read(n) if n else b''
            status, obj = service.handle(self.client_ip(), self.headers, raw)
            self.reply(status, obj)

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description='SOST website contact endpoint')
    ap.add_argument('--config', default=None)
    ap.add_argument('--check-config', action='store_true',
                    help='parse the config and exit (prints nothing secret)')
    args = ap.parse_args(argv)
    path = args.config or default_config_path()
    try:
        cfg = Config(path)
    except Exception as e:
        # ValueError messages are our own (no secrets); anything else: class name only.
        msg = str(e) if isinstance(e, ValueError) else type(e).__name__
        print('contact config error: %s' % msg, file=sys.stderr)
        return 2
    if args.check_config:
        print('config OK (smtp_security=%s, smtp_user set=%s, password set=%s)'
              % (cfg.smtp_security, bool(cfg.smtp_user), bool(cfg.smtp_password)))
        return 0
    service = ContactService(cfg)
    httpd = ThreadingHTTPServer((cfg.listen_host, cfg.listen_port), make_handler(service))
    httpd.daemon_threads = True
    print('sost-contact listening on %s:%d' % (cfg.listen_host, cfg.listen_port), file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
