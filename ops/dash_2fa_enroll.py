#!/usr/bin/env python3
# Enrol/rotate TOTP 2FA + backup codes for a SOST dashboard admin user.
# Writes /etc/sost/dash-2fa.json (chmod 600) with enabled=FALSE (activate separately
# only after the user confirms a valid code). Prints the QR / secret / backup codes
# ONCE to stdout — never logged, never committed. Backup codes are stored HASHED only.
#
# Usage:
#   sudo python3 dash_2fa_enroll.py <user> [--issuer "SOST Dashboard"]
#   # then, after the user confirms a code:  dash_2fa_enroll.py <user> --activate
#   #                                        dash_2fa_enroll.py <user> --verify 123456
import sys, os, json, base64, hmac, hashlib, struct, time, secrets as S, re

TFA_PATH = os.environ.get("DASH_2FA_PATH", "/etc/sost/dash-2fa.json")

def _load():
    try: return json.load(open(TFA_PATH))
    except Exception: return {}
def _save(d):
    tmp=TFA_PATH+".tmp"; open(tmp,"w").write(json.dumps(d,separators=(",",":")))
    os.chmod(tmp,0o600); os.replace(tmp,TFA_PATH); os.chmod(TFA_PATH,0o600)

def _totp_at(sec,t,step=30,digits=6):
    key=base64.b32decode(sec.upper()+"="*((8-len(sec)%8)%8))
    h=hmac.new(key,struct.pack(">Q",int(t//step)),hashlib.sha1).digest(); o=h[-1]&0x0f
    return str((struct.unpack(">I",h[o:o+4])[0]&0x7fffffff)%(10**digits)).zfill(digits)
def totp_verify(sec,code,window=1,step=30):
    code=str(code).strip().zfill(6); now=time.time()
    return any(hmac.compare_digest(_totp_at(sec,now+w*step,step),code) for w in range(-window,window+1))

def gen_backup(n=10):
    codes=["-".join(S.token_hex(2) for _ in range(2)) for _ in range(n)]  # e.g. ab12-cd34
    hashes=[hashlib.sha256(re.sub(r'[^A-Za-z0-9]','',c).lower().encode()).hexdigest() for c in codes]
    return codes,hashes

def main():
    if len(sys.argv)<2:
        print("usage: dash_2fa_enroll.py <user> [--issuer NAME | --activate | --deactivate | --verify CODE]"); sys.exit(2)
    user=sys.argv[1]; issuer="SOST Dashboard"; mode="enroll"; verify_code=None
    a=sys.argv[2:]
    if "--activate" in a: mode="activate"
    elif "--deactivate" in a: mode="deactivate"
    elif "--verify" in a: mode="verify"; verify_code=a[a.index("--verify")+1]
    elif "--issuer" in a: issuer=a[a.index("--issuer")+1]

    d=_load(); rec=d.get(user,{})

    if mode=="verify":
        ok=bool(rec.get("secret")) and totp_verify(rec["secret"],verify_code)
        print("VERIFY:", "OK" if ok else "FAIL"); sys.exit(0 if ok else 1)
    if mode=="activate":
        if not rec.get("secret"): print("no secret enrolled for",user); sys.exit(1)
        rec["enabled"]=True; d[user]=rec; _save(d); print("2FA ACTIVATED for",user); sys.exit(0)
    if mode=="deactivate":
        rec["enabled"]=False; d[user]=rec; _save(d); print("2FA DEACTIVATED for",user); sys.exit(0)

    # enroll (generates new secret + backup codes; enabled stays FALSE)
    secret=base64.b32encode(S.token_bytes(20)).decode().rstrip("=")   # 160-bit
    codes,hashes=gen_backup(10)
    d[user]={"secret":secret,"enabled":False,"backup_hashes":hashes,"created":int(time.time())}
    _save(d)
    label="%s:%s"%(issuer.replace(" ",""),user)
    uri="otpauth://totp/%s?secret=%s&issuer=%s&digits=6&period=30&algorithm=SHA1"%(label,secret,issuer.replace(" ","%20"))
    print("="*60); print("SOST DASHBOARD 2FA ENROLMENT —",user,"(status: enabled=FALSE)"); print("="*60)
    try:
        import qrcode
        qr=qrcode.QRCode(border=1); qr.add_data(uri); qr.make(); qr.print_ascii(invert=True)
    except Exception:
        print("(qrcode module not installed — use manual entry or the otpauth URI below)")
    print(); print("otpauth URI :",uri)
    print("MANUAL SECRET:",secret,"  (type: TOTP, 6 digits, 30s, SHA1)")
    print(); print("BACKUP CODES (10, one-time, shown ONCE — store offline):")
    for c in codes: print("   ",c)
    print(); print("Store file  :",TFA_PATH,"(enabled=FALSE; backup codes stored HASHED)")
    print("Next        : scan/enter -> confirm with --verify <code> -> then --activate")

if __name__=="__main__": main()
