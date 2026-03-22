/**
 * SOST Retro Sound Engine v2 — 105 procedural 8-bit sounds + voice + chiptune
 * All generated with Web Audio API. Zero external files.
 */
function _ctx(){try{return new(window.AudioContext||window.webkitAudioContext)()}catch(e){return null}}

/* ===== 105 RETRO SOUNDS ===== */
var RETRO_SOUNDS=[];

// A) ZX SPECTRUM (15): square wave cassette loading
(function(){
  var P=[[800,2400,400,3000,600,2000,500,2800,300,1500],[1200,600,1800,300,2400,900,1500,450,2100,750],
    [500,3500,700,2800,400,3200,600,2600,350,3000],[2000,500,1500,800,2500,400,1800,600,2200,700],
    [300,2800,500,2200,700,1800,900,1400,1100,1000],[1000,3000,500,2500,800,2000,1200,1600,400,2800],
    [600,2600,900,2000,1200,1600,600,2400,800,1800],[1500,400,2000,600,2500,350,1800,550,2200,450],
    [400,3200,800,2400,1200,1800,500,2800,700,2000],[900,2200,450,2800,650,2400,850,1800,1100,1400],
    [750,3100,550,2700,850,1900,1050,1500,350,2600],[1800,700,2300,500,2800,400,2100,650,1600,900],
    [450,2900,650,2300,950,1700,550,2500,750,2100],[1100,500,1700,800,2600,350,1900,600,2400,500],
    [350,3300,600,2500,900,2100,700,2700,400,1800]];
  P.forEach(function(p){RETRO_SOUNDS.push(function(c,d){
    var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='square';
    var t=c.currentTime;p.forEach(function(f,j){o.frequency.linearRampToValueAtTime(f,t+j*(d/p.length))});
    g.gain.setValueAtTime(0.07,t);g.gain.linearRampToValueAtTime(0,t+d);o.start(t);o.stop(t+d)})});
})();

// B) COMMODORE 64 SID (15): sawtooth+square arpeggio
(function(){
  var B=[220,294,330,392,440,523,587,659,196,262,349,494,554,698,784];
  B.forEach(function(b){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o1=c.createOscillator(),o2=c.createOscillator(),g=c.createGain();
    o1.connect(g);o2.connect(g);g.connect(c.destination);o1.type='sawtooth';o2.type='square';
    var a=[b,b*1.25,b*1.5,b*2,b*1.5,b*1.25];
    a.forEach(function(f,j){o1.frequency.setValueAtTime(f,t+j*(d/a.length));o2.frequency.setValueAtTime(f*2,t+j*(d/a.length))});
    g.gain.setValueAtTime(0.05,t);g.gain.linearRampToValueAtTime(0,t+d);
    o1.start(t);o1.stop(t+d);o2.start(t);o2.stop(t+d)})});
})();

// C) ATARI 2600 (15): low square blips with modulation
(function(){
  var F=[120,90,150,180,200,110,160,130,170,140,100,190,135,155,175];
  F.forEach(function(f){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='square';
    for(var j=0;j<8;j++){o.frequency.setValueAtTime(f*(1+j*0.3),t+j*(d/8));o.frequency.linearRampToValueAtTime(f*(1+j*0.15),t+(j+0.5)*(d/8))}
    g.gain.setValueAtTime(0.06,t);g.gain.linearRampToValueAtTime(0,t+d);o.start(t);o.stop(t+d)})});
})();

// D) AMSTRAD CPC AY-3-8910 (15): square with envelope decay
(function(){
  var T=[440,523,659,784,880,392,494,587,698,831,349,415,554,622,740];
  T.forEach(function(f){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='square';
    o.frequency.setValueAtTime(f,t);o.frequency.exponentialRampToValueAtTime(Math.max(f*0.25,20),t+d);
    g.gain.setValueAtTime(0.06,t);g.gain.setValueAtTime(0.07,t+d*0.1);g.gain.linearRampToValueAtTime(0,t+d);
    o.start(t);o.stop(t+d)})});
})();

