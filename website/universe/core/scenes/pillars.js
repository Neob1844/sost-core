/* SOST Universe scene module: pillars (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("pillars", {
 "p": " if(kind<=.92){ vec3 q; vec3 Sd=normalize(vec3(.8+u_ptr.x*u_ptrA,1.,.4)); if(kind<.70){ float k=floor(a_s.x*3.); float x0=-1.3+k*1.25+.1*sin(k*3.); float H=k<.5?1.6:k<1.5?2.4:1.2; float y=-2.2+a_s.y*(H+2.2); float tp=(y+2.2)/(H+2.2); float R=(.55-.3*tp)*(1.+.25*sin(y*5.+k*2.)+.15*sin(y*11.+k)); float an=a_s.z*6.2832; float rr=R*pow(fract(a_s.w*13.),.35); vec3 n=vec3(cos(an),0.,sin(an)); float head=exp(-pow((tp-1.)*5.,2.)); q=vec3(x0,y,0.)+n*rr+vec3(0.,head*.25*rr,0.); float lit=clamp(dot(normalize(n+vec3(0.,head*1.5,0.)),Sd),0.,1.)*smoothstep(.75,1.,rr/R); float ev=fract(a_s.w*7.+u_t*.15)*lit; q+=Sd*ev*.25; col=mix(u_col[0]*.7,mix(u_col[1],u_col[5],lit),lit)*1.2; alpha=(.16+.55*lit)*(1.-ev*.6); sz=1.2; } else { vec3 g=vec3(a_s.x-.5,a_s.y-.5,a_s.z-.5)*vec3(7.,5.,2.); g.xy+=flow(g.xy*.6,u_t*.04)*.3; q=g+vec3(0.,0.,-1.2); col=mix(u_col[3],u_col[2],a_s.y)*1.; alpha=.09; sz=1.6; } p=rotX(rotY(q,-u_yaw*.6),-u_tilt); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
