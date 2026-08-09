#!/usr/bin/env python3
# SOST x GeaSpirit promo v4 — intense pulsing-glow splash, mining/nature titles,
# rainbow CONVERGENCEX, cinematic finale.
import os, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
W="/tmp/gxvideo"; PNG=W+"/png"; FR_DIR=W+"/splashfr"
os.makedirs(PNG,exist_ok=True); os.makedirs(FR_DIR,exist_ok=True)
FB="/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
FRG="/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
GOLD=(245,197,66); GREEN=(70,210,150); RED=(255,72,80); WHITE=(245,245,245); GREY=(170,178,188)
SOST_GLOW=(251,1,13); GEA_GLOW=(0,255,65)
RAIN=[(230,57,70),(245,158,11),(74,222,128),(34,211,238),(192,132,252),(230,57,70)]  # sostcore.com stops

def fit(path,text,size,maxw,dr):
    f=ImageFont.truetype(path,size)
    while size>16 and dr.textlength(text,font=f)>maxw: size-=2; f=ImageFont.truetype(path,size)
    return f
def ctext(dr,cx,y,text,font,fill,shadow=True):
    w=dr.textlength(text,font=font)
    if shadow: dr.text((cx-w/2+2,y+2),text,font=font,fill=(0,0,0,150))
    dr.text((cx-w/2,y),text,font=font,fill=fill)
def rounded(img,rad):
    m=Image.new("L",img.size,0); ImageDraw.Draw(m).rounded_rectangle([0,0,img.size[0],img.size[1]],rad,fill=255)
    out=img.convert("RGBA"); out.putalpha(m); return out
def badge(path,size,white_bg):
    SS=4; S=size*SS                      # supersample for clean rounded edges
    base=Image.new("RGBA",(S,S),(255,255,255,255) if white_bg else (8,8,8,255))
    lg=Image.open(path).convert("RGBA")
    if white_bg:
        pad=int(S*0.038); s=S-2*pad; lg=lg.resize((s,s),Image.LANCZOS); base.alpha_composite(lg,(pad,pad))  # GeaSpirit inner +10%
    else:
        lg=lg.resize((S,S),Image.LANCZOS); base.alpha_composite(lg,(0,0))
    m=Image.new("L",(S,S),0); ImageDraw.Draw(m).rounded_rectangle([0,0,S,S],int(S*0.20),fill=255)
    base.putalpha(m)
    return base.resize((size,size),Image.LANCZOS)
def glow_img(size,color,pad):
    big=size+2*pad
    c=Image.new("RGBA",(big,big),(0,0,0,0))
    ImageDraw.Draw(c).rounded_rectangle([pad,pad,pad+size,pad+size],int(size*0.20),fill=color+(255,))
    wide=c.filter(ImageFilter.GaussianBlur(pad*0.60))
    tight=c.filter(ImageFilter.GaussianBlur(pad*0.26))
    out=Image.alpha_composite(wide,tight)
    for _ in range(3): out=Image.alpha_composite(out,tight)   # intense core
    return out
def with_alpha(img,f):
    f=max(0.0,min(1.0,f)); r,g,b,a=img.split(); a=a.point(lambda v:int(v*f)); return Image.merge("RGBA",(r,g,b,a))
def bg_grad():
    g=Image.new("RGBA",(1920,1080)); d=ImageDraw.Draw(g)
    for y in range(1080):
        t=y/1080; d.line([(0,y),(1920,y)],fill=(max(int(11-6*t),3),max(int(14-8*t),4),max(int(20-11*t),6),255))
    glow=Image.new("RGBA",(1920,1080),(0,0,0,0))
    ImageDraw.Draw(glow).ellipse([460,30,1460,760],fill=(40,60,80,60))
    return Image.alpha_composite(g,glow.filter(ImageFilter.GaussianBlur(170)))
def grad_row(w):
    segs=len(RAIN)-1; out=[]
    for x in range(w):
        p=(x/max(w-1,1))*segs; i=min(int(p),segs-1); f=p-i; a=RAIN[i]; b=RAIN[i+1]
        out.append(tuple(int(a[k]+(b[k]-a[k])*f) for k in range(3)))
    return out
