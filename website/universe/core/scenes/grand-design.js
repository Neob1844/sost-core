/* SOST Universe scene module: grand-design (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("grand-design", {
 "p": " if(kind<=.92){ float pit=.36; float pat=u_t*.035; if(kind<.07){ float r=.42*pow(a_s.x,1.6); float cz=2.*a_s.z-1.; float s0=sqrt(1.-cz*cz); p=vec3(r*s0*cos(a_s.y*6.2832),r*cz*.55,r*s0*sin(a_s.y*6.2832)); col=mix(u_col[5],u_col[6],a_s.x)*.9; alpha=.10; sz=1.1; } else if(kind<.30){ float r=.3+2.6*sqrt(a_s.x); float th=a_s.y*6.2832+u_t*.25/(r+.4); p=vec3(r*cos(th),(a_s.z-.5)*.05,r*sin(th)); col=mix(u_col[2],u_col[5],.3)*.7; alpha=.10; sz=.8; } else { float r=.35+2.55*pow(a_s.x,.85); float g=(a_s.z+fract(a_s.z*7.31)+fract(a_s.z*3.17)-1.5)*.55; float m=step(.5,fract(a_s.y*2.)); float th=m*3.1416+log(r)/tan(pit)+g*(.35+.1*r)+pat; p=vec3(r*cos(th),(fract(a_s.y*91.7)-.5)*.06,r*sin(th)); float lane=smoothstep(-.34,-.24,g)*(1.-smoothstep(-.16,-.06,g)); float hii=step(.18,g)*step(fract(a_s.y*13.7+floor(r*9.)*.31),.25); col=mix(u_col[2],u_col[3],smoothstep(.5,2.5,r)); col=mix(col,u_col[1]*1.3,hii); alpha=(.30+.25*hii)*(1.-.92*lane); sz=.9+.7*hii; } p=rotX(p,.62); p=rotY(p,u_t*.02); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
