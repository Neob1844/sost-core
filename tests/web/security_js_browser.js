// security.js adversarial + 45-page pass. Pages are served as https://sostcore.com/* via
// request interception from a local website/ dir (true production origin); every other
// host is aborted. Usage: node tests/web/security_js_browser.js <chrome> <pup> <website_dir> <baseline_website_dir>
'use strict';
const fs=require('fs'),path=require('path');
const [CH,PUP,SITE,BASE]=process.argv.slice(2);
const puppeteer=require(PUP);
const MIME={'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml','.json':'application/json','.woff2':'font/woff2','.jpg':'image/jpeg','.webp':'image/webp','.ico':'image/x-icon','.pdf':'application/pdf','.gif':'image/gif','.mp4':'video/mp4'};
let n=0,ok=0;const step=(nm,c,d='')=>{n++;if(c)ok++;console.log(`[${c?'PASS':'FAIL'}] ${nm}${d?' — '+d:''}`)};
const MUST_FAIL=['https://evil.example/sostcore.com/x.js','https://sostcore.com.evil.example/x.js','https://evil-sostcore.com/x.js',
 'https://user@sostcore.com.evil.example/x.js','https://sostcore.com@evil.example/x.js','javascript:alert(1)','JaVaScRiPt:alert(1)',
 'data:text/javascript,alert(1)','data:application/javascript;base64,YWxlcnQoMSk=','http://sostcore.com/x.js','http://www.sostcore.com/x.js',
 '//evil.example/x.js','//evil.example/sostcore.com/x.js','//sostcore.com.evil.example/x.js','//sostcore.com/x.js','\\\\evil.example/x.js','/\\evil.example/x.js',
 ' //evil.example/x.js','https://user:pw@sostcore.com/x.js','https://user@sostcore.com/x.js','https://sostcore.com:8443/x.js','https://sostcore.com:80/x.js',
 'https://evil.example/?u=sostcore.com','https://evil.example/#sostcore.com','https://xsostcore.com/x.js','https://sostcore.com./x.js',
 'https://sostcore.com%2eevil.example/x.js','https://SOSTCORE.COM.evil.example/x.js','https://evil.example\\@sostcore.com/x.js',
 'https://cdn.jsdelivr.net/npm/x.js','https://unpkg.com/x.js','https://cdnjs.cloudflare.com/x.js','https://fonts.googleapis.com/x.js',
 'blob:https://sostcore.com/0000-1111','https://js.hcaptcha.com.evil.example/x.js','http://js.hcaptcha.com/1/api.js','https://evil.example/js.hcaptcha.com/x.js',
 'https://hcaptcha.com/1/api.js','https://explorer.sostcore.com/x.js','https://wallet.sostcore.com/x.js','https://sostprotocol.com/x.js','wss://sostcore.com/x.js','ftp://sostcore.com/x.js'];
const MUST_PASS=['https://sostcore.com/js/nav-toggle.js','https://www.sostcore.com/js/x.js','https://SOSTCORE.com/js/x.js','https://sostcore.com:443/js/x.js',
 '/js/security.js?v=v576','js/x.js','./js/x.js','https://js.hcaptcha.com/1/api.js'];