def rainbow_text(img,cx,y,text,font):
    dr=ImageDraw.Draw(img); tw=int(dr.textlength(text,font=font)); h=int(font.size*1.5)
    layer=Image.new("RGBA",(tw,h),(0,0,0,0)); ImageDraw.Draw(layer).text((0,0),text,font=font,fill=(255,255,255,255))
    alpha=layer.split()[3]; row=grad_row(tw)
    G=Image.new("RGB",(tw,h)); px=G.load()
    for x in range(tw):
        c=row[x]
        for yy in range(h): px[x,yy]=c
    G=G.convert("RGBA"); G.putalpha(alpha)
    sh=Image.new("RGBA",(tw,h),(0,0,0,0)); ImageDraw.Draw(sh).text((3,3),text,font=font,fill=(0,0,0,160))
    img.alpha_composite(sh,(int(cx-tw/2),int(y))); img.alpha_composite(G,(int(cx-tw/2),int(y)))
def rainbow_bar(img,x,y,w,h):
    row=grad_row(int(w)); G=Image.new("RGB",(int(w),int(h))); px=G.load()
    for i in range(int(w)):
        for yy in range(int(h)): px[i,yy]=row[i]
    img.alpha_composite(G.convert("RGBA"),(int(x),int(y)))

# ---------- animated SPLASH (intense pulsing glow) ----------
LS=290; PAD=130
sost_b=badge(W+"/sost-logo.png",LS,False); gea_b=badge(W+"/geaspirit-logo.png",LS,True)
badge(W+"/sost-logo.png",320,False).save(W+"/sostwm.png")  # corner watermark = SOST black rounded badge
glow_s=glow_img(LS,SOST_GLOW,PAD); glow_g=glow_img(LS,GEA_GLOW,PAD)
xS=560; xG=1360; cy=322
back=bg_grad(); dr=ImageDraw.Draw(back)
ctext(dr,960,cy-95,"×",ImageFont.truetype(FB,150),WHITE)
fn=ImageFont.truetype(FB,40)
ctext(dr,xS,cy+LS//2+12,"SOST PROTOCOL",fn,RED); ctext(dr,xG,cy+LS//2+12,"GEASPIRIT",fn,GREEN)
ft=fit(FB,"FUSING TWO WORLDS",70,1600,dr); ctext(dr,960,560,"FUSING TWO WORLDS",ft,WHITE)
dr.rectangle([810,548,1110,553],fill=GOLD+(230,))
ctext(dr,960,652,"verifiable on-chain trust  +  mineral intelligence",ImageFont.truetype(FRG,42),GOLD)
ctext(dr,960,722,"GeaSpirit finds the value · SOST anchors the trust on-chain",ImageFont.truetype(FRG,34),GREY)
ctext(dr,960,792,"the on-chain trust layer for real-world mining",ImageFont.truetype(FRG,30),GREY)
FPS=30; SPL=8.0; PER=2.4
n=int(SPL*FPS)
for i in range(n):
    t=i/FPS; ph=0.5+0.5*math.sin(2*math.pi*t/PER); fac=min(1.0,0.48+0.85*ph)
    fr=back.copy()
    ps=(xS-LS//2-PAD,cy-LS//2-PAD); pg=(xG-LS//2-PAD,cy-LS//2-PAD)
    gs=with_alpha(glow_s,fac); gg=with_alpha(glow_g,fac)
    for _ in range(2):    # composite for intensity (softened)
        fr.alpha_composite(gs,ps); fr.alpha_composite(gg,pg)
    fr.alpha_composite(sost_b,(xS-LS//2,cy-LS//2)); fr.alpha_composite(gea_b,(xG-LS//2,cy-LS//2))
    fr.convert("RGB").save(FR_DIR+f"/f{i:04d}.png")
print(f"splash frames: {n}")

# ---------- cinematic FINALE background ----------
fin=bg_grad(); dr=ImageDraw.Draw(fin)
ImageDraw.Draw(fin).rounded_rectangle([150,140,150+1620,140+375],18,fill=(0,0,0,255),outline=(60,70,82,255),width=2)
LB=128
sb=badge(W+"/sost-logo.png",LB,False); gb=badge(W+"/geaspirit-logo.png",LB,True)
fy=600; sx=960-220-LB//2; gx=960+220-LB//2
fgl_s=glow_img(LB,SOST_GLOW,80); fgl_g=glow_img(LB,GEA_GLOW,80)
for _ in range(4):
    fin.alpha_composite(fgl_s,(sx-80,fy-80)); fin.alpha_composite(fgl_g,(gx-80,fy-80))
fin.alpha_composite(sb,(sx,fy)); fin.alpha_composite(gb,(gx,fy))
ctext(dr,960,fy+LB//2-40,"×",ImageFont.truetype(FB,72),WHITE)
ctext(dr,960,fy+LB+30,"SOST  ×  GEASPIRIT",fit(FB,"SOST  ×  GEASPIRIT",78,1600,dr),WHITE)
ctext(dr,960,fy+LB+135,"sostcore.com      ·      geaspirit.com",ImageFont.truetype(FRG,40),GOLD)
fin.convert("RGB").save(W+"/finale_bg.png")

# ---------- titles + manifest ----------
# SRC, IN, DUR, COLOR, HEAD, SUB, MODE   (mode r = rainbow headline)
SEGS=[
("Drone Shot - 15241.mp4",8,8.5,GOLD,"THE EARTH HOLDS TRILLIONS","in minerals the world has forgotten","n"),
("Digging - 27151.mp4",2,8.5,GOLD,"THOUSANDS OF MINES","abandoned · historic · overlooked","n"),
("203503 (1080p).mp4",0,8.5,GOLD,"ACTIVE · ABANDONED · FORGOTTEN","every site holds a second story","n"),
("Gold Wash - 35565.mp4",3,8.5,GOLD,"VALUE LEFT BEHIND","a second chance, waiting to be found","n"),
("waterfall_-_44189 (540p).mp4",0,6,GREEN,"GEASPIRIT","mineral intelligence platform","n"),
("/tmp/gxvideo/seg5photos.mp4",0,22.1,GREEN,"OPEN DATA  +  SATELLITE","satellite · LiDAR · multispectral · spectral indices · 3D point clouds","n"),
("river_-_76937 (1080p).mp4",5,8.5,GREEN,"A SCORE FOR EVERY ASSET","transparent · honest · second-chance first","n"),
("Coal Mining - 40030.mp4",0,8.5,GREEN,"GEASPIRIT FINDS THE VALUE","where to look · what is undervalued","n"),
("galaxy_-_56995 (540p).mp4",0,8.5,RED,"SOST PROTOCOL","a sovereign Layer-1 blockchain","n"),
("/tmp/gxvideo/seg9logo.mp4",0,8.5,RED,"SOST PROOF-OF-WORK ENGINE","ConvergenceX — real computation, not a hash lottery","n"),
("/tmp/gxvideo/seg10coin.mp4",0,8.5,RED,"SOVEREIGN BY DESIGN","no pools · no gatekeepers · no central mint","n"),
("Nature - 35264.mp4",0,8.5,GOLD,"FROM THE EARTH TO THE CHAIN","mineral intelligence meets verifiable on-chain trust","n"),
("Touch - 6424.mp4",0,8,WHITE,"","","f"),
]
man=open(W+"/manifest3.txt","w")
for i,(src,inp,dur,col,head,sub,mode) in enumerate(SEGS):
    if mode in ("n","r"):
        img=Image.new("RGBA",(1920,1080),(0,0,0,0))
        grad=Image.new("RGBA",(1920,1080),(0,0,0,0)); gd=ImageDraw.Draw(grad)
        for y in range(700,1080):
            a=int(195*((y-700)/380)**1.15); gd.line([(0,y),(1920,y)],fill=(6,8,10,a))
        img=Image.alpha_composite(img,grad); dr=ImageDraw.Draw(img)
        rainbow=(mode=="r")
        fh=fit(FB,head,(80 if rainbow else 68),1740,dr); fs=fit(FRG,sub,42,1740,dr)
        hy=816; hw=dr.textlength(head,font=fh); rw=min(hw,520); rx=(1920-rw)/2
        if rainbow:
            rainbow_bar(img,rx,hy-18,rw,6); rainbow_text(img,960,hy,head,fh)
        else:
            dr.rectangle([rx,hy-18,rx+rw,hy-13],fill=col+(220,)); ctext(dr,960,hy,head,fh,col)
        ctext(dr,960,hy+fh.size+24,sub,fs,WHITE,shadow=False)
        img.save(PNG+f"/t{i}.png")
    man.write(f"{src}:::{inp}:::{dur}:::{mode}\n")
man.close()
print("OK gen3 v4: %d scenes"%len(SEGS))