// E) NES/FAMICOM (15): pulse+triangle sequences
(function(){
  var N=[262,294,330,349,392,440,494,523,587,659,196,233,277,311,370];
  N.forEach(function(f){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o1=c.createOscillator(),o2=c.createOscillator(),g=c.createGain();
    o1.connect(g);o2.connect(g);g.connect(c.destination);o1.type='square';o2.type='triangle';
    var s=[f,f*1.19,f*1.5,f*1.19,f,f*0.75,f,f*1.5];
    s.forEach(function(n,j){o1.frequency.setValueAtTime(n,t+j*(d/s.length));o2.frequency.setValueAtTime(n*0.5,t+j*(d/s.length))});
    g.gain.setValueAtTime(0.05,t);g.gain.linearRampToValueAtTime(0,t+d);
    o1.start(t);o1.stop(t+d);o2.start(t);o2.stop(t+d)})});
})();

// F) GAME BOY (15): sweep chip sounds
(function(){
  var S=[800,600,1000,500,900,700,1100,550,950,650,750,850,1050,480,720];
  S.forEach(function(f,i){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='square';
    o.frequency.setValueAtTime(f,t);o.frequency.exponentialRampToValueAtTime(i%2?Math.max(f*0.25,20):Math.min(f*4,8000),t+d*0.6);
    o.frequency.setValueAtTime(f*1.5,t+d*0.65);o.frequency.exponentialRampToValueAtTime(Math.max(f*0.5,20),t+d);
    g.gain.setValueAtTime(0.06,t);g.gain.linearRampToValueAtTime(0,t+d);o.start(t);o.stop(t+d)})});
})();

// G) SNES (15): softer sine+triangle with short delay
(function(){
  var M=[262,330,392,494,523,587,659,784,880,440,349,294,196,233,698];
  M.forEach(function(f){RETRO_SOUNDS.push(function(c,d){
    var t=c.currentTime,o1=c.createOscillator(),o2=c.createOscillator(),g=c.createGain(),dl=c.createDelay(0.3);
    var dg=c.createGain();dg.gain.value=0.3;o1.connect(g);o2.connect(g);g.connect(c.destination);g.connect(dl);dl.connect(dg);dg.connect(c.destination);
    o1.type='sine';o2.type='triangle';dl.delayTime.value=0.15;
    var seq=[f,f*1.33,f*1.5,f*1.33,f,f*0.75];
    seq.forEach(function(n,j){o1.frequency.setValueAtTime(n,t+j*(d/seq.length));o2.frequency.setValueAtTime(n*0.5,t+j*(d/seq.length))});
    g.gain.setValueAtTime(0.04,t);g.gain.linearRampToValueAtTime(0,t+d);
    o1.start(t);o1.stop(t+d);o2.start(t);o2.stop(t+d)})});
})();

/* ===== RANDOM PLAY ===== */
function playRandomRetroSound(duration){
  duration=duration||1.0;var c=_ctx();if(!c)return;
  try{RETRO_SOUNDS[Math.floor(Math.random()*RETRO_SOUNDS.length)](c,duration)}catch(e){}
}

/* ===== VOICE COUNTDOWN — all 60 numbers, English forced ===== */
var _vReady=false;
if(window.speechSynthesis){speechSynthesis.getVoices();speechSynthesis.onvoiceschanged=function(){_vReady=true;speechSynthesis.getVoices()}}
var _WORDS={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten',
  11:'eleven',12:'twelve',13:'thirteen',14:'fourteen',15:'fifteen',16:'sixteen',17:'seventeen',18:'eighteen',19:'nineteen',20:'twenty',
  21:'twenty one',22:'twenty two',23:'twenty three',24:'twenty four',25:'twenty five',26:'twenty six',27:'twenty seven',28:'twenty eight',29:'twenty nine',30:'thirty',
  31:'thirty one',32:'thirty two',33:'thirty three',34:'thirty four',35:'thirty five',36:'thirty six',37:'thirty seven',38:'thirty eight',39:'thirty nine',40:'forty',
  41:'forty one',42:'forty two',43:'forty three',44:'forty four',45:'forty five',46:'forty six',47:'forty seven',48:'forty eight',49:'forty nine',50:'fifty',
  51:'fifty one',52:'fifty two',53:'fifty three',54:'fifty four',55:'fifty five',56:'fifty six',57:'fifty seven',58:'fifty eight',59:'fifty nine',60:'sixty'};

