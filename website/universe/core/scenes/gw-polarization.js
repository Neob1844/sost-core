/* SOST Universe scene module: gw-polarization (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("gw-polarization", {
 "p": " if(kind<=.92){ float k=floor(a_s.x*3.); float an=a_s.y*6.2832; float ph=u_t*1.6-k*.9; float pl=mod(floor(u_t/10.),2.); float hp=pl<.5?cos(ph):0., hx=pl<.5?0.:cos(ph); vec2 v=vec2(cos(an),sin(an))*.80; vec2 d=vec2(v.x*hp+v.y*hx,-v.y*hp+v.x*hx)*.28; vec3 q=vec3(v+d,(k-1.)*-1.25); q.xy*=1.+.015*(fract(a_s.z*7.)-.5); float ring=fract(a_s.w*3.)<.88?1.:0.; if(ring<.5){ q=vec3(0.,0.,(a_s.z-.5)*4.); } float fb=fract(a_s.y*12.); float bead=step(abs(fb-.5),.03); vec3 rc=k<.5?u_col[3]:k<1.5?u_col[1]:u_col[4]; col=mix(rc,vec3(1.),.15*bead)*1.15; col=mix(col,u_col[5],ring<.5?1.:0.); alpha=ring>.5?(.13+.07*abs(cos(ph))+.45*bead):.05; sz=ring>.5?.8+1.8*bead:1.; p=rotX(rotY(q,-u_yaw*.5+.55),-u_tilt+.35); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
