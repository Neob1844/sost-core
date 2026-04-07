#!/usr/bin/env python3
"""
SOST P2P Sync Simulation Test
Connects to seed node as a new peer and verifies block delivery
through the critical 2500→2501 boundary and up to the tip.

Usage: python3 scripts/test_sync_simulation.py [host] [port]
"""
import socket
import struct
import hashlib
import time
import sys
import json

MAGIC = 0x534F5354  # "SOST"
DEFAULT_HOST = "seed.sostcore.com"
DEFAULT_PORT = 19333
GENESIS_HASH = bytes.fromhex("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37")

def write_u32(v):
    return struct.pack('<I', v)

def read_u32(b):
    return struct.unpack('<I', b)[0]

def write_i64(v):
    return struct.pack('<q', v)

def read_i64(b):
    return struct.unpack('<q', b)[0]

def send_msg(sock, cmd, payload=b''):
    """Send a P2P message (plaintext framing)."""
    hdr = write_u32(MAGIC) + cmd.encode().ljust(4, b'\x00')[:4] + write_u32(len(payload))
    sock.sendall(hdr + payload)

def recv_msg(sock, timeout=30):
    """Receive a P2P message (plaintext framing)."""
    sock.settimeout(timeout)
    try:
        hdr = b''
        while len(hdr) < 12:
            chunk = sock.recv(12 - len(hdr))
            if not chunk:
                return None, None
            hdr += chunk

        magic = read_u32(hdr[0:4])
        if magic != MAGIC:
            print(f"  [WARN] Bad magic: {hex(magic)}")
            return None, None

        cmd = hdr[4:8].rstrip(b'\x00').decode('ascii', errors='replace')
        payload_len = read_u32(hdr[8:12])

        if payload_len > 10_000_000:  # 10MB max
            print(f"  [WARN] Payload too large: {payload_len}")
            return None, None

        payload = b''
        while len(payload) < payload_len:
            chunk = sock.recv(min(65536, payload_len - len(payload)))
            if not chunk:
                return None, None
            payload += chunk

        return cmd, payload
    except socket.timeout:
        return "TIMEOUT", b''

