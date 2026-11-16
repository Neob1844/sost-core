/* SOST Universe scene module: alfven-waves (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("alfven-waves", {
 "p": " if(kind<=.92){ float x=(a_s.x-.5)*6.; float an=a_s.y*6.2832; float R=.45*(1.+(a_s.z-.5)*.1); float c1=fract(u_t*.09)*8.-4., c2=4.-fract(u_t*.07+.4)*8.; float dphi=1.4*exp(-pow((x-c1)/.7,2.))*sin((x-c1)*5.)+1.1*exp(-pow((x-c2)/.6,2.))*sin((x-c2)*6.); float ang=an+dphi+x*.15; vec3 q=vec3(x,R*cos(ang),R*sin(ang)); float e=abs(dphi); col=mix(u_col[2],mix(u_col[1],u_col[5],min(e,1.)),min(e*1.5,1.))*1.15; alpha=.10+.30*min(e,1.); sz=.9; p=rotX(rotY(q,.35),-.2); }",
 "l": " { float k=mod(cid,16.); float an=k/16.*6.2832; float x=(u-.5)*6.; float c1=fract(u_t*.09)*8.-4., c2=4.-fract(u_t*.07+.4)*8.; float dphi=1.4*exp(-pow((x-c1)/.7,2.))*sin((x-c1)*5.)+1.1*exp(-pow((x-c2)/.6,2.))*sin((x-c2)*6.); float ang=an+dphi+x*.15; p=rotX(rotY(vec3(x,.45*cos(ang),.45*sin(ang)),.35),-.2); col=mix(u_col[2],u_col[1],min(abs(dphi),1.))*.9; }",
 "la": 1.4,
 "rc": "vec3(0.)",
 "rad": 0
});
