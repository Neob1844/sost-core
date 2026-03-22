/* SOST Security Layer — XSS protection, auto-lock, injection detection */

// === XSS SANITIZATION ===
function sanitize(str){
  if(typeof str!=='string')return'';
  var d=document.createElement('div');d.textContent=str;return d.innerHTML;
}

// === WALLET AUTO-LOCK (5 min inactivity) ===
var _lastActivity=Date.now();
['mousemove','keypress','touchstart','click'].forEach(function(e){
  document.addEventListener(e,function(){_lastActivity=Date.now()},{passive:true});
});
setInterval(function(){
  if(Date.now()-_lastActivity>300000){
    // Clear sensitive data from global scope
    if(window.walletPrivKey){window.walletPrivKey=null;}
    if(window.decryptedKey){window.decryptedKey=null;}
    if(typeof lockWallet==='function')try{lockWallet();}catch(e){}
  }
},30000);

// === EXTENSION INJECTION DETECTION ===
try{
  var _secObs=new MutationObserver(function(muts){
    muts.forEach(function(m){
      m.addedNodes.forEach(function(node){
        if(node.tagName==='SCRIPT'&&node.src&&
           node.src.indexOf('sostcore.com')<0&&
           node.src.indexOf('jsdelivr')<0&&
           node.src.indexOf('unpkg')<0&&
           node.src.indexOf('cdnjs')<0&&
           node.src.indexOf('googleapis')<0){
          console.warn('SECURITY: Blocked external script:',node.src);
          node.remove();
        }
      });
    });
  });
  _secObs.observe(document.documentElement,{childList:true,subtree:true});
}catch(e){}
