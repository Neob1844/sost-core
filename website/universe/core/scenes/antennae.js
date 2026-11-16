/* SOST Universe scene module: antennae (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("antennae", {
 "p": " if(kind<=.92){ float T=fract(u_t/26.+.45); float gi=step(.5,fract(a_s.y*2.)); float sg=gi>.5?1.:-1.; vec3 C=vec3(.42*sg,.10*sg,0.); if(kind<.40){ float s=a_s.x; float grow=.25+.75*smoothstep(0.,.45,T); float ss=.08+s*grow; float th0=gi>.5?-.35:2.79; float th=th0+ss*2.3; float rad=.30+ss*2.0; float w=(a_s.y+fract(a_s.y*5.71)+fract(a_s.y*2.33)-1.5)*(.025+.07*ss); vec2 dir=vec2(cos(th),sin(th)); vec2 nrm=vec2(-dir.y,dir.x); vec3 tp=vec3(C.xy+dir*rad+nrm*w,(fract(a_s.z*7.)-.5)*.10*(1.+ss)); p=tp; col=mix(mix(u_col[5],u_col[2],smoothstep(0.,.5,ss)),u_col[3],smoothstep(.5,1.,ss))*1.15; alpha=.30*(1.-.55*ss)*smoothstep(0.,.03,s); sz=1.; } else { float r=.04+.46*pow(a_s.x,.8); float th=a_s.z*6.2832; float arm=pow(.5+.5*cos(2.*(th-3.2*r)-u_t*.05*sg),3.); th+=u_t*.12/(r+.2)*sg; vec3 dsk=vec3(r*cos(th),r*sin(th)*.80,r*sin(th)*.25); dsk=gi>.5?rotY(rotX(dsk,-.35),-.5):rotY(dsk,.35); vec3 q=C+dsk; float ov=exp(-pow(length(q.xy)*3.2,2.)); float knot=step(.90,fract(a_s.z*37.+a_s.x*11.))*ov; col=mix(gi>.5?u_col[5]:u_col[6],u_col[2],smoothstep(.06,.4,r))*1.1; col=mix(col,u_col[1]*1.4,knot); col=mix(col,vec3(1.,.9,.7),exp(-r*25.)*.6); alpha=(.16+.22*arm+.35*exp(-r*12.)+.6*knot); sz=.9+1.2*knot; p=q; } alpha*=smoothstep(0.,.04,T)*smoothstep(1.,.95,T); p=rotY(rotX(p,.30),u_t*.025-.2); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0,
 "rc": "vec3(0.)",
 "rad": 0
});
