#!/usr/bin/env python3
# Generate title PNGs (1920x1080 RGBA) + manifest for the SOST x GeaSpirit promo.
import os
from PIL import Image, ImageDraw, ImageFont

W=os.path.expanduser("/tmp/gxvideo"); PNG=os.path.join(W,"png"); os.makedirs(PNG,exist_ok=True)
FB="/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
FR="/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
GOLD=(245,197,66); GREEN=(53,214,160); RED=(255,72,80); WHITE=(245,245,245)

# SRC, IN, COLOR, HEADLINE, SUBTITLE
SEGS=[
("Drone Shot - 15241.mp4",8,GOLD,"THE EARTH HOLDS TRILLIONS","in minerals the world has forgotten"),
("Digging - 27151.mp4",2,GOLD,"THOUSANDS OF MINES","abandoned   ·   historic   ·   overlooked"),
("Gold Wash - 35565.mp4",3,GOLD,"VALUE LEFT BEHIND","a second chance, waiting to be found"),
("Nature - 35264.mp4",0,GREEN,"GEASPIRIT","mineral intelligence platform"),
("Digital Gold - 43610.mp4",0,GREEN,"OPEN DATA  +  SATELLITE","remote sensing · spectral signatures · change detection"),
("Mother Board - 47221.mp4",8,GREEN,"A SCORE FOR EVERY ASSET","transparent · honest · second-chance first"),
("Bitcoin - 13476.mp4",0,RED,"SOST PROTOCOL","a sovereign Layer-1 blockchain"),
("Gears - 822.mp4",0,RED,"CONVERGENCEX  PROOF-OF-WORK","real computation, real value"),
("Computer - 47217.mp4",8,RED,"SOVEREIGN BY DESIGN","no pools · no gatekeepers · no central mint"),
("Coal Mining - 40030.mp4",0,GREEN,"GEASPIRIT FINDS THE VALUE","where to look · what is undervalued"),
("Macbook - 3576.mp4",4,RED,"SOST ANCHORS THE TRUST","intelligence made verifiable on-chain"),
("Highway - 62368.mp4",0,GOLD,"FROM THE EARTH TO THE CHAIN","mineral intelligence meets sovereign money"),
("Gold - 69279.mp4",0,WHITE,"SOST  ×  GEASPIRIT","sostcore.com      ·      geaspirit.com"),
]

def fit(path,text,size,maxw,dr):
    f=ImageFont.truetype(path,size)
    while size>20:
        w=dr.textlength(text,font=f)
        if w<=maxw: break
        size-=2; f=ImageFont.truetype(path,size)
    return f

def make(i,col,head,sub,finale=False):
    img=Image.new("RGBA",(1920,1080),(0,0,0,0)); dr=ImageDraw.Draw(img)
    # bottom gradient scrim
    grad=Image.new("RGBA",(1920,1080),(0,0,0,0)); gd=ImageDraw.Draw(grad)
    top=620 if finale else 700
    for y in range(top,1080):
        a=int(190*((y-top)/(1080-top))**1.15)
        gd.line([(0,y),(1920,y)],fill=(6,8,10,a))
    img=Image.alpha_composite(img,grad); dr=ImageDraw.Draw(img)
    hs=92 if finale else 68
    fh=fit(FB,head,hs,1740,dr); fs=fit(FR,sub,42,1740,dr)
    hy=820 if not finale else 792
    hw=dr.textlength(head,font=fh)
    # subtle shadow
    dr.text(((1920-hw)/2+2,hy+2),head,font=fh,fill=(0,0,0,160))
    dr.text(((1920-hw)/2,hy),head,font=fh,fill=col+(255,))
    sw=dr.textlength(sub,font=fs); sy=hy+hs+24
    dr.text(((1920-sw)/2,sy),sub,font=fs,fill=WHITE+(235,))
    # accent rule under headline
    rw=min(hw,520); rx=(1920-rw)/2
    dr.rectangle([rx,hy-18,rx+rw,hy-13],fill=col+(220,))
    img.save(os.path.join(PNG,f"t{i}.png"))

man=open(os.path.join(W,"manifest.txt"),"w")
for i,(src,inp,col,head,sub) in enumerate(SEGS):
    make(i,col,head,sub,finale=(i==len(SEGS)-1))
    man.write(f"{src}:::{inp}\n")
man.close()
print(f"generated {len(SEGS)} title PNGs + manifest")
