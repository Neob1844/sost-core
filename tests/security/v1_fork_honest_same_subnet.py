# HONEST peer (different IP) sends ONE fork after the flood.
import socket,struct,sys,json,time
MAGIC=0x534F5354
def frame(c,p=b''): return struct.pack('<I',MAGIC)+c+struct.pack('<I',len(p))+p
host,port,gen,base_json=sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4]
base=json.load(open(base_json))
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
try: s.bind(('127.0.0.201',0))
except OSError: pass
s.settimeout(10); s.connect((host,port))
s.sendall(frame(b'VERS',struct.pack('<q',500)+bytes.fromhex(gen)))
time.sleep(0.5)
b=dict(base)
b['block_id']='cafe0001'+base['block_id'][8:]  # unique honest fork
b['timestamp']=base['timestamp']+999999
b['height']=base['height']+1
s.sendall(frame(b'BLCK',json.dumps(b,separators=(',',':')).encode()))
time.sleep(0.5); s.close()
print(json.dumps({'honest_block_id':b['block_id'][:16]}))