const OLD=(s)=>s.indexOf('sostcore.com')>=0||s.indexOf('jsdelivr')>=0||s.indexOf('unpkg')>=0||s.indexOf('cdnjs')>=0||s.indexOf('googleapis')>=0;
function pagesOf(dir){return fs.readdirSync(dir).filter(f=>f.endsWith('.html')&&fs.readFileSync(path.join(dir,f),'utf8').includes('js/security.js')).sort();}
async function visit(browser,dir,page_,w,csp){
  const p=await browser.newPage();await p.setViewport({width:w,height:900});
  const errs=[],blocked=[],ext=new Set();
  p.on('pageerror',e=>errs.push(String(e.message||e).split('\n')[0]));
  p.on('console',m=>{const t=m.text();if(t.indexOf('SECURITY: Blocked external script')>=0)blocked.push(t);});
  await p.setRequestInterception(true);
  p.on('request',r=>{const u=new URL(r.url());
    if(u.hostname==='sostcore.com'){let f=decodeURIComponent(u.pathname);if(f.endsWith('/'))f+='index.html';const fp=path.join(dir,f);
      if(fp.startsWith(dir)&&fs.existsSync(fp)&&fs.statSync(fp).isFile())return r.respond({status:200,contentType:MIME[path.extname(fp)]||'application/octet-stream',headers:csp?{'content-security-policy':csp}:{},body:fs.readFileSync(fp)});
      return r.respond({status:404,contentType:'text/plain',body:'nf'});}
    if(u.protocol==='data:'||u.protocol==='blob:')return r.continue();
    ext.add(u.hostname);r.abort();});
  try{await p.goto('https://sostcore.com/'+page_,{waitUntil:'load',timeout:30000});}catch(e){errs.push('NAV '+e.message);}
  await new Promise(r=>setTimeout(r,2500));
  return {p,errs,blocked,ext};
}
(async()=>{
  const browser=await puppeteer.launch({executablePath:CH,headless:true,args:['--no-sandbox','--disable-gpu','--ignore-certificate-errors']});
  // 1) vectors in the real page context (origin https://sostcore.com)
  const {p}=await visit(browser,SITE,'index.html',1366);
  const fn=await p.evaluate(()=>typeof window.__sostIsAllowedScriptSrc);step('validator exported',fn==='function');
  let fp=0,fnn=0,oldFn=0;
  for(const v of MUST_FAIL){const a=await p.evaluate(s=>window.__sostIsAllowedScriptSrc(s),v);if(a)fnn++;if(OLD(v))oldFn++;step('BLOCK '+JSON.stringify(v),!a,'old substring check: '+(OLD(v)?'ALLOWED':'blocked'));}
  for(const v of MUST_PASS){const a=await p.evaluate(s=>window.__sostIsAllowedScriptSrc(s),v);if(!a)fp++;step('ALLOW '+JSON.stringify(v),a);}
  // 2) DOM behaviour: injected nodes removed, legit kept, src attribute swap caught
  const dom=await p.evaluate(async()=>{const mk=(s)=>{const e=document.createElement('script');e.src=s;e.className='__t';document.body.appendChild(e);return e;};
    const ev=[mk('https://evil.example/sostcore.com/x.js'),mk('https://sostcore.com.evil.example/x.js'),mk('//evil.example/x.js'),mk('data:text/javascript,window.__pwn=1')];
    const good=mk('https://sostcore.com/js/__probe.js');const good2=mk('/js/__probe2.js');
    const div=document.createElement('div');div.innerHTML='<span></span>';const nested=document.createElement('script');nested.src='https://sostcore.com@evil.example/x.js';div.appendChild(nested);document.body.appendChild(div);
    await new Promise(r=>setTimeout(r,50));
    const swap=good;swap.src='https://evil-sostcore.com/x.js';await new Promise(r=>setTimeout(r,50));
    return {evilRemoved:ev.every(e=>!e.isConnected),nestedRemoved:!nested.isConnected,good2Kept:good2.isConnected,swapRemoved:!swap.isConnected,pwn:!!window.__pwn};});
  step('DOM: injected look-alike/data/protocol-relative scripts removed',dom.evilRemoved);
  step('DOM: script nested in an inserted subtree removed',dom.nestedRemoved);
  step('DOM: same-origin relative script kept',dom.good2Kept);
  step('DOM: src swapped to look-alike after insertion removed',dom.swapRemoved);
  console.log('INFO: without CSP an injected data: script still ran before removal: '+dom.pwn+' (MutationObserver runs after insertion; security.js cannot pre-empt execution)');
  await p.close();
  const LIVECSP="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; connect-src 'self' https://sostcore.com https://explorer.sostcore.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'";
  const c=await visit(browser,SITE,'index.html',1366,LIVECSP);
  const pw=await c.p.evaluate(async()=>{const e=document.createElement('script');e.src='data:text/javascript,window.__pwn2=1';document.body.appendChild(e);
    const e2=document.createElement('script');e2.src='https://evil.example/sostcore.com/x.js';document.body.appendChild(e2);await new Promise(r=>setTimeout(r,300));return !!window.__pwn2;});
  step('with the production CSP the injected data: script does not execute',!pw);
  await c.p.close();
  console.log(`ATTACK_VECTORS=${MUST_FAIL.length} FALSE_NEGATIVES=${fnn} LEGIT_VECTORS=${MUST_PASS.length} FALSE_POSITIVES=${fp} OLD_CHECK_WOULD_ALLOW=${oldFn}`);
  // 3) all pages loading security.js: new vs baseline
  const pages=pagesOf(SITE);console.log('PAGES_WITH_SECURITY_JS='+pages.length);
  let newErr=0,legitBlocked=0;const extAll=new Set();
  for(const pg of pages){
    const a=await visit(browser,SITE,pg,1366);await a.p.close();
    const b=await visit(browser,BASE,pg,1366);await b.p.close();
    a.ext.forEach(h=>extAll.add(h));
    const added=a.errs.filter(e=>!b.errs.includes(e));newErr+=added.length;
    // a "legit" block = a same-origin script or hcaptcha removed
    const lb=a.blocked.filter(t=>/https:\/\/(www\.)?sostcore\.com\/|js\.hcaptcha\.com/.test(t)&&!/evil/.test(t));legitBlocked+=lb.length;
    step('page '+pg,added.length===0&&lb.length===0,`errs new=${a.errs.length} base=${b.errs.length} added=${JSON.stringify(added)} blocked=${JSON.stringify(a.blocked)}`);
  }
  console.log('EXTERNAL_HOSTS_REQUESTED='+[...extAll].sort().join(','));
  console.log(`PAGES_TESTED=${pages.length} NEW_JS_ERRORS=${newErr} LEGIT_SCRIPTS_BLOCKED=${legitBlocked}`);
  console.log(`RESULT ${ok}/${n}`);
  await browser.close();process.exit(ok===n?0:1);
})().catch(e=>{console.error(e);process.exit(2);});
