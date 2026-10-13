#!/usr/bin/env python3
# native_multisig_vectors.py — independent reference generator for the native multisig
# spec vectors (docs/v40000/NATIVE_MULTISIG_SPEC_40000.md). Pure Python standard library:
# RIPEMD-160, secp256k1 point arithmetic, bech32m, RFC 6979 deterministic ECDSA (LOW-S).
# NON-CONSENSUS research tool; it shares no code with the node.
# Usage: python3 -I tools/research/native_multisig_vectors.py > tests/vectors/native_multisig_40000.json
import hashlib, json, struct, sys

# ---------------- RIPEMD-160 (pure python) ----------------
_r1 = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,
       3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,
       4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13]
_r2 = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,
       15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,
       12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11]
_s1 = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,
       11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,
       9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6]
_s2 = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,
       9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,
       8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11]
_K1 = [0x00000000,0x5A827999,0x6ED9EBA1,0x8F1BBCDC,0xA953FD4E]
_K2 = [0x50A28BE6,0x5C4DD124,0x6D703EF3,0x7A6D76E9,0x00000000]
def _f(j,x,y,z):
    if j<16: return x^y^z
    if j<32: return (x&y)|(~x&z)
    if j<48: return (x|~y)^z
    if j<64: return (x&z)|(y&~z)
    return x^(y|~z)
