# Website contact endpoint (`POST /api/contact`)

Status: **prepared, NOT deployed.** Nothing in this directory has been installed on the VPS.

Front-end switch: the form in `website/js/nav-toggle.js` ships with
`var CONTACT_SEND_ENABLED = false;` — the SEND button is disabled, a "Sending is not active
yet" note is shown and the page makes no request at all. Only after this service is installed,
`/etc/sost/contact-api.conf` exists and the real-email test below has passed, change that one
line to `true` (and bump the `nav-toggle.js?v=` cache-buster on the pages that load it).

The nav "Contact" item opens the contact emblem; a click on the emblem opens a small form
(`website/js/nav-toggle.js`) that posts JSON to the same-origin endpoint `/api/contact`.
nginx proxies that path to `ops/sost-contact-api.py` (Python 3 stdlib only), which sends
one plain-text email per accepted submission to a **fixed inbox configured only on the
server**. The inbox address never appears in the website, this repository or any response.

| File | Goes to |
|---|---|
| `ops/sost-contact-api.py` | `/opt/sost/sost-contact-api.py` (root:root 0644) |
| `deploy/contact/sost-contact-api.service` | `/etc/systemd/system/sost-contact-api.service` |
| `deploy/contact/contact-api.conf.example` | template for `/etc/sost/contact-api.conf` (root:root **0600**) |
| `deploy/contact/nginx-contact-api.conf` | pasted into the `sostcore.com` server block of `/etc/nginx/sites-enabled/sost` |
| `tests/contact/` | local tests only (fake SMTP); not deployed |

## Why STRATO SMTP (and not a local MTA)

Read-only audit, 2026-10-20:

* VPS (Ubuntu 24.04, Python 3.12.3, systemd 255): **no MTA** installed (no postfix, exim,
  msmtp, sendmail). Outbound TCP to `smtp.strato.de` 465 and 587 is open.
* DNS for `sostcore.com`: `MX 5 smtpin.rzone.de` (STRATO); `_dmarc` = `v=DMARC1;p=reject;`;
  DKIM key published at `strato-dkim-0002._domainkey`; **no SPF TXT record** on the apex.
* Consequence: a message with a `From:` in `sostcore.com` sent directly from the VPS has no
  SPF pass and no DKIM signature, so DMARC `p=reject` makes receivers drop it. A message
  submitted to STRATO (authenticated as the mailbox) is DKIM-signed by STRATO for the domain
  (aligned `d=`), which satisfies DMARC even without SPF.
* So the service submits to `smtp.strato.de:465` (implicit TLS) authenticated as the STRATO
  mailbox, with envelope sender and `From:` = that same mailbox (`mail_from` = `smtp_user`).
  The visitor's address is only placed in `Reply-To:`. No address was invented.
* Recommended (owner, optional): publish an SPF record so SPF also aligns, e.g.
  `sostcore.com. TXT "v=spf1 include:_spf.strato.com ~all"` (STRATO's own include; check
  STRATO's current recommendation before publishing; keep `include:` entries for any other
  service that sends as the domain).

## Security properties (enforced by the service; covered by `tests/contact/`)

* POST only (405 otherwise); JSON or form-urlencoded; body ≤ 16 KB (nginx and service).
* `email` required, strict ASCII syntax (≤ 254, local part ≤ 64); `subject` required ≤ 200;
  `message` required ≤ 5000; `name` optional ≤ 100.
* CR/LF/control characters in name, email or subject → 400 (header injection).
* The client cannot set To/Cc/Bcc/From: unknown fields are ignored; recipient and sender
  come from the config only (no open relay). Plain text, no attachments.
* Honeypot field `website`: filled → fake success, nothing sent.
* Origin must be `https://sostcore.com` / `https://www.sostcore.com` (Referer fallback);
  missing both → 403. No CORS headers.
* Rate limits (in memory): 3 sends / 10 min and 20 / day per IP, 30 requests / 10 min per
  IP, global 30 / hour and 200 / day; plus nginx `limit_req` 6 r/m burst 5.
* Duplicates: same idempotency key (24 h) or same IP+email+subject+message (10 min) →
  original success returned, no second email; concurrent duplicates → 409.
* Responses are fixed JSON; they never contain the inbox, the SMTP host, paths or exception
  text. Logs (journal) hold only result code, field lengths and a salted per-process hash
  of the IP — never the message, name, subject or visitor email. Nothing is stored on disk.

