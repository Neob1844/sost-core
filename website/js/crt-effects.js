/* SOST CRT Navigation Effects — intercepts nav links for CRT transition + sound */
(function(){
  // Create zap element if not exists
  if(!document.getElementById('crtZap')){
    var z=document.createElement('div');z.id='crtZap';z.className='crt-zap';
    document.body.appendChild(z);
  }
  // Intercept internal nav links
  var links=document.querySelectorAll('nav a[href], .nav-links a[href]');
  links.forEach(function(a){
    var href=a.getAttribute('href')||'';
    if(href&&!href.startsWith('http')&&!href.startsWith('#')&&!href.startsWith('javascript')&&href.indexOf('.')>0){
      a.addEventListener('click',function(e){
        e.preventDefault();
        document.body.classList.add('crt-off');
        setTimeout(function(){var zap=document.getElementById('crtZap');if(zap)zap.classList.add('on')},650);
        if(typeof playRandomRetroSound==='function')try{playRandomRetroSound(0.9)}catch(ex){}
        setTimeout(function(){window.location.href=href},900);
      });
    }
  });
})();
