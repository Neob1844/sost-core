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

/* ===== VOICE COUNTDOWN — English only ===== */
if(window.speechSynthesis){speechSynthesis.getVoices();speechSynthesis.onvoiceschanged=function(){speechSynthesis.getVoices()}}
var _CALLOUTS={60:'sixty',50:'fifty',40:'forty',30:'thirty',20:'twenty',
  10:'ten',9:'nine',8:'eight',7:'seven',6:'six',5:'five',4:'four',3:'three',2:'two',1:'one'};

function speakCountdown(n){
  try{
    if(!window.speechSynthesis||!_CALLOUTS[n])return;
    speechSynthesis.cancel();
    var u=new SpeechSynthesisUtterance(_CALLOUTS[n]);
    u.lang='en-US';u.rate=0.9;u.pitch=0.7;u.volume=0.6;
    var voices=speechSynthesis.getVoices();var best=null;
    ['Google US English','Microsoft David','Microsoft Mark','Alex','Daniel','Google UK English Male'].some(function(p){
      best=voices.find(function(v){return v.name&&v.name.indexOf(p)>=0});return!!best});
    if(!best)best=voices.find(function(v){return v.lang==='en-US'})||voices.find(function(v){return v.lang&&v.lang.indexOf('en')===0});
    if(best)u.voice=best;
    speechSynthesis.speak(u);
  }catch(e){}
}

