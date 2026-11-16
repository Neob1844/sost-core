/* SOST Universe scene module: milky-way-inside (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("milky-way-inside", {
 "p": " if(kind<=.92){ float lon=(a_s.x-.5)*3.3+u_t*.015+u_ptr.x*u_ptrA*.4; float g=(a_s.y+fract(a_s.y*7.3)+fract(a_s.y*3.1)-1.5); float bulge=exp(-lon*lon*3.); float lat=g*(.07+.16*bulge)+.05*sin(lon*2.3); if(kind<.16){ lat=(a_s.y-.5)*2.6; } float rift=step(abs(lat-.02*sin(lon*7.)-.01),.016+.022*bulge)*step(abs(lon),1.15)*step(.16,kind); float blob=step(.84,.5+.5*sin(lon*9.+1.)*sin(lat*40.))*step(.16,kind); float hii=step(.982,fract(a_s.z*53.+a_s.x*7.))*step(.16,kind)*step(abs(lat),.09); vec3 dir=normalize(vec3(sin(lon),lat,-cos(lon))); float tl=.5; dir=vec3(dir.x*cos(tl)-dir.y*sin(tl),dir.x*sin(tl)+dir.y*cos(tl),dir.z); vec3 v=vec3(0.,0.,4.6)+dir*9.; p=rotX(rotY(v,-u_yaw),-u_tilt); vec3 dc=mix(mix(u_col[2],u_col[0],fract(a_s.z*3.)),vec3(.85,.9,1.),.25); col=kind<.16?mix(u_col[int(band)],vec3(1.),.4):mix(dc,mix(u_col[5],u_col[6],.35),bulge)*1.35; col=mix(col,u_col[1]*1.5,hii); alpha=(kind<.16?.75*step(.7,fract(a_s.z*11.)):.55+.40*bulge)*(1.-.95*rift)*(1.-.6*blob)+.6*hii; sz=kind<.16?1.4+1.6*step(.97,fract(a_s.z*29.)):2.0+.8*bulge+2.*hii; }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
