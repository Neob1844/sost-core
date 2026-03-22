/* SOST 50 CRT Effects Engine — each effect 2s, random per click */

var CRT_EFFECTS=[
// === CAT 1: CRT CLASSIC (1-10) ===
function(b,d){b.style.transition='transform 2s ease-in,filter 2s';b.style.transform='scaleY(.003)';b.style.filter='brightness(3)';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,filter 2s';b.style.transform='scaleX(.003)';b.style.filter='brightness(2)';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,filter 2s';b.style.transform='scale(.003)';b.style.filter='brightness(4)';setTimeout(d,2000)},
function(b,d){var n=0,f=setInterval(function(){b.style.opacity=b.style.opacity==='0'?'1':'0';if(++n>8){clearInterval(f);b.style.transition='transform 1s ease-in';b.style.transform='scaleY(.003)';b.style.filter='brightness(3)';setTimeout(d,1000)}},100)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;z-index:999999;pointer-events:none';document.body.appendChild(ov);var n=0,iv=setInterval(function(){var c=document.createElement('canvas');c.width=80;c.height=50;var x=c.getContext('2d'),im=x.createImageData(80,50);for(var i=0;i<im.data.length;i+=4){var v=Math.random()*255;im.data[i]=im.data[i+1]=im.data[i+2]=v;im.data[i+3]=140}x.putImageData(im,0,0);ov.style.background='url('+c.toDataURL()+')';ov.style.backgroundSize='cover';if(++n>20){clearInterval(iv);ov.remove();b.style.opacity='0';setTimeout(d,300)}},80)},
function(b,d){var l=document.createElement('div');l.style.cssText='position:fixed;left:0;width:100vw;height:3px;background:#fff;z-index:999999;top:0;transition:top 2s linear;box-shadow:0 0 20px #fff';document.body.appendChild(l);requestAnimationFrame(function(){l.style.top='100vh'});b.style.transition='filter 2s';b.style.filter='brightness(0)';setTimeout(function(){l.remove();d()},2000)},
function(b,d){b.style.transition='transform 2s ease-in,border-radius 2s,filter 2s';b.style.transform='scale(.01)';b.style.borderRadius='50%';b.style.filter='brightness(2) blur(5px)';b.style.overflow='hidden';setTimeout(d,2000)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;z-index:999999;pointer-events:none;background:repeating-linear-gradient(0deg,transparent 0px,transparent 4px,rgba(0,0,0,.8) 4px,rgba(0,0,0,.8) 8px)';document.body.appendChild(ov);b.style.transition='filter 2s';b.style.filter='brightness(0)';setTimeout(function(){ov.remove();d()},2000)},
function(b,d){var bl=0,iv=setInterval(function(){bl+=.8;b.style.filter='blur('+bl+'px) brightness('+(1+bl*.04)+')';if(bl>=20){clearInterval(iv);b.style.opacity='0';setTimeout(d,300)}},70)},
function(b,d){b.style.transition='transform 1s ease-in,filter 1s';b.style.transform='scaleY(.003)';b.style.filter='brightness(5)';setTimeout(function(){b.style.transition='transform .8s,filter .8s';b.style.transform='scaleY(0) scaleX(0)';b.style.filter='brightness(0)';setTimeout(d,800)},1000)},

// === CAT 2: PIP-BOY / FALLOUT (11-20) ===
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;z-index:999999;background:rgba(0,255,100,.3);pointer-events:none';document.body.appendChild(ov);b.style.transition='filter 2s';b.style.filter='sepia(1) saturate(5) hue-rotate(70deg) brightness(0)';setTimeout(function(){ov.remove();d()},2000)},
function(b,d){var n=0,iv=setInterval(function(){b.style.transform='translate('+(Math.random()*30-15)+'px,'+(Math.random()*20-10)+'px)';b.style.filter='hue-rotate('+Math.random()*360+'deg)';if(++n>25){clearInterval(iv);b.style.opacity='0';b.style.transform='';setTimeout(d,200)}},70)},
function(b,d){b.style.transition='transform 2s ease-in';b.style.transform='translateY(-120vh)';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in';b.style.transform='translateY(120vh)';setTimeout(d,2000)},
function(b,d){b.style.transition='filter 1.5s';b.style.filter='sepia(1) saturate(10) hue-rotate(70deg) brightness(.3)';setTimeout(function(){b.style.transition='filter .5s';b.style.filter='brightness(0)';setTimeout(d,500)},1500)},
function(b,d){var s=0,iv=setInterval(function(){s+=1.5;b.style.filter='blur('+(s/4)+'px) contrast('+(1+s*.1)+')';if(s>30){clearInterval(iv);b.style.opacity='0';setTimeout(d,300)}},55)},
function(b,d){var n=0,iv=setInterval(function(){b.style.transform='translateX('+(Math.random()*20-10)+'px) skewX('+(Math.random()*5-2.5)+'deg)';b.style.filter='saturate('+Math.random()*3+') brightness('+(0.5+Math.random())+')';if(++n>25){clearInterval(iv);b.style.opacity='0';b.style.transform='';setTimeout(d,200)}},70)},
function(b,d){b.style.transition='filter 2s,opacity 2s';b.style.filter='sepia(1) hue-rotate(90deg) contrast(2) brightness(.5)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){var n=0,iv=setInterval(function(){b.style.clipPath='inset('+Math.random()*50+'% 0 '+Math.random()*50+'% 0)';b.style.filter='brightness('+(0.3+Math.random()*2)+')';if(++n>25){clearInterval(iv);b.style.clipPath='';b.style.opacity='0';setTimeout(d,200)}},70)},
function(b,d){b.style.transition='filter .4s';b.style.filter='brightness(5)';setTimeout(function(){b.style.transition='filter 1.4s';b.style.filter='brightness(0)';setTimeout(d,1400)},400)},

// === CAT 3: TERMINAL / HACKER (21-30) ===
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;top:0;left:0;width:100vw;height:0;background:#000;z-index:999999;transition:height 2s ease-in';document.body.appendChild(ov);requestAnimationFrame(function(){ov.style.height='100vh'});setTimeout(function(){b.style.opacity='0';ov.remove();d()},2000)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;top:0;left:0;width:0;height:100vh;background:#000;z-index:999999;transition:width 2s ease-in';document.body.appendChild(ov);requestAnimationFrame(function(){ov.style.width='100vw'});setTimeout(function(){b.style.opacity='0';ov.remove();d()},2000)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;top:0;left:0;width:200vw;height:200vh;background:#000;z-index:999999;transform:translate(-100%,-100%) rotate(45deg);transition:transform 2s ease-in';document.body.appendChild(ov);requestAnimationFrame(function(){ov.style.transform='translate(0,0) rotate(45deg)'});setTimeout(function(){b.style.opacity='0';ov.remove();d()},2000)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;top:50%;left:50%;width:0;height:0;border-radius:50%;background:#000;z-index:999999;transition:all 2s ease-in;transform:translate(-50%,-50%)';document.body.appendChild(ov);requestAnimationFrame(function(){ov.style.width='300vw';ov.style.height='300vh'});setTimeout(function(){b.style.opacity='0';ov.remove();d()},2000)},
function(b,d){var bars=[];for(var i=0;i<20;i++){var bar=document.createElement('div');bar.style.cssText='position:fixed;left:0;width:100vw;height:0;background:#000;z-index:999999;top:'+(i*5)+'%;transition:height 2s ease-in '+(i*.05)+'s';document.body.appendChild(bar);bars.push(bar)}requestAnimationFrame(function(){bars.forEach(function(bar){bar.style.height='5vh'})});setTimeout(function(){b.style.opacity='0';bars.forEach(function(bar){bar.remove()});d()},2000)},
function(b,d){var px=1,iv=setInterval(function(){px+=2;b.style.filter='blur('+px*.15+'px) contrast('+(1+px*.03)+')';b.style.imageRendering='pixelated';if(px>30){clearInterval(iv);b.style.opacity='0';setTimeout(d,300)}},55)},
function(b,d){var n=0,iv=setInterval(function(){var off=n*2;b.style.textShadow=off+'px 0 red,-'+off+'px 0 cyan';b.style.filter='saturate('+(1+n*.2)+')';if(++n>25){clearInterval(iv);b.style.textShadow='';b.style.opacity='0';setTimeout(d,200)}},70)},
function(b,d){var l=document.createElement('div');l.style.cssText='position:fixed;left:0;width:100vw;height:4px;background:linear-gradient(90deg,transparent,#0f0,transparent);z-index:999999;top:0;transition:top 2s linear;box-shadow:0 0 30px #0f0';document.body.appendChild(l);requestAnimationFrame(function(){l.style.top='100vh'});b.style.transition='filter 2s';b.style.filter='brightness(0) sepia(1) hue-rotate(70deg)';setTimeout(function(){l.remove();d()},2000)},
function(b,d){var ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;z-index:999999;pointer-events:none;color:#0f0;font-family:monospace;font-size:14px;overflow:hidden;line-height:1.2';var txt='';for(var i=0;i<2000;i++)txt+=Math.random()>.5?'1':'0';ov.textContent=txt;document.body.appendChild(ov);b.style.transition='opacity 2s';b.style.opacity='0';setTimeout(function(){ov.remove();d()},2000)},
function(b,d){var n=0,iv=setInterval(function(){for(var i=0;i<3;i++){var bl=document.createElement('div');bl.style.cssText='position:fixed;z-index:999999;background:#000;width:'+(20+Math.random()*80)+'px;height:'+(10+Math.random()*40)+'px;left:'+Math.random()*100+'%;top:'+Math.random()*100+'%';document.body.appendChild(bl);setTimeout(function(){bl.remove()},1800)}if(++n>12){clearInterval(iv);b.style.opacity='0';setTimeout(d,400)}},130)},

// === CAT 4: ARCADE / RETRO GAMING (31-40) ===
function(b,d){b.style.transition='filter 1s,opacity 1s';b.style.filter='brightness(5)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,filter 2s';b.style.transform='scale(50)';b.style.filter='blur(10px) brightness(0)';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,opacity 2s';b.style.transform='scale(.01)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,opacity 1.5s';b.style.transform='rotate(720deg) scale(.01)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 1s ease-in';b.style.transform='perspective(800px) rotateY(90deg)';setTimeout(function(){b.style.opacity='0';setTimeout(d,800)},1000)},
function(b,d){b.style.transition='transform 1s ease-in';b.style.transform='perspective(800px) rotateX(90deg)';setTimeout(function(){b.style.opacity='0';setTimeout(d,800)},1000)},
function(b,d){b.style.transition='transform 2s ease-in,opacity 2s';b.style.transform='translateX(-120vw)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){b.style.transition='transform 2s ease-in,opacity 2s';b.style.transform='translateX(120vw)';b.style.opacity='0';setTimeout(d,2000)},
function(b,d){var cells=[];for(var r=0;r<8;r++)for(var c=0;c<6;c++){var cell=document.createElement('div');cell.style.cssText='position:fixed;z-index:999999;background:#000;opacity:0;width:'+(100/6)+'vw;height:'+(100/8)+'vh;left:'+(c*100/6)+'vw;top:'+(r*100/8)+'vh;transition:opacity .3s';document.body.appendChild(cell);cells.push(cell)}var idx=cells.map(function(_,i){return i});for(var i=idx.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1));var t=idx[i];idx[i]=idx[j];idx[j]=t}idx.forEach(function(ci,ti){setTimeout(function(){cells[ci].style.opacity='1'},ti*35)});setTimeout(function(){b.style.opacity='0';cells.forEach(function(c){c.remove()});d()},2000)},
function(b,d){b.style.transition='transform 2s ease-in,filter 2s,border-radius 2s';b.style.transform='scale(.01) rotate(1080deg)';b.style.filter='blur(5px)';b.style.borderRadius='50%';b.style.overflow='hidden';setTimeout(d,2000)},

// === CAT 5: DISTORTION / GLITCH ART (41-50) ===
function(b,d){var n=0,iv=setInterval(function(){var o=n*1.5;b.style.textShadow=o+'px 0 #f00,-'+o+'px 0 #0ff,0 '+o+'px #0f0';b.style.filter='hue-rotate('+n*15+'deg)';if(++n>25){clearInterval(iv);b.style.opacity='0';b.style.textShadow='';setTimeout(d,200)}},70)},
function(b,d){var n=0,iv=setInterval(function(){n+=.15;b.style.transform='skewX('+Math.sin(n*3)*15+'deg) skewY('+Math.cos(n*2)*8+'deg)';b.style.filter='brightness('+(1+Math.sin(n*5)*.3)+')';if(n>4){clearInterval(iv);b.style.opacity='0';b.style.transform='';setTimeout(d,300)}},40)},
function(b,d){b.style.transition='transform 2s ease-in,filter 2s';b.style.transform='translateY(50vh) scaleY(2)';b.style.filter='blur(8px) brightness(0)';setTimeout(d,2000)},
function(b,d){var n=0,iv=setInterval(function(){var lines=[];for(var i=0;i<5;i++){var l=document.createElement('div');l.style.cssText='position:fixed;z-index:999999;background:rgba(255,255,255,.7);height:2px;width:'+(20+Math.random()*80)+'vw;left:'+Math.random()*100+'%;top:'+Math.random()*100+'%;transform:rotate('+(Math.random()*360)+'deg)';document.body.appendChild(l);lines.push(l)}setTimeout(function(){lines.forEach(function(l){l.remove()})},150);if(++n>12){clearInterval(iv);b.style.opacity='0';setTimeout(d,300)}},140)},
function(b,d){b.style.transition='filter 2s,opacity 1.5s';b.style.filter='invert(1) hue-rotate(180deg)';setTimeout(function(){b.style.opacity='0'},1000);setTimeout(d,2000)},
function(b,d){var n=0,iv=setInterval(function(){n+=.5;b.style.filter='contrast('+(1+n*.3)+') saturate('+(3-n*.15)+')';if(n>20){clearInterval(iv);b.style.opacity='0';setTimeout(d,300)}},70)},
function(b,d){b.style.transition='filter 1s';b.style.filter='saturate(5) contrast(3) hue-rotate(60deg)';setTimeout(function(){b.style.transition='filter 1s,opacity 1s';b.style.filter='saturate(0) brightness(3)';b.style.opacity='0';setTimeout(d,1000)},1000)},
function(b,d){b.style.transition='filter 2s';b.style.filter='sepia(1) saturate(5) hue-rotate(-30deg) contrast(1.5) brightness(.8)';setTimeout(function(){b.style.opacity='0';setTimeout(d,200)},1800)},
function(b,d){b.style.transition='filter .3s';b.style.filter='brightness(10) invert(1)';setTimeout(function(){b.style.transition='filter 1.5s,opacity 1.5s';b.style.filter='brightness(0) invert(0)';b.style.opacity='0';setTimeout(d,1500)},300)},
function(b,d){var n=0,iv=setInterval(function(){b.style.filter='brightness('+(5-n*.15)+') blur('+(n*.3)+'px) hue-rotate('+(n*20)+'deg)';b.style.transform='scale('+(1+n*.02)+')';if(++n>30){clearInterval(iv);b.style.opacity='0';b.style.transform='';setTimeout(d,200)}},55)}
];

/* Random CRT effect player */
function playRandomCRTEffect(callback){
  var idx=Math.floor(Math.random()*CRT_EFFECTS.length);
  var body=document.body;
  CRT_EFFECTS[idx](body,function(){
    // Do NOT restore styles — keep screen black/hidden until navigation
    body.style.opacity='0';
    body.style.visibility='hidden';
    if(callback)callback();
  });
}

/* Intercept nav links */
(function(){
  if(!document.getElementById('crtZap')){
    var z=document.createElement('div');z.id='crtZap';z.className='crt-zap';document.body.appendChild(z);
  }
  var links=document.querySelectorAll('nav a[href], .nav-links a[href], header a[href]');
  links.forEach(function(a){
    var href=a.getAttribute('href')||'';
    if(href&&!href.startsWith('http')&&!href.startsWith('#')&&!href.startsWith('javascript')&&href.indexOf('.')>0){
      a.addEventListener('click',function(e){
        e.preventDefault();
        if(typeof playRandomRetroSound==='function')try{playRandomRetroSound(2)}catch(ex){}
        playRandomCRTEffect(function(){window.location.href=href});
      });
    }
  });
})();