/* ===== 100 NES CHIPTUNE MELODIES ===== */
var CHIPTUNES=[
  // --- Original 30 ---
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
  {n:[196,330,262,392,294,440,330,494,349,523,392,587,440,659,494,784],t:160},
  {n:[349,440,523,440,349,294,262,294,349,440,523,659,523,440,349,294],t:150},
  {n:[587,523,440,392,349,392,440,523,587,659,784,659,587,523,440,392],t:185},
  {n:[262,349,440,523,440,349,262,196,262,349,440,587,523,440,349,262],t:140},
  {n:[392,330,262,196,262,330,392,440,523,440,392,330,262,196,262,330],t:175},
  {n:[494,440,392,349,330,294,262,294,330,349,392,440,494,523,587,523],t:155},
  {n:[659,523,440,392,330,262,330,392,440,523,659,784,880,784,659,523],t:190},
  {n:[220,262,330,392,440,523,440,392,330,262,220,262,330,440,523,659],t:145},
  {n:[784,698,659,587,523,494,440,392,440,494,523,587,659,698,784,880],t:200},
  {n:[330,262,196,262,330,392,440,392,330,262,196,330,392,523,440,330],t:160},
  {n:[440,349,294,262,294,349,440,523,587,523,440,349,294,262,196,262],t:170},
  // --- 31-40: Platformer style ---
  {n:[659,659,262,659,262,523,659,262,784,262,392,262,262,262,262,262],t:200}, // Mario-ish
  {n:[466,349,466,466,523,587,622,698,587,466,349,466,349,294,262,294],t:160}, // Zelda-ish
  {n:[659,622,659,622,659,494,587,523,440,262,330,440,494,330,415,494],t:175}, // Mega Man-ish
  {n:[330,349,330,294,330,262,196,262,330,262,196,165,196,262,330,392],t:130}, // Metroid-ish
  {n:[440,659,587,523,494,440,392,440,523,587,659,587,523,440,392,440],t:185}, // Castlevania-ish
  {n:[659,494,523,587,659,587,523,494,440,440,523,659,587,523,440,440],t:150}, // Tetris-ish
  {n:[659,740,831,880,988,880,831,659,523,659,784,880,784,659,523,659],t:170}, // DuckTales-ish
  {n:[440,392,440,523,440,392,330,262,330,440,523,659,523,440,330,262],t:190}, // Contra-ish
  {n:[523,523,523,392,440,494,523,392,440,494,523,659,587,523,494,440],t:165}, // Punch-Out-ish
  {n:[392,440,494,523,587,659,740,784,740,659,587,523,494,440,392,440],t:155}, // Kirby-ish
  // --- 41-50: RPG/Adventure style ---
  {n:[262,330,392,262,330,392,494,392,330,262,196,262,330,392,523,392],t:120}, // FF-ish
  {n:[294,370,440,294,370,440,587,440,370,294,220,294,370,440,587,440],t:125}, // Dragon Quest-ish
  {n:[330,392,494,659,494,392,330,262,330,392,494,659,784,659,494,392],t:135}, // Earthbound-ish
  {n:[262,311,392,311,262,196,262,311,392,523,392,311,262,196,165,196],t:110}, // Faxanadu-ish
  {n:[440,523,440,392,349,392,440,523,659,523,440,392,349,294,262,294],t:130}, // Crystalis-ish
  {n:[196,247,294,392,294,247,196,165,196,247,294,392,494,392,294,247],t:115}, // Shadowgate-ish
  {n:[330,415,523,659,523,415,330,262,330,415,523,659,784,659,523,415],t:140}, // Startropics-ish
  {n:[220,262,330,440,330,262,220,175,220,262,330,440,523,440,330,262],t:120}, // Ultima-ish
  {n:[349,440,523,698,523,440,349,262,349,440,523,698,880,698,523,440],t:135}, // Wizardry-ish
  {n:[294,349,440,587,440,349,294,247,294,349,440,587,698,587,440,349],t:125}, // Destiny of Emperor-ish
  // --- 51-60: Action/Shooter style ---
  {n:[440,523,659,880,659,523,440,330,440,523,659,880,1047,880,659,523],t:210}, // Gradius-ish
  {n:[392,466,523,587,622,587,523,466,392,466,523,587,698,587,523,466],t:195}, // R-Type-ish
  {n:[330,440,523,659,784,659,523,440,330,440,523,784,659,523,440,330],t:200}, // Life Force-ish
  {n:[262,349,440,523,659,523,440,349,262,349,523,659,784,659,440,349],t:180}, // 1943-ish
  {n:[494,587,698,880,698,587,494,392,494,587,698,880,988,880,698,587],t:205}, // Zanac-ish
  {n:[220,294,370,440,523,440,370,294,220,294,370,523,659,523,370,294],t:190}, // Gun-Nac-ish
  {n:[349,440,523,698,880,698,523,440,349,440,698,880,1047,880,523,440],t:215}, // TwinBee-ish
  {n:[262,330,440,523,440,330,262,196,330,440,523,659,523,440,330,262],t:185}, // Xevious-ish
  {n:[392,494,587,784,587,494,392,330,392,494,587,784,880,784,587,494],t:195}, // Star Soldier-ish
  {n:[440,523,659,784,880,784,659,523,440,659,784,880,1047,880,784,659],t:210}, // Crisis Force-ish
  // --- 61-70: Puzzle/Cute style ---
  {n:[523,659,784,659,523,392,523,659,784,1047,784,659,523,392,262,392],t:175}, // Bubble Bobble-ish
  {n:[659,784,880,784,659,523,440,523,659,784,880,1047,880,784,659,523],t:165}, // Snow Bros-ish
  {n:[392,440,523,440,392,330,294,330,392,440,523,587,523,440,392,330],t:150}, // Lode Runner-ish
  {n:[523,587,659,587,523,494,440,494,523,587,659,784,659,587,523,494],t:160}, // Adventures of Lolo-ish
  {n:[330,392,440,523,440,392,330,294,262,294,330,392,440,523,587,523],t:155}, // Solomon's Key-ish
  {n:[440,494,523,587,659,587,523,494,440,392,349,392,440,494,523,587],t:170}, // Kickle Cubicle-ish
  {n:[262,330,392,523,659,523,392,330,262,330,392,523,659,784,659,523],t:145}, // Yoshi-ish
  {n:[349,440,523,659,523,440,349,294,349,440,523,659,784,659,523,440],t:160}, // Wario's Woods-ish
  {n:[196,262,330,440,330,262,196,165,262,330,440,523,440,330,262,196],t:140}, // Dr. Mario-ish
  {n:[294,370,440,523,587,523,440,370,294,370,440,523,659,587,523,440],t:155}, // Palamedes-ish
  // --- 71-80: Horror/Dark style ---
  {n:[165,196,220,196,165,147,131,147,165,196,220,262,220,196,165,147],t:110}, // Ghost House-ish
  {n:[233,262,294,262,233,220,196,220,233,262,294,349,294,262,233,220],t:105}, // Ghosts n Goblins-ish
  {n:[175,196,233,196,175,165,147,165,175,196,233,262,233,196,175,165],t:100}, // Splatterhouse-ish
  {n:[311,330,349,330,311,294,262,294,311,330,349,392,349,330,311,294],t:115}, // Gargoyle's Quest-ish
  {n:[220,247,262,294,262,247,220,196,220,247,262,311,294,262,247,220],t:108}, // Monster Party-ish
  {n:[147,175,196,220,196,175,147,131,147,175,196,233,220,196,175,147],t:95},  // Friday 13th-ish
  {n:[262,294,311,294,262,247,220,247,262,294,311,349,311,294,262,247],t:112}, // Nightmare Elm-ish
  {n:[196,220,247,262,247,220,196,175,196,220,247,294,262,247,220,196],t:105}, // Uninvited-ish
  {n:[330,349,370,392,370,349,330,311,330,349,370,415,392,370,349,330],t:118}, // Deja Vu-ish
  {n:[131,147,165,175,196,175,165,147,131,165,196,220,196,165,147,131],t:90},  // Sweet Home-ish
  // --- 81-90: Sports/Racing style ---
  {n:[523,587,659,784,659,587,523,440,523,587,784,880,784,587,523,440],t:220}, // Excitebike-ish
  {n:[440,523,587,659,784,659,587,523,440,523,659,784,880,784,659,523],t:210}, // RC Pro-Am-ish
  {n:[392,440,523,587,659,587,523,440,392,440,587,659,784,659,523,440],t:200}, // Rad Racer-ish
  {n:[349,440,523,587,698,587,523,440,349,440,523,698,784,698,523,440],t:195}, // Mach Rider-ish
  {n:[262,330,440,523,659,523,440,330,262,330,523,659,784,659,440,330],t:215}, // Track n Field-ish
  {n:[294,392,494,587,698,587,494,392,294,392,587,698,784,698,494,392],t:205}, // Ice Hockey-ish
  {n:[330,440,523,659,784,659,523,440,330,440,659,784,880,784,523,440],t:220}, // Tecmo Bowl-ish
  {n:[196,262,330,392,494,392,330,262,196,330,392,494,587,494,392,330],t:190}, // Pro Wrestling-ish
  {n:[349,392,440,523,587,523,440,392,349,440,523,587,659,587,523,440],t:200}, // Double Dribble-ish
  {n:[440,494,587,659,784,659,587,494,440,587,659,784,880,784,659,587],t:210}, // Blades of Steel-ish
  // --- 91-100: Wild/Experimental style ---
  {n:[262,523,392,659,330,587,440,784,349,698,494,880,523,1047,659,784],t:180}, // Battletoads-ish
  {n:[880,784,659,587,523,440,392,330,262,330,392,440,523,587,659,784],t:195}, // Ninja Gaiden-ish
  {n:[440,392,330,294,262,294,330,392,440,523,587,659,587,523,440,392],t:170}, // TMNT-ish
  {n:[523,440,349,294,262,294,349,440,523,659,698,784,698,659,523,440],t:175}, // River City-ish
  {n:[659,698,784,698,659,587,523,587,659,698,784,880,784,698,659,587],t:185}, // Blaster Master-ish
  {n:[196,262,196,330,196,392,196,440,196,392,196,330,196,262,196,220],t:160}, // Balloon Fight-ish
  {n:[523,262,440,330,392,349,330,392,262,440,330,494,349,523,392,587],t:175}, // Ice Climber-ish
  {n:[784,698,784,880,784,659,523,659,784,880,1047,880,784,659,523,659],t:200}, // Kid Icarus-ish
  {n:[330,294,262,294,330,392,440,523,440,392,330,294,262,196,165,196],t:145}, // Adventure Island-ish
  {n:[440,523,440,659,523,784,659,880,784,659,523,440,392,330,262,330],t:190}  // Double Dragon-ish
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

/* ===== NES AUTOPLAY ON LOAD (10s) ===== */
var _nesCtx=null,_nesMuted=false,_nesGain=null,_nesPlaying=false;
function _nesAutoplay(){
  if(_nesPlaying)return;_nesPlaying=true;
  var c=_ctx();if(!c)return;_nesCtx=c;
  var master=c.createGain();master.gain.value=0.04;master.connect(c.destination);_nesGain=master;
  var m=CHIPTUNES[Math.floor(Math.random()*CHIPTUNES.length)];
  var dur=10,nt=60/m.t,t=c.currentTime,total=0;
  var bass=c.createOscillator(),bg=c.createGain();
  bass.type='triangle';bass.frequency.value=m.n[0]*0.25;
  bg.gain.setValueAtTime(0.6,t);bg.gain.setValueAtTime(0.6,t+dur-2);bg.gain.linearRampToValueAtTime(0,t+dur);
  bass.connect(bg);bg.connect(master);bass.start(t);bass.stop(t+dur);
  while(total<dur){
    m.n.forEach(function(freq,i){
      var s=t+total+i*nt;if(s-t>=dur)return;
      var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(master);o.type='square';
      o.frequency.setValueAtTime(freq,s);
      var fadeStart=Math.max(0,dur-2-(s-t));var vol=(s-t>dur-2)?Math.max(0,1-(s-t-(dur-2))/2):1;
      g.gain.setValueAtTime(0,s);g.gain.linearRampToValueAtTime(vol,s+0.01);
      g.gain.linearRampToValueAtTime(vol*0.6,s+nt*0.5);g.gain.linearRampToValueAtTime(0,s+nt*0.9);
      o.start(s);o.stop(s+nt);
    });
    total+=m.n.length*nt;
  }
  var idx=CHIPTUNES.indexOf(m);
  var btn=document.getElementById('nesMuteBtn');
  if(btn)btn.title='NES #'+(idx+1)+'/100 — click to mute';
  setTimeout(function(){_nesPlaying=false;if(btn)btn.style.opacity='0.4'},10500);
}
function _nesStop(){
  if(_nesCtx){try{_nesCtx.close()}catch(e){}_nesCtx=null;_nesGain=null;_nesPlaying=false;}
}
function _nesPlayRandom(){
  _nesStop();
  var c=_ctx();if(!c)return;_nesCtx=c;_nesPlaying=true;
  var master=c.createGain();master.gain.value=0.04;master.connect(c.destination);_nesGain=master;
  var m=CHIPTUNES[Math.floor(Math.random()*CHIPTUNES.length)];
  var dur=10,nt=60/m.t,t=c.currentTime,total=0;
  var bass=c.createOscillator(),bg=c.createGain();
  bass.type='triangle';bass.frequency.value=m.n[0]*0.25;
  bg.gain.setValueAtTime(0.6,t);bg.gain.setValueAtTime(0.6,t+dur-2);bg.gain.linearRampToValueAtTime(0,t+dur);
  bass.connect(bg);bg.connect(master);bass.start(t);bass.stop(t+dur);
  while(total<dur){
    m.n.forEach(function(freq,i){
      var s=t+total+i*nt;if(s-t>=dur)return;
      var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(master);o.type='square';
      o.frequency.setValueAtTime(freq,s);
      var vol=(s-t>dur-2)?Math.max(0,1-(s-t-(dur-2))/2):1;
      g.gain.setValueAtTime(0,s);g.gain.linearRampToValueAtTime(vol,s+0.01);
      g.gain.linearRampToValueAtTime(vol*0.6,s+nt*0.5);g.gain.linearRampToValueAtTime(0,s+nt*0.9);
      o.start(s);o.stop(s+nt);
    });
    total+=m.n.length*nt;
  }
  var idx=CHIPTUNES.indexOf(m);
  var btn=document.getElementById('nesMuteBtn');
  if(btn){btn.title='NES #'+(idx+1)+'/100';btn.style.opacity='1';btn.textContent='\uD83C\uDFAE';}
  setTimeout(function(){_nesPlaying=false;if(btn)btn.style.opacity='0.4'},10500);
}
function nesToggleMute(){
  var btn=document.getElementById('nesMuteBtn');
  if(_nesPlaying){
    // Currently playing → stop it (mute)
    _nesStop();
    _nesMuted=true;
    if(btn){btn.textContent='\uD83D\uDD07';btn.title='NES muted — click to play';btn.style.opacity='0.4';}
    return;
  }
  // Not playing → play a new random melody
  _nesMuted=false;
  _nesPlayRandom();
}
(function(){
  var triggered=false;
  function onInteract(){
    if(triggered)return;triggered=true;
    document.removeEventListener('click',onInteract);
    document.removeEventListener('keydown',onInteract);
    document.removeEventListener('touchstart',onInteract);
    setTimeout(_nesAutoplay,300);
  }
  document.addEventListener('click',onInteract);
  document.addEventListener('keydown',onInteract);
  document.addEventListener('touchstart',onInteract);
})();

/* ===== SYNTHWAVE SPLASH MUSIC — atmospheric retro terminal ===== */
var SPLASH_THEMES=[
  // Each: {melody:[freq,start,dur,type,vol], pad_freq}
  {pad:65.41,mel:[[131,0,.4,'square',.09],[165,0.5,.4,'square',.09],[196,1,.4,'square',.09],[262,1.5,.8,'square',.11],[196,2.5,.4,'square',.09],[165,3,.4,'square',.09],[131,3.5,.4,'square',.09],[98,4,1,'sawtooth',.07],[131,5,.3,'square',.09],[156,5.4,.3,'square',.09],[196,5.8,.3,'square',.09],[262,6.2,.8,'triangle',.10]]},
  {pad:55,mel:[[110,0,.5,'square',.08],[147,0.6,.4,'square',.09],[175,1.1,.4,'square',.09],[220,1.6,.7,'triangle',.10],[175,2.4,.3,'square',.08],[147,2.8,.4,'square',.09],[110,3.3,.5,'sawtooth',.07],[88,3.9,1,'sine',.06],[110,5,.3,'square',.08],[131,5.4,.3,'square',.09],[165,5.8,.4,'square',.09],[220,6.3,.7,'triangle',.10]]},
  {pad:73.42,mel:[[147,0,.4,'square',.09],[175,0.5,.4,'square',.08],[220,1,.5,'triangle',.10],[294,1.6,.7,'square',.11],[220,2.4,.3,'square',.08],[175,2.8,.4,'square',.09],[147,3.3,.5,'square',.08],[110,3.9,1,'sawtooth',.06],[147,5,.3,'square',.09],[196,5.4,.4,'square',.09],[247,5.9,.3,'square',.08],[294,6.3,.7,'triangle',.10]]},
  {pad:82.41,mel:[[165,0,.4,'square',.09],[196,0.5,.4,'square',.08],[247,1,.5,'square',.09],[330,1.6,.8,'triangle',.11],[247,2.5,.3,'square',.08],[196,2.9,.4,'square',.09],[165,3.4,.5,'sawtooth',.07],[131,4,1,'sine',.06],[165,5,.3,'square',.09],[208,5.4,.3,'square',.08],[262,5.8,.4,'square',.09],[330,6.3,.7,'triangle',.10]]},
  {pad:49,mel:[[98,0,.5,'sawtooth',.07],[131,0.6,.4,'square',.09],[165,1.1,.5,'square',.09],[196,1.7,.7,'triangle',.10],[165,2.5,.3,'square',.08],[131,2.9,.4,'square',.09],[98,3.4,.6,'sawtooth',.07],[78,4,.9,'sine',.05],[98,5,.3,'square',.08],[123,5.4,.3,'square',.09],[147,5.8,.4,'square',.09],[196,6.3,.7,'triangle',.10]]},
  {pad:61.74,mel:[[123,0,.4,'square',.08],[156,0.5,.4,'square',.09],[185,1,.5,'square',.09],[247,1.6,.8,'triangle',.11],[185,2.5,.3,'square',.08],[156,2.9,.4,'square',.09],[123,3.4,.4,'square',.08],[93,3.9,1.1,'sawtooth',.06],[123,5.1,.3,'square',.09],[147,5.5,.3,'square',.08],[185,5.9,.3,'square',.09],[247,6.3,.7,'triangle',.10]]},
  {pad:87.31,mel:[[175,0,.3,'square',.09],[220,0.4,.4,'square',.09],[262,0.9,.5,'triangle',.10],[349,1.5,.8,'square',.11],[262,2.4,.3,'square',.08],[220,2.8,.4,'square',.09],[175,3.3,.5,'square',.08],[131,3.9,1,'sawtooth',.07],[175,5,.3,'square',.09],[220,5.4,.3,'square',.08],[294,5.8,.4,'square',.09],[349,6.3,.7,'triangle',.10]]},
  {pad:58.27,mel:[[117,0,.5,'sawtooth',.07],[147,0.6,.4,'square',.09],[175,1.1,.4,'square',.08],[233,1.6,.7,'triangle',.10],[175,2.4,.4,'square',.09],[147,2.9,.3,'square',.08],[117,3.3,.5,'sawtooth',.07],[88,3.9,.9,'sine',.06],[117,5,.3,'square',.08],[147,5.4,.4,'square',.09],[185,5.9,.3,'square',.08],[233,6.3,.7,'triangle',.10]]},
  {pad:69.3,mel:[[139,0,.4,'square',.09],[175,0.5,.4,'square',.08],[208,1,.5,'square',.09],[277,1.6,.8,'triangle',.11],[208,2.5,.3,'square',.08],[175,2.9,.4,'square',.09],[139,3.4,.4,'square',.08],[104,3.9,1,'sawtooth',.06],[139,5,.3,'square',.09],[175,5.4,.3,'square',.08],[220,5.8,.4,'square',.09],[277,6.3,.7,'triangle',.10]]},
  {pad:51.91,mel:[[104,0,.5,'square',.08],[131,0.6,.4,'square',.09],[156,1.1,.5,'square',.09],[208,1.7,.7,'triangle',.10],[156,2.5,.3,'square',.08],[131,2.9,.4,'square',.09],[104,3.4,.6,'sawtooth',.07],[82,4,.9,'sine',.05],[104,5,.3,'square',.09],[131,5.4,.3,'square',.08],[165,5.8,.4,'square',.09],[208,6.3,.7,'triangle',.10]]}
];

function playRetroSplashMusic(dur){
  dur=dur||7;var c=_ctx();if(!c)return;
  var theme=SPLASH_THEMES[Math.floor(Math.random()*SPLASH_THEMES.length)];
  var t=c.currentTime;
  // Low drone pad
  var pad=c.createOscillator(),pg=c.createGain();
  pad.type='sine';pad.frequency.value=theme.pad;
  pg.gain.setValueAtTime(0,t);pg.gain.linearRampToValueAtTime(0.05,t+1);
  pg.gain.setValueAtTime(0.05,t+dur-2);pg.gain.linearRampToValueAtTime(0,t+dur);
  pad.connect(pg);pg.connect(c.destination);pad.start(t);pad.stop(t+dur);
  // Melody notes
  theme.mel.forEach(function(n){
    var freq=n[0],start=n[1],d=n[2],type=n[3],vol=n[4];
    if(start>=dur)return;
    var o=c.createOscillator(),g=c.createGain();
    o.type=type;o.frequency.value=freq;
    g.gain.setValueAtTime(0,t+start);
    g.gain.linearRampToValueAtTime(vol,t+start+0.04);
    g.gain.linearRampToValueAtTime(vol*0.6,t+start+d*0.7);
    g.gain.linearRampToValueAtTime(0,t+start+d);
    o.connect(g);g.connect(c.destination);o.start(t+start);o.stop(t+start+d+0.05);
  });
}
