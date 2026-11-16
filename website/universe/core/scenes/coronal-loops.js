/* SOST Universe scene module: coronal-loops (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("coronal-loops", {
 "p": " if(kind<=.92){ vec3 q; float RS=7.; if(kind<.40){ float a=(a_s.x-.5)*1.1, b=(a_s.y-.5)*.7; vec3 n=normalize(vec3(sin(a),cos(a)*cos(b),sin(b))); q=n*RS-vec3(0.,RS+1.4,0.); float gr=.5+.5*sin(a*90.+u_t*.3)*sin(b*85.-u_t*.2); col=mix(u_col[6],u_col[5],gr)*.9; alpha=.10+.08*gr; sz=1.; } else { float k=floor(a_s.x*18.); float hh=fract(sin(k*12.9898)*43758.5); float x0=(k/17.-.5)*4.4; float hw=.25+.5*hh; float H=(.6+1.4*hh)*(1.+.08*sin(u_t*.6+k)); float s=a_s.y; float an=s*3.1416; q=vec3(x0+hw*cos(an)*.6,-1.4+H*sin(an),(hh-.5)*1.6+hw*cos(an)); float fl=pow(.5+.5*sin(s*12.-u_t*2.5+k),5.); q+=(vec3(fract(a_s.z*7.),fract(a_s.z*13.),fract(a_s.z*3.))-.5)*.04; col=mix(u_col[6],mix(u_col[5],u_col[3],hh),sin(an))*1.15; alpha=(.16+.30*fl)*(1.-.3*sin(an)); sz=.95; } p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.15); }",
 "l": " { float k=mod(cid,18.); float hh=fract(sin(k*12.9898)*43758.5); float x0=(k/17.-.5)*4.4; float hw=.25+.5*hh+(j1-.5)*.06; float H=(.6+1.4*hh)*(1.+.08*sin(u_t*.6+k)); float an=u*3.1416; p=rotX(rotY(vec3(x0+hw*cos(an)*.6,-1.4+H*sin(an),(hh-.5)*1.6+hw*cos(an)),-u_yaw*.5),-u_tilt+.15); col=mix(u_col[6],u_col[5],sin(an))*.7; }",
 "la": 1.0,
 "rc": "vec3(0.)",
 "rad": 0
});
