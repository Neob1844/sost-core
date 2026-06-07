#!/usr/bin/env python3
# SOST x GeaSpirit promo PRO — titles + transparent logos + fusion splash.
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
W="/tmp/gxvideo"; PNG=os.path.join(W,"png"); os.makedirs(PNG,exist_ok=True)
FB="/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
FR="/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
GOLD=(245,197,66); GREEN=(70,210,150); RED=(255,72,80); WHITE=(245,245,245); GREY=(170,178,188)

def transp(img, mode, thr):
    img=img.convert("RGBA"); px=img.load(); w,h=img.size
    for y in range(h):
        for x in range(w):
            r,g,b,a=px[x,y]
            if mode=="dark" and max(r,g,b)<thr: px[x,y]=(r,g,b,0)
            elif mode=="light" and min(r,g,b)>thr: px[x,y]=(r,g,b,0)
    return img

# --- transparent logos ---
sost=transp(Image.open(W+"/sost-logo.png"),"dark",46)
sost.save(W+"/sost_t.png")
gea=transp(Image.open(W+"/geaspirit-logo.png"),"light",234)
gea.save(W+"/gea_t.png")

def fit(path,text,size,maxw,dr):
    f=ImageFont.truetype(path,size)
    while size>18:
        if dr.textlength(text,font=f)<=maxw: break
        size-=2; f=ImageFont.truetype(path,size)
    return f
def ctext(dr,cy,y,text,font,fill,shadow=True):
    w=dr.textlength(text,font=font)
    if shadow: dr.text((cy-w/2+2,y+2),text,font=font,fill=(0,0,0,150))
    dr.text((cy-w/2,y),text,font=font,fill=fill)

def bg_gradient(finale=False,full=False):
    g=Image.new("RGBA",(1920,1080)); d=ImageDraw.Draw(g)
    for y in range(1080):
        t=y/1080; r=int(10-6*t); gg=int(13-8*t); b=int(18-10*t)
        d.line([(0,y),(1920,y)],fill=(max(r,3),max(gg,4),max(b,6),255))
    # radial glow
    glow=Image.new("RGBA",(1920,1080),(0,0,0,0)); gd=ImageDraw.Draw(glow)
    gd.ellipse([460,40,1460,820],fill=(40,60,80,70))
    glow=glow.filter(ImageFilter.GaussianBlur(160))
    return Image.alpha_composite(g,glow)

# ---------- SPLASH (logos + fusion message) ----------
sp=bg_gradient(); dr=ImageDraw.Draw(sp)
LS=300
s2=sost.resize((LS,LS)); g2=gea.resize((LS,LS))
cy=300
sp.alpha_composite(s2,(560-LS//2,cy-LS//2))
sp.alpha_composite(g2,(1360-LS//2,cy-LS//2))
fx=ImageFont.truetype(FB,150); ctext(dr,960,cy-95,"×",fx,WHITE)
fname=ImageFont.truetype(FB,40)
ctext(dr,560,cy+LS//2-6,"SOST PROTOCOL",fname,RED)
ctext(dr,1360,cy+LS//2-6,"GEASPIRIT",fname,GREEN)
ft=fit(FB,"FUSING TWO WORLDS",70,1600,dr); ctext(dr,960,560,"FUSING TWO WORLDS",ft,WHITE)
# accent rule
dr.rectangle([810,548,1110,553],fill=GOLD+(230,))
f1=ImageFont.truetype(FR,42); ctext(dr,960,650,"sovereign money  +  mineral intelligence",f1,GOLD)
f2=ImageFont.truetype(FR,34); ctext(dr,960,720,"GeaSpirit finds the value · SOST anchors the trust on-chain",f2,GREY)
f3=ImageFont.truetype(FR,30); ctext(dr,960,790,"the on-chain trust layer for real-world mining",f3,GREY)
sp.convert("RGB").save(W+"/splash.png")

# ---------- title overlays (lower-third) ----------
# SRC, IN, COLOR, HEADLINE, SUBTITLE  (Mother Board & Bitcoin clips replaced)
SEGS=[
("Drone Shot - 15241.mp4",8,GOLD,"THE EARTH HOLDS TRILLIONS","in minerals the world has forgotten"),
("Digging - 27151.mp4",2,GOLD,"THOUSANDS OF MINES","abandoned   ·   historic   ·   overlooked"),
("Gold Wash - 35565.mp4",3,GOLD,"VALUE LEFT BEHIND","a second chance, waiting to be found"),
("Nature - 35264.mp4",0,GREEN,"GEASPIRIT","mineral intelligence platform"),
("Digital Gold - 43610.mp4",0,GREEN,"OPEN DATA  +  SATELLITE","remote sensing · spectral signatures · change detection"),
("Bridge - 61458.mp4",0,GREEN,"A SCORE FOR EVERY ASSET","transparent · honest · second-chance first"),
("Bolts - 73875.mp4",0,RED,"SOST PROTOCOL","a sovereign Layer-1 blockchain"),
("Gears - 822.mp4",0,RED,"CONVERGENCEX  PROOF-OF-WORK","real computation, real value"),
("Computer - 47217.mp4",8,RED,"SOVEREIGN BY DESIGN","no pools · no gatekeepers · no central mint"),
("Coal Mining - 40030.mp4",0,GREEN,"GEASPIRIT FINDS THE VALUE","where to look · what is undervalued"),
("Macbook - 3576.mp4",4,RED,"SOST ANCHORS THE TRUST","intelligence made verifiable on-chain"),
("Highway - 62368.mp4",0,GOLD,"FROM THE EARTH TO THE CHAIN","mineral intelligence meets sovereign money"),
("Gold - 69279.mp4",0,WHITE,"SOST  ×  GEASPIRIT","sostcore.com      ·      geaspirit.com"),
]
man=open(W+"/manifest.txt","w")
for i,(src,inp,col,head,sub) in enumerate(SEGS):
    fin=(i==len(SEGS)-1)
    img=Image.new("RGBA",(1920,1080),(0,0,0,0))
    grad=Image.new("RGBA",(1920,1080),(0,0,0,0)); gd=ImageDraw.Draw(grad)
    top=640 if fin else 700
    for y in range(top,1080):
        a=int(195*((y-top)/(1080-top))**1.15); gd.line([(0,y),(1920,y)],fill=(6,8,10,a))
    img=Image.alpha_composite(img,grad); dr=ImageDraw.Draw(img)
    hs=92 if fin else 68
    fh=fit(FB,head,hs,1740,dr); fs=fit(FR,sub,42,1740,dr)
    hy=792 if fin else 820
    hw=dr.textlength(head,font=fh)
    rw=min(hw,520); rx=(1920-rw)/2
    dr.rectangle([rx,hy-18,rx+rw,hy-13],fill=col+(220,))
    ctext(dr,960,hy,head,fh,col)
    ctext(dr,960,hy+hs+24,sub,fs,WHITE,shadow=False)
    img.save(os.path.join(PNG,f"t{i}.png"))
    man.write(f"{src}:::{inp}\n")
man.close()
print("OK: logos transp, splash, %d titles + manifest"%len(SEGS))
