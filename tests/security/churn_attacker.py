#!/usr/bin/env python3
# Connection churn: open and immediately close N connections, fast. Bounded per-socket timeout.
import socket,sys,time
host,port,n=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
ok=0
for _ in range(n):
    try:
        s=socket.socket(); s.settimeout(1.0); s.connect((host,port)); s.close(); ok+=1
    except OSError: pass
print(ok)
