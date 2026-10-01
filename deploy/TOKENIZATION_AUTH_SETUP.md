# Enabling server-side admin auth for Tokenization / DEX (operator procedure)

The password is chosen and set by YOU and is never stored in git, logs or JavaScript.

## 1. Create the bcrypt credential (on the VPS, as root)
```
# apache2-utils provides htpasswd; -B = bcrypt (strong). You will be prompted for the password.
sudo apt-get install -y apache2-utils
sudo htpasswd -B -c /etc/nginx/sost-tokenization.htpasswd <your-admin-username>
sudo chown root:www-data /etc/nginx/sost-tokenization.htpasswd
sudo chmod 640 /etc/nginx/sost-tokenization.htpasswd
```
(Use Argon2id instead if you prefer: generate the hash with `openssl`/`argon2` and
place a `user:$argon2id$...` line — nginx accepts crypt-format hashes it was built with;
bcrypt via `-B` is the portable default and meets the strong-hash requirement.)

## 2. Add the rate-limit zone (once) to the http{} block
```
# /etc/nginx/nginx.conf  (inside http { })
limit_req_zone $binary_remote_addr zone=sost_tokauth:10m rate=10r/m;
```

## 3. Include the auth location in the sostcore.com HTTPS server block
```
# inside server { listen 443 ... server_name sostcore.com; } :
include /etc/nginx/snippets/sost-tokenization-auth.conf;   # = deploy/nginx-tokenization-auth.conf
```

## 4. Test & reload (zero downtime)
```
sudo nginx -t && sudo systemctl reload nginx
```

## Properties
- **Deny-by-default:** no htpasswd file -> 403 for all five interfaces.
- **HTTPS only** (HSTS already enforced site-wide), credentials never sent in clear.
- **Rate limited** (10 req/min + burst 5) to deter brute force; 429 on excess.
- **no-store** on the sensitive pages; nosniff / DENY framing / no-referrer.
- **Logout:** Basic-auth logout = close the browser / clear the saved credential; for a
  session-cookie flow instead, say so and it will be swapped for a server session with
  Secure + HttpOnly + SameSite=Strict cookies.
- Second, independent barrier is the consensus admin gate (S14) — see
  docs/v30000/ADMIN_CONSENSUS_GATE.md. Even with web access, only admin-signed asset
  operations are accepted by the network.

## To open public access later (controlled)
1. Flip `DEX_PUBLIC_ENABLED` / `TOKENIZATION_PUBLIC_ENABLED` to true in
   website/js/tokenization-gate.js (web execution + notice switch to public copy).
2. Lift the consensus gate per docs/v30000/ADMIN_CONSENSUS_GATE.md (future height-gated
   release) — until BOTH are done, operations stay admin-only at the protocol level.
3. Remove or relax this nginx auth location.