def test_sync(host, port):
    print(f"=" * 60)
    print(f"SOST P2P Sync Simulation Test")
    print(f"Target: {host}:{port}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"=" * 60)

    # Connect
    print(f"\n[1] Connecting to {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((host, port))
        print(f"    Connected OK")
    except Exception as e:
        print(f"    FAILED: {e}")
        return False

    # Check if seed sends EKEY (encryption key exchange)
    print(f"\n[2] Waiting for encryption handshake...")
    cmd, payload = recv_msg(sock, timeout=5)

    encrypted = False
    if cmd == "EKEY" and payload and len(payload) == 32:
        print(f"    Seed offers encryption (X25519 key received)")
        print(f"    Declining encryption — testing PLAINTEXT mode")
        # Don't respond with our key — seed should fall back to plaintext
        # Actually, we need to send VERS without encryption
        encrypted = False
    elif cmd == "TIMEOUT":
        print(f"    No encryption offered — plaintext mode")
    else:
        print(f"    Unexpected: cmd={cmd}, len={len(payload) if payload else 0}")

    # Send VERS (version message with our height=0)
    print(f"\n[3] Sending VERS (height=0, genesis hash)...")
    vers_payload = write_i64(0) + GENESIS_HASH
    send_msg(sock, "VERS", vers_payload)

    # Wait for VACK
    print(f"    Waiting for VACK...")
    cmd, payload = recv_msg(sock, timeout=10)
    if cmd == "EKEY":
        # Seed sent EKEY before VACK — we need to handle this
        print(f"    Got EKEY first — seed wants encryption")
        print(f"    Sending our VERS again after EKEY...")
        send_msg(sock, "VERS", vers_payload)
        cmd, payload = recv_msg(sock, timeout=10)

    if cmd == "VACK":
        print(f"    VACK received — handshake OK")
    elif cmd == "VERS":
        # Seed sent its VERS — extract height
        if payload and len(payload) >= 8:
            seed_height = read_i64(payload[:8])
            print(f"    Got seed VERS: height={seed_height}")
            # Send VACK back
            send_msg(sock, "VACK", b'')
            print(f"    Sent VACK")
    else:
        print(f"    Unexpected response: cmd={cmd}")
        # Try continuing anyway

    # Request blocks starting from 1
    print(f"\n[4] Requesting blocks 1..500 (first batch)...")
    send_msg(sock, "GETB", write_i64(1))

    blocks_received = {}
    highest_block = 0
    batch_count = 0
    start_time = time.time()
    critical_boundary_passed = False

    while True:
        cmd, payload = recv_msg(sock, timeout=30)

        if cmd is None:
            print(f"    Connection closed after {len(blocks_received)} blocks")
            break

        if cmd == "TIMEOUT":
            print(f"    Timeout after {len(blocks_received)} blocks (highest: {highest_block})")
            break

        if cmd == "BLCK":
            # Parse block JSON to get height
            try:
                block_json = payload.decode('utf-8', errors='replace')
                # Quick parse for height
                h_idx = block_json.find('"height":')
                if h_idx >= 0:
                    h_str = block_json[h_idx+9:h_idx+20].split(',')[0].split('}')[0].strip()
                    height = int(h_str)

                    has_tx = '"transactions"' in block_json
                    block_size = len(payload)

                    blocks_received[height] = {
                        'size': block_size,
                        'has_tx': has_tx,
                    }

                    if height > highest_block:
                        highest_block = height

                    # Log milestones
                    if height % 500 == 0 or height in [2499, 2500, 2501, 2502]:
                        elapsed = time.time() - start_time
                        print(f"    Block #{height}: {block_size}B, tx={has_tx}, elapsed={elapsed:.1f}s")

                    # Check critical boundary
                    if height == 2501 and not critical_boundary_passed:
                        critical_boundary_passed = True
                        print(f"    *** CRITICAL: Block #2501 RECEIVED ({block_size}B, tx={has_tx}) ***")

            except Exception as e:
                print(f"    Block parse error: {e}")

        elif cmd == "DONE":
            batch_count += 1
            elapsed = time.time() - start_time
            print(f"    Batch {batch_count} done. Blocks received: {len(blocks_received)}, highest: {highest_block}, elapsed: {elapsed:.1f}s")

            # Request next batch
            if highest_block < 3300:  # keep going
                next_start = highest_block + 1
                print(f"    Requesting blocks {next_start}..{next_start+499}")
                send_msg(sock, "GETB", write_i64(next_start))
            else:
                print(f"    Reached tip area — stopping")
                break

        elif cmd == "VERS":
            if payload and len(payload) >= 8:
                seed_h = read_i64(payload[:8])
                print(f"    Seed VERS: height={seed_h}")
                send_msg(sock, "VACK", b'')

        elif cmd == "VACK":
            print(f"    VACK received")

        elif cmd == "PING":
            send_msg(sock, "PONG", b'')

        else:
            print(f"    Unknown cmd: {cmd} ({len(payload) if payload else 0}B)")

    sock.close()
    elapsed = time.time() - start_time

    # Report
    print(f"\n{'=' * 60}")
    print(f"SYNC SIMULATION REPORT")
    print(f"{'=' * 60}")
    print(f"Blocks received: {len(blocks_received)}")
    print(f"Highest block:   {highest_block}")
    print(f"Batches:         {batch_count}")
    print(f"Elapsed:         {elapsed:.1f}s")
    print(f"Speed:           {len(blocks_received)/max(elapsed,1):.1f} blocks/sec")

    # Check critical boundaries
    print(f"\nCRITICAL CHECKS:")

    boundaries = [1, 500, 1000, 1500, 2000, 2500, 2501, 2502, 3000, 3100, 3200]
    for h in boundaries:
        if h in blocks_received:
            b = blocks_received[h]
            status = "OK" if b['has_tx'] else "MISSING TX"
            print(f"  Block #{h}: {status} ({b['size']}B)")
        elif h <= highest_block:
            print(f"  Block #{h}: MISSING (not received)")
        else:
            print(f"  Block #{h}: not reached yet")

    # Verdict
    print(f"\nVERDICT:")
    if 2501 in blocks_received:
        print(f"  PASS — Block #2501 received successfully")
        if highest_block >= 3200:
            print(f"  PASS — Synced to {highest_block} (near tip)")
            print(f"  *** SYNC TEST PASSED ***")
            return True
        else:
            print(f"  PARTIAL — Passed 2501 but only reached {highest_block}")
            return True  # still passed the critical test
    else:
        if highest_block >= 2500:
            print(f"  FAIL — Synced to {highest_block} but block #2501 NOT received")
            print(f"  *** THIS IS THE BUG — blocks after 2500 are not delivered ***")
        else:
            print(f"  FAIL — Only reached block {highest_block}")
        return False

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    success = test_sync(host, port)
    sys.exit(0 if success else 1)
