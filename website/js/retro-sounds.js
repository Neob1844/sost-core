/**
 * SOST Retro Sound Engine — 60 procedural 8-bit sounds + voice countdown + chiptune
 * All sounds generated with Web Audio API. No MP3 files.
 */

/* ===== UTILITY ===== */
function _ctx(){try{return new(window.AudioContext||window.webkitAudioContext)();}catch(e){return null;}}
function _osc(c,type,freq,t,dur,vol){
  var o=c.createOscillator(),g=c.createGain();
  o.connect(g);g.connect(c.destination);o.type=type;
  o.frequency.setValueAtTime(freq,t);
  g.gain.setValueAtTime(vol,t);g.gain.linearRampToValueAtTime(0,t+dur);
  o.start(t);o.stop(t+dur);return o;
}

/* ===== 60 RETRO SOUNDS ===== */
var RETRO_SOUNDS=[];

// A) SPECTRUM ZX (0-9): square wave cassette-style
(function(){
  var patterns=[
    [800,2400,400,3000,600,2000,500,2800,300,1500],
    [1200,600,1800,300,2400,900,1500,450,2100,750],
    [500,3500,700,2800,400,3200,600,2600,350,3000],
    [2000,500,1500,800,2500,400,1800,600,2200,700],
    [300,2800,500,2200,700,1800,900,1400,1100,1000],
    [1000,3000,500,2500,800,2000,1200,1600,400,2800],
    [600,2600,900,2000,1200,1600,600,2400,800,1800],
    [1500,400,2000,600,2500,350,1800,550,2200,450],
    [400,3200,800,2400,1200,1800,500,2800,700,2000],
    [900,2200,450,2800,650,2400,850,1800,1100,1400]
  ];
  patterns.forEach(function(p,i){
    RETRO_SOUNDS.push({name:'spectrum_'+i,cat:'spectrum',play:function(c,d){
      var o=c.createOscillator(),g=c.createGain();o.connect(g);g.connect(c.destination);
      o.type='square';var t=c.currentTime;
      p.forEach(function(f,j){o.frequency.linearRampToValueAtTime(f,t+j*(d/p.length));});
      g.gain.setValueAtTime(0.06,t);g.gain.linearRampToValueAtTime(0,t+d);
      o.start(t);o.stop(t+d);
    }});
  });
})();

// B) COMMODORE 64 SID (10-19): sawtooth + square combo
(function(){
  var bases=[220,330,440,550,660,196,294,392,494,588];
  bases.forEach(function(b,i){
    RETRO_SOUNDS.push({name:'c64_'+i,cat:'c64',play:function(c,d){
      var t=c.currentTime;
      var o1=c.createOscillator(),o2=c.createOscillator(),g=c.createGain();
      o1.connect(g);o2.connect(g);g.connect(c.destination);
      o1.type='sawtooth';o2.type='square';
      var arp=[b,b*1.25,b*1.5,b*2,b*1.5,b*1.25];
      arp.forEach(function(f,j){
        o1.frequency.setValueAtTime(f,t+j*(d/arp.length));
        o2.frequency.setValueAtTime(f*2,t+j*(d/arp.length));
      });
      g.gain.setValueAtTime(0.04,t);g.gain.linearRampToValueAtTime(0,t+d);
      o1.start(t);o1.stop(t+d);o2.start(t);o2.stop(t+d);
    }});
  });
})();

// C) ATARI 2600 (20-29): low square blips
(function(){
  var freqs=[120,180,90,150,200,110,160,130,170,140];
  freqs.forEach(function(f,i){
    RETRO_SOUNDS.push({name:'atari_'+i,cat:'atari',play:function(c,d){
      var t=c.currentTime;var o=c.createOscillator(),g=c.createGain();
      o.connect(g);g.connect(c.destination);o.type='square';
      for(var j=0;j<8;j++){
        o.frequency.setValueAtTime(f*(1+j*0.3),t+j*(d/8));
        o.frequency.linearRampToValueAtTime(f*(1+j*0.15),t+(j+0.5)*(d/8));
      }
      g.gain.setValueAtTime(0.05,t);g.gain.linearRampToValueAtTime(0,t+d);
      o.start(t);o.stop(t+d);
    }});
  });
})();

// D) AMSTRAD CPC AY-3-8910 (30-39): square + noise envelope
(function(){
  var tones=[440,523,659,784,880,392,494,587,698,831];
  tones.forEach(function(f,i){
    RETRO_SOUNDS.push({name:'amstrad_'+i,cat:'amstrad',play:function(c,d){
      var t=c.currentTime;
      var o=c.createOscillator(),g=c.createGain();
      o.connect(g);g.connect(c.destination);o.type='square';
      o.frequency.setValueAtTime(f,t);
      o.frequency.exponentialRampToValueAtTime(f*0.5,t+d*0.7);
      o.frequency.exponentialRampToValueAtTime(f*0.25,t+d);
      g.gain.setValueAtTime(0.05,t);
      g.gain.setValueAtTime(0.07,t+d*0.1);
      g.gain.linearRampToValueAtTime(0.03,t+d*0.5);
      g.gain.linearRampToValueAtTime(0,t+d);
      o.start(t);o.stop(t+d);
    }});
  });
})();

