import sys
Q16_ONE=65536; MIN_BITSQ=65536; MAX_BITSQ=255*65536; TARGET=600; DT_MAX=86400; WINDOW=288
V12_HEIGHT=7350; V11_H=7000
# V11 slingshot: threshold 1800s, drop 1250bps
def v12_tier(cur):
    if cur>10800: return 5
    if cur>7200: return 4
    if cur>3600: return 3
    if cur>1800: return 2
    if cur>1200: return 1
    return 0
V12_DROP={5:5000,4:3750,3:2500,2:1250,1:650}

def model(kind,p1,p2,prev,height,elapsed):
    # rebuild chain times exactly as harness: N=289, interval to block i = p1 (kind0) or (p1 if i%2==1 else p2)
    N=289; t=1000000; times=[t]
    for i in range(1,N):
        iv = p1 if kind==0 else (p1 if (i%2==1) else p2)
        t+=iv; times.append(t)
    prev_bitsq = prev if prev else 765730
    # V6PP path requires chain.size()>=10 (289 ok). window=min(289,288)=288; start=289-288=1
    window=min(N,WINDOW); start=N-window
    total=0; count=0
    for i in range(start+1, N):  # i in [2,288]
        dt = times[i]-times[i-1]
        dt = max(1, min(DT_MAX, dt))
        total+=dt; count+=1
    avg = (total//count) if count>0 else TARGET
    deviation = avg - TARGET
    abs_dev = -deviation if deviation<0 else deviation
    delta=0
    # height>=5270 tier set
    if abs_dev<=15: max_delta=0
    elif abs_dev<=60: max_delta=prev_bitsq//200
    elif abs_dev<=120: max_delta=prev_bitsq//100
    elif abs_dev<=240: max_delta=prev_bitsq//50
    else: max_delta=prev_bitsq//33
    if max_delta<1 and abs_dev>15: max_delta=1
    deadband=15
    if max_delta>0 and abs_dev>deadband:
        excess=abs_dev-deadband
        raw_delta=(prev_bitsq*excess)//(TARGET*4)
        if deviation<0: delta=min(raw_delta,max_delta)
        else: delta=-min(raw_delta,max_delta)
    result=prev_bitsq+delta
    result=max(MIN_BITSQ,min(MAX_BITSQ,result))
    now = times[-1]+elapsed  # elapsed = now - last.time
    # slingshot
    if height>=V12_HEIGHT and now>0:
        cur=now-times[-1]
        t_=v12_tier(cur); drop=V12_DROP.get(t_,0)
        if drop>0:
            r=(result*(10000-drop))//10000
            if r<MIN_BITSQ: r=MIN_BITSQ
            result=r
    elif height>=V11_H and height<V12_HEIGHT and now>0 and N>=2:
        prev_elapsed=times[-1]-times[-2]
        current_elapsed=now-times[-1]
        if prev_elapsed>1800 and current_elapsed>TARGET:
            r=(result*(10000-1250))//10000
            if r<MIN_BITSQ: r=MIN_BITSQ
            result=r
    return result

f=open('dump.csv'); hdr=f.readline()
n=0; mism=0; samples=[]
for line in f:
    kind,p1,p2,prev,height,elapsed,result=map(int,line.strip().split(','))
    got=model(kind,p1,p2,prev,height,elapsed)
    n+=1
    if got!=result:
        mism+=1
        if len(samples)<12: samples.append((kind,p1,p2,prev,height,elapsed,result,got))
print(f"vectores comparados: {n}")
print(f"divergencias: {mism}")
if mism:
    print("kind,p1,p2,prev,height,elapsed  C++=result  PY=got")
    for s in samples: print(f"  {s[:6]}  C++={s[6]}  PY={s[7]}")
else:
    print("RESULT: BIT-EXACT PASS — 0 divergencias en todo el espacio de vectores del régimen activo (>=5270 + slingshot V11/V12)")