def _rol(x,n): x&=0xffffffff; return ((x<<n)|(x>>(32-n)))&0xffffffff
def ripemd160(m):
    h=[0x67452301,0xEFCDAB89,0x98BADCFE,0x10325476,0xC3D2E1F0]
    ml=len(m)*8; m=m+b'\x80'
    while len(m)%64!=56: m+=b'\x00'
    m+=struct.pack('<Q',ml)
    for i in range(0,len(m),64):
        X=struct.unpack('<16I',m[i:i+64])
        al,bl,cl,dl,el=h; ar,br,cr,dr,er=h
        for j in range(80):
            t=_rol(al+(_f(j,bl,cl,dl)&0xffffffff)+X[_r1[j]]+_K1[j//16],_s1[j])+el
            al,el,dl,cl,bl=el,dl,_rol(cl,10),bl,t&0xffffffff
            t=_rol(ar+(_f(79-j,br,cr,dr)&0xffffffff)+X[_r2[j]]+_K2[j//16],_s2[j])+er
            ar,er,dr,cr,br=er,dr,_rol(cr,10),br,t&0xffffffff
        t=(h[1]+cl+dr)&0xffffffff
        h[1]=(h[2]+dl+er)&0xffffffff; h[2]=(h[3]+el+ar)&0xffffffff
        h[3]=(h[4]+al+br)&0xffffffff; h[4]=(h[0]+bl+cr)&0xffffffff; h[0]=t
    return struct.pack('<5I',*h)
assert ripemd160(b'').hex()=='9c1185a5c5e9fc54612808977ee8f548b2258d31'
assert ripemd160(b'abc').hex()=='8eb208f7e05d987a9b044a8e98c6b087f15a0bfc'

# ---------------- secp256k1 pubkeys ----------------
P=2**256-2**32-977; N=0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G=(0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
   0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)
def padd(a,b):
    if a is None: return b
    if b is None: return a
    if a[0]==b[0] and (a[1]+b[1])%P==0: return None
    if a==b: l=3*a[0]*a[0]*pow(2*a[1],P-2,P)%P
    else: l=(b[1]-a[1])*pow(b[0]-a[0],P-2,P)%P
    x=(l*l-a[0]-b[0])%P; return (x,(l*(a[0]-x)-a[1])%P)
def pmul(k,pt=G):
    r=None
    while k:
        if k&1: r=padd(r,pt)
        pt=padd(pt,pt); k>>=1
    return r
def comp(pt): return bytes([2+(pt[1]&1)])+pt[0].to_bytes(32,'big')

def sha256(b): return hashlib.sha256(b).digest()
def sha256d(b): return sha256(sha256(b))

def policy_bytes(m, pks):
    pks=sorted(pks); return bytes([m,len(pks)])+b''.join(pks)
def msh(policy): return ripemd160(sha256(b'SOST-MS1'+policy))

# ---------------- bech32m ----------------
CS='qpzry9x8gf2tvdw0s3jn54khce6mua7l'
def polymod(v):
    g=[0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3]; c=1
    for x in v:
        b=c>>25; c=((c&0x1ffffff)<<5)^x
        for i in range(5): c^=g[i] if (b>>i)&1 else 0
    return c
def hrpx(h): return [ord(x)>>5 for x in h]+[0]+[ord(x)&31 for x in h]
def convertbits(data,f,t,pad):
    acc=0;bits=0;ret=[];mx=(1<<t)-1
    for v in data:
        acc=(acc<<f)|v; bits+=f
        while bits>=t: bits-=t; ret.append((acc>>bits)&mx)
    if pad:
        if bits: ret.append((acc<<(t-bits))&mx)
    elif bits>=f or ((acc<<(t-bits))&mx): return None
    return ret
def b32m_encode(hrp,data8):
    d=convertbits(data8,8,5,True)
    pm=polymod(hrpx(hrp)+d+[0]*6)^0x2bc830a3
    return hrp+'1'+''.join(CS[x] for x in d+[(pm>>5*(5-i))&31 for i in range(6)])
def b32m_decode(s, want_hrp):
    if s.lower()!=s: return None
    if len(s)>90: return None
    pos=s.rfind('1')
    if pos<1 or pos+7>len(s): return None
    hrp=s[:pos]
    if hrp!=want_hrp: return None
    try: d=[CS.index(c) for c in s[pos+1:]]
    except ValueError: return None
    if polymod(hrpx(hrp)+d)!=0x2bc830a3: return None
    b=convertbits(d[:-6],5,8,False)
    if b is None or len(b)!=21 or b[0]!=0x01: return None
    return bytes(b[1:])
# official BIP-350 checksum vectors
for v in ['a1lqfn3a','abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx']:
    pos=v.rfind('1'); assert polymod(hrpx(v[:pos])+[CS.index(c) for c in v[pos+1:]])==0x2bc830a3

pks=[comp(pmul(k)) for k in range(1,6)]
pol35=policy_bytes(3,pks); m35=msh(pol35)
pol23=policy_bytes(2,pks[:3]); m23=msh(pol23)
out={}
out['PK_sorted']=[p.hex() for p in sorted(pks)]
out['policy35']=pol35.hex(); out['msh35']=m35.hex()
for h in ['sostms','tsostms','dsostms']: out['addr35_'+h]=b32m_encode(h,b'\x01'+m35)
out['msh23']=m23.hex(); out['addr23_sostms']=b32m_encode('sostms',b'\x01'+m23)
# negative decode checks
a=out['addr35_sostms']
assert b32m_decode(a,'sostms')==m35
assert b32m_decode(a[:-1]+('q' if a[-1]!='q' else 'p'),'sostms') is None
assert b32m_decode('t'+a,'tsostms') is None
assert b32m_decode(a.upper(),'sostms') is None

# ---------------- CHAIN_ID ----------------
GEN='6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37'
CID={n:sha256(('SOST-CHAIN-ID-V1|%s|%s'%(n,GEN)).encode()) for n in ['mainnet','testnet','devnet']}
for n in CID: out['chain_id_'+n]=CID[n].hex()

# ---------------- sighash v2 reference vector ----------------
def ser_out(amount,typ,pkh,payload):
    return struct.pack('<qB',amount,typ)+pkh+struct.pack('<H',len(payload))+payload
def sighash_v2(chain_id, version, tx_type, prevouts, spent, outputs, i, auth_kind, auth_commit, genesis):
    hp=sha256d(b''.join(t+struct.pack('<I',ix) for t,ix in prevouts))
    hs=sha256d(b''.join(ser_out(*s) for s in spent))
    ho=sha256d(b''.join(ser_out(*o) for o in outputs))
    pre=(b'SOST-SIGHASH-V2'+chain_id+struct.pack('<IB',version,tx_type)+hp+hs+
         prevouts[i][0]+struct.pack('<I',prevouts[i][1])+struct.pack('<qB',spent[i][0],spent[i][1])+
         bytes([auth_kind])+auth_commit+ho+genesis)
    assert len(pre)==246, len(pre)
    return sha256d(pre), pre
# Vector V2-SH-1: 1 multisig input (3-of-5 above) + 1 single-sig input; 2 outputs, one with a 15-byte payload.
prev0=(bytes(range(32)),0); prev1=(bytes(range(32,64)),7)
pk1=comp(pmul(1)); pkh1=ripemd160(sha256(pk1))
spent=[(10_000_000_000,0x50,m35,b''),(250_000_000,0x00,pkh1,b'')]
outs=[(9_000_000_000,0x00,bytes([0x11]*20),bytes(range(15))),(1_249_990_000,0x50,m35,b'')]
gen=bytes.fromhex(GEN)
for n in ['mainnet','testnet','devnet']:
    h0,pre0=sighash_v2(CID[n],2,0,[prev0,prev1],spent,outs,0,1,m35,gen)
    h1,_=sighash_v2(CID[n],2,0,[prev0,prev1],spent,outs,1,0,b'\x00'*20,gen)
    out['v2sh1_%s_in0'%n]=h0.hex(); out['v2sh1_%s_in1'%n]=h1.hex()
    if n=='mainnet': out['v2sh1_mainnet_in0_preimage']=pre0.hex()

# ---------------- deterministic ECDSA (RFC 6979, low-S) ----------------
import hmac
def rfc6979_k(x, z32):
    h1=(int.from_bytes(z32,'big')%N).to_bytes(32,'big'); bx=x.to_bytes(32,'big')+h1
    V=b'\x01'*32; K=b'\x00'*32
    K=hmac.new(K,V+b'\x00'+bx,'sha256').digest(); V=hmac.new(K,V,'sha256').digest()
    K=hmac.new(K,V+b'\x01'+bx,'sha256').digest(); V=hmac.new(K,V,'sha256').digest()
    while True:
        V=hmac.new(K,V,'sha256').digest(); k=int.from_bytes(V,'big')
        if 1<=k<N: return k
        K=hmac.new(K,V+b'\x00','sha256').digest(); V=hmac.new(K,V,'sha256').digest()
def ecdsa_sign(x, z32):
    k=rfc6979_k(x,z32); R=pmul(k); r=R[0]%N; z=int.from_bytes(z32,'big')%N
    s=pow(k,N-2,N)*(z+r*x)%N
    if s>N//2: s=N-s
    return r.to_bytes(32,'big')+s.to_bytes(32,'big')
def ecdsa_verify(pub_pt, z32, sig):
    r=int.from_bytes(sig[:32],'big'); s=int.from_bytes(sig[32:],'big')
    if not (1<=r<N and 1<=s<=N//2): return False
    z=int.from_bytes(z32,'big')%N; w=pow(s,N-2,N)
    X=padd(pmul(z*w%N),pmul(r*w%N,pub_pt)); return X is not None and X[0]%N==r

# ---------------- full v2 transaction vector V2-TX-1 (mainnet) ----------------
def cs(n):
    assert n<0xfd; return bytes([n])
def ser_tx_v2(prevouts, auths, outputs):
    b=struct.pack('<IB',2,0)+cs(len(prevouts))
    for (t,ix),a in zip(prevouts,auths): b+=t+struct.pack('<I',ix)+a
    b+=cs(len(outputs))+b''.join(ser_out(*o) for o in outputs)
    return b
priv_by_pk={comp(pmul(k)):k for k in range(1,6)}
spk=sorted(pks)
h0,_=sighash_v2(CID['mainnet'],2,0,[prev0,prev1],spent,outs,0,1,m35,gen)
h1,_=sighash_v2(CID['mainnet'],2,0,[prev0,prev1],spent,outs,1,0,b'\x00'*20,gen)
idxs=[0,1,2]
sigs=[]
for i in idxs:
    sg=ecdsa_sign(priv_by_pk[spk[i]],h0); assert ecdsa_verify(pmul(priv_by_pk[spk[i]]),h0,sg); sigs.append((i,sg))
s1=ecdsa_sign(1,h1); assert ecdsa_verify(pmul(1),h1,s1)
auth0_unsigned=b'\x01'+pol35+b'\x00'
auth0=b'\x01'+pol35+bytes([3])+b''.join(bytes([i])+sg for i,sg in sigs)
auth1=b'\x00'+s1+pk1
assert len(b'\x00'*36)+len(auth0)==400
tx_unsigned=ser_tx_v2([prev0,prev1],[auth0_unsigned,b'\x00'+b'\x00'*97],outs)
tx_signed=ser_tx_v2([prev0,prev1],[auth0,auth1],outs)
out['v2tx1_signers_priv']=[priv_by_pk[spk[i]] for i in idxs]; out['v2tx1_key_indexes']=idxs
for i,sg in sigs: out['v2tx1_in0_sig_idx%d'%i]=sg.hex()
out['v2tx1_in1_sig']=s1.hex()
out['v2tx1_unsigned_template_hex']=tx_unsigned.hex()
out['v2tx1_signed_hex']=tx_signed.hex()
out['v2tx1_signed_len']=len(tx_signed)
out['v2tx1_txid']=sha256d(tx_signed).hex()
fee=spent[0][0]+spent[1][0]-outs[0][0]-outs[1][0]
out['v2tx1_fee_stocks']=fee

out['_meta']={'spec':'docs/v40000/NATIVE_MULTISIG_SPEC_40000.md','status':'NORMATIVE VECTORS (implementation not authorized)',
  'v2sh1_tx':'2 inputs: in0 OUT_MULTISIG 3-of-5 (10,000,000,000 stocks), in1 OUT_TRANSFER single-sig priv 1 (250,000,000); '
             'outputs: 9,000,000,000 OUT_TRANSFER pkh 0x11*20 with 15-byte payload 00..0e (consensus-valid, not policy-standard), '
             '1,249,990,000 OUT_MULTISIG change to the same MSH',
  'prevouts':['00..1f:0','20..3f:7'],'genesis':GEN,'sighash':'v2, 246-byte preimage',
  'ecdsa':'RFC 6979 HMAC-SHA256 nonce, LOW-S, compact r||s (matches libsecp256k1 secp256k1_ecdsa_sign with the default nonce)'}
print(json.dumps(out, indent=2, sort_keys=True))
