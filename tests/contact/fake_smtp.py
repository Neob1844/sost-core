"""Tiny in-process SMTP sink for tests (stdlib only; smtpd was removed in Python 3.12).

Speaks just enough ESMTP for smtplib: EHLO/HELO, AUTH PLAIN/LOGIN (accepts any), MAIL,
RCPT, DATA, RSET, NOOP, QUIT. Every accepted message is stored as
{'mail_from', 'rcpt_to', 'data', 'auth'}. Set .fail = True to answer DATA with 554.
"""
import socket
import threading


class FakeSMTP:
    def __init__(self, host='127.0.0.1', port=0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(16)
        self.host, self.port = self.sock.getsockname()
        self.messages = []
        self.fail = False
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _session(self, conn):
        f = conn.makefile('rb')
        w = lambda s: conn.sendall((s + '\r\n').encode())
        w('220 fake.smtp ESMTP')
        cur = {'mail_from': None, 'rcpt_to': [], 'auth': None}
        try:
            while True:
                line = f.readline()
                if not line:
                    return
                cmd = line.decode('utf-8', 'replace').rstrip('\r\n')
                up = cmd.upper()
                if up.startswith('EHLO'):
                    conn.sendall(b'250-fake.smtp\r\n250-AUTH PLAIN LOGIN\r\n250 8BITMIME\r\n')
                elif up.startswith('HELO'):
                    w('250 fake.smtp')
                elif up.startswith('AUTH'):
                    cur['auth'] = cmd.split()[1] if len(cmd.split()) > 1 else '?'
                    if up.startswith('AUTH LOGIN') and len(cmd.split()) == 2:
                        w('334 VXNlcm5hbWU6'); f.readline(); w('334 UGFzc3dvcmQ6'); f.readline()
                    elif up == 'AUTH PLAIN':
                        w('334 '); f.readline()
                    w('235 ok')
                elif up.startswith('MAIL FROM:'):
                    cur['mail_from'] = cmd[10:].strip().split()[0].strip('<>'); w('250 ok')
                elif up.startswith('RCPT TO:'):
                    cur['rcpt_to'].append(cmd[8:].strip().strip('<>')); w('250 ok')
                elif up == 'DATA':
                    w('354 go')
                    buf = []
                    while True:
                        l = f.readline()
                        if not l or l in (b'.\r\n', b'.\n'):
                            break
                        if l.startswith(b'..'):
                            l = l[1:]
                        buf.append(l)
                    if self.fail:
                        w('554 rejected')
                    else:
                        self.messages.append(dict(cur, data=b''.join(buf)))
                        w('250 queued')
                    cur = {'mail_from': None, 'rcpt_to': [], 'auth': cur['auth']}
                elif up in ('RSET', 'NOOP'):
                    w('250 ok')
                elif up == 'QUIT':
                    w('221 bye'); return
                else:
                    w('502 no')
        finally:
            try:
                conn.close()
            except Exception:
                pass