function speakCountdown(n){
  try{
    if(!window.speechSynthesis||!_WORDS[n])return;
    speechSynthesis.cancel();
    var u=new SpeechSynthesisUtterance(_WORDS[n]);
    u.lang='en-US';u.rate=1.1;u.pitch=0.7;u.volume=0.6;
    var voices=speechSynthesis.getVoices();var best=null;
    ['Google US English','Microsoft David','Microsoft Mark','Alex','Daniel','Google UK English Male'].some(function(p){
      best=voices.find(function(v){return v.name&&v.name.indexOf(p)>=0});return!!best});
    if(!best)best=voices.find(function(v){return v.lang==='en-US'})||voices.find(function(v){return v.lang==='en-GB'})||voices.find(function(v){return v.lang&&v.lang.indexOf('en')===0});
    if(best)u.voice=best;
    speechSynthesis.speak(u);
  }catch(e){}
}

/* ===== 20 CHIPTUNE MELODIES ===== */
var CHIPTUNES=[
  {n:[262,330,392,523,392,330,262,330,392,523,659,523,392,330,262,330],t:180},
  {n:[196,233,262,277,262,233,196,196,262,311,330,311,262,233,196,233],t:150},
  {n:[440,554,659,880,659,554,440,554,659,880,1047,880,659,554,440,554],t:200},
  {n:[330,392,494,392,330,262,330,392,494,659,494,392,330,262,196,262],t:170},
  {n:[523,494,440,392,440,494,523,659,523,494,440,392,330,262,330,392],t:160},
  {n:[196,262,330,392,440,392,330,262,196,262,330,440,523,440,330,262],t:140},
  {n:[880,784,659,523,440,523,659,784,880,784,659,523,440,392,330,392],t:190},
  {n:[262,294,330,349,392,440,494,523,494,440,392,349,330,294,262,294],t:155},
  {n:[392,494,587,494,392,330,392,494,587,698,587,494,392,330,262,330],t:175},
  {n:[440,523,659,523,440,349,440,523,659,784,659,523,440,349,294,349],t:165},
  {n:[330,349,392,440,494,440,392,349,330,294,262,294,330,349,392,440],t:145},
  {n:[523,587,659,784,659,587,523,494,440,494,523,587,659,523,440,392],t:185},
  {n:[196,220,262,294,330,294,262,220,196,220,262,330,392,330,262,220],t:135},
  {n:[659,587,523,494,440,392,349,330,349,392,440,494,523,587,659,587],t:195},
  {n:[262,392,330,440,349,494,392,523,440,587,494,659,523,587,440,392],t:170},
  {n:[784,659,523,440,392,330,262,196,262,330,392,440,523,659,784,659],t:180},
  {n:[294,349,440,349,294,262,294,349,440,523,440,349,294,262,196,262],t:155},
  {n:[440,392,349,330,349,392,440,523,440,392,349,330,294,262,294,330],t:165},
  {n:[523,440,392,330,392,440,523,659,523,440,392,330,262,196,262,330],t:175},
  {n:[196,330,262,392,294,440,330,494,349,523,392,587,440,659,494,784],t:160}
];
function playChiptuneSplash(duration){
  duration=duration||7;var c=_ctx();if(!c)return;
  var m=CHIPTUNES[Math.floor(Math.random()*CHIPTUNES.length)];
  var nt=60/m.t,t=c.currentTime,total=0;
  while(total<duration){
    m.n.forEach(function(freq,i){
      var s=t+total+i*nt;if(s-t>=duration)return;
      var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);o.type='square';
      o.frequency.setValueAtTime(freq,s);
      g.gain.setValueAtTime(0,s);g.gain.linearRampToValueAtTime(0.04,s+0.015);
      g.gain.linearRampToValueAtTime(0.025,s+nt*0.5);g.gain.linearRampToValueAtTime(0,s+nt*0.9);
      o.start(s);o.stop(s+nt)});
    total+=m.n.length*nt}
}
