import sys, os, time, threading, socket, struct, binascii, random, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sostpeer as P

VP2P=int(sys.argv[1]); VRPC=int(sys.argv[2]); GEN=binascii.unhexlify(sys.argv[3])
NPID=int(sys.argv[4]); N=int(sys.argv[5]); DUR=int(sys.argv[6])

stop=threading.Event()
stats={'conn':0,'sent':0,'err':0}
lock=threading.Lock()
def bump(k,v=1):
    with lock: stats[k]=stats.get(k,0)+v

def junk_block():  # malformed block JSON
    return json.dumps({"block_id":"ff"*32,"prev_hash":"00"*32,"height":random.randint(1,99999),
                       "merkle_root":"ab"*32,"commit":"cd"*32,"checkpoints_root":"ef"*32,
                       "timestamp":random.randint(0,2**40),"bits_q":random.randint(0,2**32),
                       "nonce":random.randint(0,2**32),"transactions":[]}).encode()

def peer(idx):
    behav = idx % 7
    try:
        s=P.connect('127.0.0.1',VP2P,timeout=4); bump('conn')
    except Exception:
        bump('err'); return
    try:
        if behav==5:  # framejunk: garbage bytes, no valid handshake
            for _ in range(5):
                if stop.is_set(): break
                s.sendall(os.urandom(random.randint(8,400))); bump('sent'); time.sleep(0.2)
            return
        # honest-ish handshake — reply VACK to the node's VERS so the connection persists
        h = 999999 if behav==0 else random.randint(0,5)
        P.send_frame(s,'VERS',P.vers_payload(h,GEN)); bump('sent')
        s.settimeout(0.2)
        for _ in range(4):
            try:
                f=P.recv_frame(s,0.4)
            except Exception:
                f=None
            if f and f[0]=='VERS': P.send_frame(s,'VACK',b''); bump('sent')
            if f and f[0]=='VACK': break
            if f is None: break
        while not stop.is_set():
            if behav==0:   # fakeheight then silent
                time.sleep(0.5)
            elif behav==1: # orphan/malformed BLCK flood
                P.send_frame(s,'BLCK',junk_block()); bump('sent'); time.sleep(0.02)
            elif behav==2: # GETB flood (serving saturation)
                P.send_frame(s,'GETB',struct.pack('<q',random.randint(0,20))); bump('sent'); time.sleep(0.01)
            elif behav==3: # churn: reconnect rapidly
                s.close(); time.sleep(0.05); 
                try: s=P.connect('127.0.0.1',VP2P,timeout=3); bump('conn'); P.send_frame(s,'VERS',P.vers_payload(0,GEN))
                except Exception: bump('err'); return
            elif behav==4: # silent after handshake
                time.sleep(1.0)
            elif behav==6: # duplicate block spam (same junk)
                P.send_frame(s,'BLCK',DUP); bump('sent'); time.sleep(0.03)
            # drain any incoming without blocking long
            s.settimeout(0.01)
            try:
                while True:
                    d=s.recv(65536)
                    if not d: break
            except Exception: pass
    except Exception:
        bump('err')
    finally:
        try: s.close()
        except Exception: pass
DUP=junk_block()

def rpc(method):
    req=urllib.request.Request(f'http://127.0.0.1:{VRPC}/', data=json.dumps({"method":method,"params":[],"id":1}).encode(), headers={'Content-Type':'application/json'})
    t0=time.time()
    with urllib.request.urlopen(req, timeout=6) as r: r.read()
    return (time.time()-t0)*1000
def cpu_rss():
    try:
        st=open(f'/proc/{NPID}/stat').read().split(); ut,stt=int(st[13]),int(st[14])
        rss=int(open(f'/proc/{NPID}/status').read().split('VmRSS:')[1].split()[0])//1024
        return ut+stt, rss
    except Exception: return None,None

# launch peers
threads=[threading.Thread(target=peer,args=(i,),daemon=True) for i in range(N)]
t0=time.time()
for th in threads: th.start(); 
# sample victim during storm
HZ=os.sysconf('SC_CLK_TCK'); prev=None; peak_rss=0; lat=[]; avail=0; samples=0
while time.time()-t0 < DUR:
    time.sleep(3); samples+=1
    c,rss=cpu_rss()
    if rss is None: print("[D] VICTIM DIED"); break
    peak_rss=max(peak_rss,rss)
    cpu_pct=None
    if prev is not None: cpu_pct=100.0*(c-prev[0])/(HZ*(time.time()-prev[1]))
    prev=(c,time.time())
    try: ms=rpc('getblockcount'); lat.append(ms); avail+=1; a='ok'
    except Exception: ms=-1; a='TIMEOUT'
    print(f"[D]  t={int(time.time()-t0):2d}s peers_conn={stats['conn']} sent={stats['sent']} RSS={rss}MB CPU={('%.0f'%cpu_pct+'%') if cpu_pct is not None else '—'} rpc={('%.0f'%ms+'ms') if ms>=0 else a}")
stop.set(); time.sleep(1)
print(f"[D] SUMMARY: N={N} sim-peers, {DUR}s | conns={stats['conn']} frames_sent={stats['sent']} errs={stats['err']}")
print(f"[D] victim peakRSS={peak_rss}MB rpc_availability={avail}/{samples} avg_lat={('%.0f'%(sum(lat)/len(lat))) if lat else 'NA'}ms")
