"""Protocol-accurate SOST P2P peer (plaintext, enc OFF). For the isolated adversarial lab.
Frame: [u32 LE P2P_MAGIC=0x534F5354][4B cmd][u32 LE len][payload]. VERS payload: i64 LE height + 32B genesis."""
import socket, struct, time, os
P2P_MAGIC = 0x534F5354
def send_frame(sock, cmd, payload=b''):
    cmd = cmd.encode() if isinstance(cmd,str) else cmd
    assert len(cmd)==4
    hdr = struct.pack('<I', P2P_MAGIC) + cmd + struct.pack('<I', len(payload))
    sock.sendall(hdr + payload)
def recv_all(sock, n, deadline):
    buf=b''
    while len(buf)<n:
        sock.settimeout(max(0.05, deadline-time.time()))
        try: chunk=sock.recv(n-len(buf))
        except (socket.timeout, OSError): return None
        if not chunk: return None
        buf+=chunk
    return buf
def recv_frame(sock, timeout=3.0):
    dl=time.time()+timeout
    hdr=recv_all(sock,12,dl)
    if not hdr or len(hdr)<12: return None
    magic,=struct.unpack('<I',hdr[:4]); cmd=hdr[4:8].rstrip(b'\x00').decode('latin1'); ln,=struct.unpack('<I',hdr[8:12])
    if magic!=P2P_MAGIC: return ('BADMAGIC',b'')
    if ln>4*1024*1024: return ('OVERSIZE',b'')
    pl=recv_all(sock,ln,dl) if ln else b''
    if ln and pl is None: return None
    return (cmd, pl or b'')
def vers_payload(height, genesis32):
    return struct.pack('<q', height) + genesis32
def connect(host, port, timeout=4.0):
    s=socket.create_connection((host,port), timeout=timeout); return s
