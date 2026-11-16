/* SOST Universe scene module: polar-cap (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("polar-cap", {
 "p": " if(kind<=.92){ vec3 q; float RS=6.; if(kind<.40){ float a=(a_s.x-.5)*1.3, b=(a_s.y-.5)*.9; a=floor(a*60.)/60.+(fract(a_s.z*3.)<.5?0.:(fract(a_s.z*17.)-.5)/60.); vec3 n=normalize(vec3(sin(a),cos(a)*cos(b),sin(b))); q=n*RS-vec3(0.,RS+1.25,0.); float cap=exp(-pow(a/.12,2.)-pow(b/.12,2.)); col=mix(u_col[2]*.6,u_col[5],cap)*1.1; alpha=.12+.4*cap; sz=.9; } else { float col_=floor(a_s.x*40.); float hh=fract(sin(col_*12.9898)*43758.5); float x0=(hh-.5)*.55, z0=(fract(hh*7.13)-.5)*.55; float f=fract(a_s.y+u_t*(.35+.3*hh)); float on=step(.35,fract(sin(floor(u_t*1.5+hh*9.)*78.2+col_)*43758.5)); float y=-1.25+f*3.4; q=vec3(x0*(1.+f*f*2.5),y,z0*(1.+f*f*2.5))+vec3(fract(a_s.z*11.)-.5,0.,fract(a_s.z*5.7)-.5)*.02*(1.+f*3.); col=mix(u_col[5],mix(u_col[3],u_col[0],f),smoothstep(0.,.4,f))*1.2; alpha=on*.35*(1.-f*.8); sz=.9; } p=rotX(rotY(q,-u_yaw*.5),-u_tilt+.12); }",
 "l": " { float k=mod(cid,30.); float hh=fract(sin(k*12.9898)*43758.5); float x0=(hh-.5)*.55, z0=(fract(hh*7.13)-.5)*.55; float f=u; p=rotX(rotY(vec3(x0*(1.+f*f*2.5),-1.25+f*3.4,z0*(1.+f*f*2.5)),-u_yaw*.5),-u_tilt+.12); col=mix(u_col[3],u_col[0],u)*.5*(1.-u); }",
 "la": 1.1,
 "rc": "vec3(0.)",
 "rad": 0
});