Run the tests locally: `python3 tests/contact/test_contact_api.py -v`.

## Deploy (owner-run, when authorised)

```bash
# 0. From the laptop/WSL checkout of the reviewed branch
cd /path/to/sost-core
python3 tests/contact/test_contact_api.py
scp -i ~/.ssh/sost_vps ops/sost-contact-api.py deploy/contact/sost-contact-api.service \
    deploy/contact/nginx-contact-api.conf deploy/contact/contact-api.conf.example \
    root@212.132.108.244:/root/contact-deploy/

# 1. On the VPS (as root)
ssh -i ~/.ssh/sost_vps root@212.132.108.244
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S); RB=/opt/sost/rollback-contact-$TS; mkdir -p "$RB"
cp -a /etc/nginx/sites-enabled/sost "$RB/nginx-sost.conf"
install -o root -g root -m 0644 /root/contact-deploy/sost-contact-api.py /opt/sost/sost-contact-api.py
install -o root -g root -m 0644 /root/contact-deploy/sost-contact-api.service /etc/systemd/system/sost-contact-api.service
# Config: create from the template, then edit the four <PLACEHOLDERS> (inbox, mailbox, user, password)
install -o root -g root -m 0600 /root/contact-deploy/contact-api.conf.example /etc/sost/contact-api.conf
nano /etc/sost/contact-api.conf            # replace every <...>; never paste it anywhere else
python3 /opt/sost/sost-contact-api.py --config /etc/sost/contact-api.conf --check-config
systemctl daemon-reload && systemctl enable --now sost-contact-api.service
systemctl --no-pager status sost-contact-api.service | head -5
curl -s -o /dev/null -w '%{http_code}\n' -X GET http://127.0.0.1:18330/api/contact   # expect 405

# 2. nginx: add the limit_req_zone line at the top of /etc/nginx/sites-enabled/sost
#    (next to the other limit_req_zone lines) and paste the `location = /api/contact`
#    block from nginx-contact-api.conf inside the sostcore.com server block.
nano /etc/nginx/sites-enabled/sost
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w '%{http_code}\n' https://sostcore.com/api/contact            # expect 403 (GET denied)
curl -s -X POST -H 'Content-Type: application/json' -H 'Origin: https://evil.example' \
     -d '{}' https://sostcore.com/api/contact; echo                                    # expect forbidden
rm -rf /root/contact-deploy
```

The website files (`website/js/nav-toggle.js` + the HTML pages with the new cache-buster)
are deployed with the usual surgical website deploy. Deploy the endpoint first: until it is
live, the form shows "Unable to send the message. Please try again later."

## REAL EMAIL TEST (pending: needs the SMTP credentials in the server config)

1. Make sure `/etc/sost/contact-api.conf` has the real mailbox, password and inbox, and
   `--check-config` prints `config OK (... smtp_user set=True, password set=True)`.
2. Open `https://sostcore.com/`, click **Contact** → click the emblem → fill Email,
   Subject `REAL TEST <date>`, Message → **SEND MESSAGE**. Expect "Your message has been sent."
3. Check the inbox: one message, `From: SOST website contact form <mailbox>`, `Reply-To:` the
   address typed in the form, subject `[sostcore.com contact] REAL TEST <date>`, body starting
   `From website contact form`. In the raw headers, `Authentication-Results` should show
   `dkim=pass header.d=sostcore.com` and `dmarc=pass`.
4. On failure: `journalctl -u sost-contact-api -n 20` shows `contact smtp_error kind=<Class>`
   (e.g. `SMTPAuthenticationError` → wrong user/password; `SMTPSenderRefused` → `mail_from`
   is not the authenticated mailbox).

## Rollback

```bash
systemctl disable --now sost-contact-api.service
cp -a /opt/sost/rollback-contact-<TS>/nginx-sost.conf /etc/nginx/sites-enabled/sost
nginx -t && systemctl reload nginx
rm -f /etc/systemd/system/sost-contact-api.service && systemctl daemon-reload
# optional: shred -u /etc/sost/contact-api.conf ; rm -f /opt/sost/sost-contact-api.py
```

Website rollback: redeploy the previous `website/js/nav-toggle.js` and HTML cache-buster.
With the endpoint gone and the old JS, Contact shows only the emblem again.
