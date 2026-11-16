/* SOST Universe scene module: inflation-genesis (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("inflation-genesis", {
 "p": " if(kind<=.92){ float T=fract(u_t/16.+.15); float gr=smoothstep(.04,.42,T); float R=.03+1.95*(exp(gr*4.)-1.)/(exp(4.)-1.); vec3 d=vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); float rr=pow(fract(a_s.w*13.),.33); float st=smoothstep(.38,.85,T); rr=mix(rr,.90+.10*rr,st*.8); vec3 q0=d*rr; float n=sin(q0.x*5.+q0.y*3.)*sin(q0.y*6.-q0.z*2.)*sin(q0.z*5.+q0.x*4.)+.5*sin(q0.x*11.)*sin(q0.y*13.)*sin(q0.z*9.); n=clamp(n,-1.,1.); vec3 q=q0*R*(1.+.06*n*st); vec3 hot=mix(u_col[6],u_col[5],smoothstep(.2,.9,n)); vec3 cold=mix(u_col[0],u_col[2],smoothstep(.2,.9,-n)); col=mix(vec3(1.,.85,.6),n>0.?hot:cold,smoothstep(.06,.35,T))*1.45; float flash=exp(-pow((T-.05)*18.,2.)); alpha=(.22+.80*st*smoothstep(.15,.75,abs(n))+.35*flash)*clamp(.05+R*.55,0.,1.)*smoothstep(1.,.93,T); sz=1.+.5*st*smoothstep(.5,.9,abs(n)); p=rotY(rotX(q,.35),u_t*.06); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
