/* SOST Universe scene module: merger-tree (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("merger-tree", {
 "p": " if(kind<=.92){ float L=floor(a_s.x*5.); float n=pow(2.,4.-L); float i=floor(fract(a_s.x*5.)*n); float y=-1.9+L*.95; float x=((i+.5)/n-.5)*4.6; float fl=fract(u_t*.12); float act=exp(-pow((fl*5.-L-.5)*1.4,2.)); vec3 q=vec3(x,y,0.)+(.04+.035*L)*pow(fract(a_s.w*13.),.4)*vec3(sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*cos(a_s.y*6.2832),2.*a_s.z-1.,sqrt(1.-(2.*a_s.z-1.)*(2.*a_s.z-1.))*sin(a_s.y*6.2832)); col=mix(u_col[2],u_col[5],L/4.)*(.8+act*.35); alpha=.08+.12*act; sz=.9+.3*act; p=rotX(rotY(q,-u_yaw*.4+.15*sin(u_t*.1)),-u_tilt+.05); }",
 "l": " { float k=mod(cid,30.); float L=k<16.?0.:k<24.?1.:k<28.?2.:3.; float base=L<.5?0.:L<1.5?16.:L<2.5?24.:28.; float i=k-base; float n=pow(2.,4.-L); float y0=-1.9+L*.95; float x0=((i+.5)/n-.5)*4.6; float x1=((floor(i/2.)+.5)/(n/2.)-.5)*4.6; float s=u; vec3 q=vec3(mix(x0,x1,smoothstep(0.,1.,s)),y0+.95*s,0.); float fl=fract(u_t*.12); p=rotX(rotY(q,-u_yaw*.4+.15*sin(u_t*.1)),-u_tilt+.05); col=mix(u_col[2],u_col[5],(L+s)/4.)*(.4+.6*exp(-pow((fl*5.-L-s-.5)*1.4,2.))); }",
 "la": 1.2,
 "rc": "vec3(0.)",
 "rad": 0
});
