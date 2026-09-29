#!/usr/bin/env python3
"""Minimal plaintext SOST P2P peer that serves blocks from a chain.json fixture in a
chosen ORDER, to reproduce the orphan dead-end deterministically.

usage: orphan_peer.py <chain.json> <listen_port> <announce_height> <order,comma,sep> [relay_after]
  The node under test connects to us (--connect 127.0.0.1:<port> --p2p-enc off).
  On its first GETB we send BLCK for each height in <order>, then DONE.
  If relay_after is given, 3 s later we push those heights as unsolicited relay BLCKs.
"""
import socket, struct, sys, time

MAGIC = 0x534F5354
chain, port, ann = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
order = [int(x) for x in sys.argv[4].split(',')]
relay = [int(x) for x in sys.argv[5].split(',')] if len(sys.argv) > 5 else []

raw = {}
with open(chain) as f:
    for line in f:
        s = line.strip().rstrip(',')
        if s.startswith('{"block_id"'):
            h = int(s.split('"height":', 1)[1].split(',', 1)[0])
            raw[h] = s
genesis = bytes.fromhex(raw[0].split('"block_id":"', 1)[1][:64])

def send(c, cmd, payload=b''):
    c.sendall(struct.pack('<I', MAGIC) + cmd.encode() + struct.pack('<I', len(payload)) + payload)

def recv(c):
    hdr = b''
    while len(hdr) < 12:
        d = c.recv(12 - len(hdr))
        if not d: return None, None
        hdr += d
    n = struct.unpack('<I', hdr[8:12])[0]
    body = b''
    while len(body) < n:
        d = c.recv(n - len(body))
        if not d: return None, None
        body += d
    return hdr[4:8].decode(), body

s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', port)); s.listen(1)
c, _ = s.accept()
send(c, 'VERS', struct.pack('<q', ann) + genesis)
served = False
c.settimeout(30)
while True:
    try:
        cmd, body = recv(c)
    except socket.timeout:
        break
    if cmd is None: break
    print('peer<-', cmd, len(body), flush=True)
    if cmd == 'VERS':
        send(c, 'VACK')
    elif cmd == 'GETB' and not served:
        served = True
        frm = struct.unpack('<q', body[:8])[0]
        print('GETB from', frm, '-> serving order', order, flush=True)
        for h in order:
            send(c, 'BLCK', raw[h].encode())
            time.sleep(0.3)
        send(c, 'DONE')
        if relay:
            time.sleep(3)
            for h in relay:
                print('relay BLCK', h, flush=True)
                send(c, 'BLCK', raw[h].encode()); time.sleep(0.5)
    elif cmd == 'GETB':
        send(c, 'DONE')
    elif cmd == 'PING':
        send(c, 'PONG')
