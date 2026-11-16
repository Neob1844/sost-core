/* SOST Universe scene module: void-foam (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("void-foam", {
 "p": " if(kind<=.92){ vec3 c=(vec3(a_s.x,a_s.y,a_s.z)-.5)*vec3(6.,3.8,.9); vec3 g=c*1.1+vec3(0.,0.,u_t*.05); vec3 ip=floor(g); vec3 fp=fract(g); float d1=9.,d2=9.; for(int i=-1;i<=1;i++)for(int j=-1;j<=1;j++)for(int k=-1;k<=1;k++){ vec3 o=vec3(float(i),float(j),float(k)); vec3 h=fract(sin(vec3(dot(ip+o,vec3(127.1,311.7,74.7)),dot(ip+o,vec3(269.5,183.3,246.1)),dot(ip+o,vec3(113.5,271.9,124.6))))*43758.5); float dd=length(o+h-fp); if(dd<d1){d2=d1;d1=dd;}else if(dd<d2){d2=dd;} } float wall=exp(-pow((d2-d1)*13.,2.)); float edge=exp(-pow((d2-d1)*30.,2.)); vec3 q=c; col=mix(u_col[2],mix(u_col[3],u_col[5],edge),wall)*1.1; alpha=.004+.42*wall+.4*edge; sz=1.; p=rotX(rotY(q,-u_yaw*.6),-u_tilt+.1); }",
 "l": " { p=vec3(0.,0.,-80.); col=vec3(0.); }",
 "la": 0.8,
 "rc": "vec3(0.)",
 "rad": 0
});
