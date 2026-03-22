/* SOST CRT Navigation — Fallout pip-boy TV shutdown on every page transition */
(function(){
  // Create zap + flash elements
  if(!document.getElementById('crtZap')){
    var z=document.createElement('div');z.id='crtZap';z.className='crt-zap';document.body.appendChild(z);
    var fl=document.createElement('div');fl.id='crtFlash';fl.className='crt-flash';document.body.appendChild(fl);
  }

  // Intercept all internal nav links
  var links=document.querySelectorAll('nav a[href], .nav-links a[href], header a[href]');
  links.forEach(function(a){
    var href=a.getAttribute('href')||'';
    if(href&&!href.startsWith('http')&&!href.startsWith('#')&&!href.startsWith('javascript')&&href.indexOf('.')>0){
      a.addEventListener('click',function(e){
        e.preventDefault();
        // Phosphor flash
        var fl=document.getElementById('crtFlash');
        if(fl){fl.classList.add('on');setTimeout(function(){fl.classList.remove('on')},150);}
        // CRT off animation
        document.body.classList.add('crt-off');
        // Zap line appears mid-animation
        setTimeout(function(){var zap=document.getElementById('crtZap');if(zap)zap.classList.add('on')},900);
        // Retro sound
        if(typeof playRandomRetroSound==='function')try{playRandomRetroSound(1.5)}catch(ex){}
        // Navigate after animation completes
        setTimeout(function(){window.location.href=href},1500);
      });
    }
  });
})();