// E) NES/FAMICOM (40-49): pulse + triangle
(function(){
  var notes=[262,294,330,349,392,440,494,523,587,659];
  notes.forEach(function(f,i){
    RETRO_SOUNDS.push({name:'nes_'+i,cat:'nes',play:function(c,d){
      var t=c.currentTime;
      var o1=c.createOscillator(),o2=c.createOscillator(),g=c.createGain();
      o1.connect(g);o2.connect(g);g.connect(c.destination);
      o1.type='square';o2.type='triangle';
      var seq=[f,f*1.19,f*1.5,f*1.19,f,f*0.75,f,f*1.5];
      seq.forEach(function(n,j){
        o1.frequency.setValueAtTime(n,t+j*(d/seq.length));
        o2.frequency.setValueAtTime(n*0.5,t+j*(d/seq.length));
      });
      g.gain.setValueAtTime(0.04,t);g.gain.linearRampToValueAtTime(0,t+d);
      o1.start(t);o1.stop(t+d);o2.start(t);o2.stop(t+d);
    }});
  });
})();

// F) GAME BOY (50-59): sweep + short chip
(function(){
  var starts=[800,600,1000,500,900,700,1100,550,950,650];
  starts.forEach(function(f,i){
    RETRO_SOUNDS.push({name:'gameboy_'+i,cat:'gameboy',play:function(c,d){
      var t=c.currentTime;var o=c.createOscillator(),g=c.createGain();
      o.connect(g);g.connect(c.destination);o.type='square';
      o.frequency.setValueAtTime(f,t);
      o.frequency.exponentialRampToValueAtTime(f*(i%2?0.25:4),t+d*0.6);
      o.frequency.setValueAtTime(f*1.5,t+d*0.65);
      o.frequency.exponentialRampToValueAtTime(f*0.5,t+d);
      g.gain.setValueAtTime(0.05,t);
      g.gain.setValueAtTime(0.06,t+d*0.05);
      g.gain.linearRampToValueAtTime(0,t+d);
      o.start(t);o.stop(t+d);
    }});
  });
})();

/* ===== RANDOM PLAY ===== */
function playRandomRetroSound(duration){
  duration=duration||1.0;
  var c=_ctx();if(!c)return;
  RETRO_SOUNDS[Math.floor(Math.random()*RETRO_SOUNDS.length)].play(c,duration);
}

/* ===== VOICE COUNTDOWN ===== */
function speakCountdown(n){
  try{
    if(!window.speechSynthesis)return;
    var words={60:'sixty',50:'fifty',40:'forty',30:'thirty',20:'twenty',
      10:'ten',9:'nine',8:'eight',7:'seven',6:'six',5:'five',4:'four',3:'three',2:'two',1:'one'};
    if(!words[n])return;
    var u=new SpeechSynthesisUtterance(words[n]);
    u.rate=0.9;u.pitch=0.8;u.volume=0.4;
    var voices=speechSynthesis.getVoices();
    var en=voices.find(function(v){return v.lang.startsWith('en');});
    if(en)u.voice=en;
    speechSynthesis.speak(u);
  }catch(e){}
}

/* ===== CHIPTUNE SPLASH MUSIC ===== */
var CHIPTUNES=[
  {notes:[262,330,392,523,392,330,262,330,392,523,659,523,392,330,262,330],tempo:180},
  {notes:[196,233,262,277,262,233,196,196,262,311,330,311,262,233,196,233],tempo:150},
  {notes:[440,554,659,880,659,554,440,554,659,880,1047,880,659,554,440,554],tempo:200},
  {notes:[330,392,494,392,330,262,330,392,494,659,494,392,330,262,196,262],tempo:170},
  {notes:[523,494,440,392,440,494,523,659,523,494,440,392,330,262,330,392],tempo:160},
  {notes:[196,262,330,392,440,392,330,262,196,262,330,440,523,440,330,262],tempo:140},
  {notes:[880,784,659,523,440,523,659,784,880,784,659,523,440,392,330,392],tempo:190},
  {notes:[262,294,330,349,392,440,494,523,494,440,392,349,330,294,262,294],tempo:155},
  {notes:[392,494,587,494,392,330,392,494,587,698,587,494,392,330,262,330],tempo:175},
  {notes:[440,523,659,523,440,349,440,523,659,784,659,523,440,349,294,349],tempo:165}
];

function playChiptuneSplash(duration){
  duration=duration||7;
  var c=_ctx();if(!c)return;
  var mel=CHIPTUNES[Math.floor(Math.random()*CHIPTUNES.length)];
  var nt=60/mel.tempo;var t=c.currentTime;var total=0;
  while(total<duration){
    mel.notes.forEach(function(freq,i){
      var start=t+total+i*nt;
      if(start-t>=duration)return;
      var o=c.createOscillator(),g=c.createGain();
      o.connect(g);g.connect(c.destination);o.type='square';
      o.frequency.setValueAtTime(freq,start);
      g.gain.setValueAtTime(0,start);
      g.gain.linearRampToValueAtTime(0.04,start+0.015);
      g.gain.linearRampToValueAtTime(0.025,start+nt*0.5);
      g.gain.linearRampToValueAtTime(0,start+nt*0.9);
      o.start(start);o.stop(start+nt);
    });
    total+=mel.notes.length*nt;
  }
}
