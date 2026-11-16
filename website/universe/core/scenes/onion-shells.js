/* SOST Universe scene module: onion-shells (metadata and card: core/u-scenes.js). Loaded on demand by core/u-core.js. */
SOSTU.sceneLib.register("onion-shells", {
 "p": " if(kind<=.92){ float T=fract(u_t/16.); float col_=smoothstep(.8,.86,T); float fl=exp(-pow((T-.87)*40.,2.)); float r=pow(a_s.x,.6)*1.85; float an=a_s.y*6.2832+u_t*.05; float L=r>1.6?0.:r>1.25?1.:r>.95?2.:r>.7?3.:r>.48?4.:r>.28?5.:6.; float cell=sin(an*(10.+L*3.)+u_t*(.6+.2*L)*(mod(L,2.)<.5?1.:-1.))*sin((r-L*.2)*30.); float rr=r*(L>5.5?(1.-.7*col_):1.); rr+=.012*cell; vec3 q=vec3(rr*cos(an),rr*sin(an),(a_s.z-.5)*.08*(1.-r/1.9)); vec3 cc=L<.5?u_col[2]:L<1.5?u_col[3]:L<2.5?u_col[4]:L<3.5?u_col[5]:L<4.5?u_col[6]:L<5.5?u_col[1]:vec3(.9,.85,.8); col=cc*(1.+.25*cell)*1.05; alpha=(.22+.14*cell)*(1.-.5*step(5.5,L)); sz=1.05; float sh=fl*exp(-pow((r-(T-.86)*30.)*3.,2.)); col=mix(col,u_col[5],min(sh*3.,1.)); alpha+=.3*sh; p=rotX(rotY(q,-u_yaw),-u_tilt); }",
 "l": " { float k=mod(cid,7.); float R=k<.5?1.6:k<1.5?1.25:k<2.5?.95:k<3.5?.7:k<4.5?.48:k<5.5?.28:.1; float an=u*6.2832; p=rotX(rotY(vec3(R*cos(an),R*sin(an),0.),-u_yaw),-u_tilt); col=vec3(.5,.55,.7)*.35; }",
 "la": 0.5,
 "rc": "vec3(0.)",
 "rad": 0
});
