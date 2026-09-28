#!/usr/bin/env node
// P6 — drive the REAL sacs-tx-safety.js state machine from live node RPC.
// Long-lived poller: refreshes a chain snapshot each tick and updates the tracker
// (everConfirmed persists), printing every status transition with a timestamp.
const http=require('http');
const TXSAFE=require(require('path').join(__dirname,'..','website','lab','sacs','sacs-tx-safety.js'));
const PORT=process.argv[2], TXID=process.argv[3], SECS=parseInt(process.argv[4]||'120');
function rpc(method,params){return new Promise(res=>{const body=JSON.stringify({jsonrpc:"2.0",id:1,method,params:params||[]});
  const req=http.request({host:'127.0.0.1',port:PORT,method:'POST',headers:{'Content-Type':'application/json','Authorization':'Basic dTpw','Content-Length':Buffer.byteLength(body)}},r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>{try{res(JSON.parse(d).result)}catch(e){res(null)}});});
  req.on('error',()=>res(null));req.write(body);req.end();});}
let snap={tip:0,confirmed:null,inMempool:false,ok:true};
const cv={ dataComplete:()=>snap.ok, tipHeight:()=>snap.tip, conflictOf:()=>null,
  txConfirmedIn:()=>snap.confirmed,
  blockHashAt:(h)=> (snap.confirmed&&snap.confirmed.height===h)?snap.confirmed.hash:null,
  inMempool:()=>snap.inMempool };
const tracker=TXSAFE.makeTracker(cv,{});
tracker.track(TXID,{amount:0});
let last=null;
function stamp(){return new Date().toISOString().substr(11,8);}
async function tick(){
  const tip=await rpc('getblockcount'); snap.tip=parseInt(tip)||0; snap.ok=(tip!==null);
  const rawv=await rpc('getrawtransaction',[TXID,1]);
  if(rawv && rawv.confirmed===true && typeof rawv.block_height==='number'){
    const hash=await rpc('getblockhash',[rawv.block_height]);
    snap.confirmed={height:rawv.block_height,hash:hash}; snap.inMempool=false;
  } else {
    snap.confirmed=null;
    const mp=await rpc('getrawmempool'); snap.inMempool=Array.isArray(mp)&&mp.indexOf(TXID)>=0;
  }
  const s=tracker.update(TXID);
  const key=s.status+'|'+(s.confirmHeight||'')+'|'+s.confirmations+'|'+s.note;
  if(key!==last){ last=key; console.log(`[${stamp()}] tip=${snap.tip} status=${s.status} confHeight=${s.confirmHeight||'-'} conf=${s.confirmations} inMempool=${snap.inMempool} note="${s.note}"`); }
}
(async()=>{ const end=Date.now()+SECS*1000; while(Date.now()<end){ await tick(); await new Promise(r=>setTimeout(r,1000)); } })();
