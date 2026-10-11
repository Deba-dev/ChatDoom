"""The two web pages OBS shows (as a Browser Source): payment/Super Chat alerts and chat on screen."""

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>CHATDOOM overlay</title>
<style>
@font-face{font-family:Poppins;font-weight:500;src:url(/fonts/Poppins-Medium.ttf)}
@font-face{font-family:Poppins;font-weight:700;src:url(/fonts/Poppins-Bold.ttf)}
:root{--a1:#8b5cf6;--a2:#22d3ee;--a3:#f472b6}
html,body{margin:0;height:100%;background:transparent;overflow:hidden;color:#fff;
  font-family:Poppins,'Segoe UI','Noto Sans Devanagari',sans-serif}
/* ---------- alerts ---------- */
#alertbox{position:fixed;left:50%;top:48px;transform:translateX(-50%);width:min(900px,94vw)}
.alert{position:relative;isolation:isolate;margin:0 auto;padding:24px 34px;border-radius:28px;text-align:center;
  background:rgba(12,10,32,.88);box-shadow:0 14px 50px rgba(0,0,0,.55),0 0 46px var(--a1);
  animation:pop .75s cubic-bezier(.2,1.5,.4,1) both,floaty 3s ease-in-out .75s infinite}
.alert::before{content:"";position:absolute;inset:-3px;z-index:-1;border-radius:31px;
  background:linear-gradient(120deg,var(--a1),var(--a2),var(--a3),var(--a1));background-size:300% 300%;animation:shift 4s linear infinite}
.alert.out{animation:out .55s ease-in both}
.alert.style-sakura{border-radius:48px;background:linear-gradient(110deg,rgba(47,8,35,.94),rgba(20,10,38,.94));box-shadow:0 14px 48px rgba(0,0,0,.55),0 0 36px #f472b6}
.alert.style-sakura::before{border-radius:52px;background:linear-gradient(120deg,#ff71b8,#ffe0ef,#c15aff,#ff71b8)}
.alert.style-brush{border-radius:8px 42px 8px 42px;background:linear-gradient(105deg,rgba(8,13,30,.97),rgba(25,9,35,.9));box-shadow:0 10px 38px rgba(0,0,0,.6),0 0 24px var(--a2)}
.alert.style-brush::before{border-radius:8px 42px 8px 42px;clip-path:polygon(3% 10%,100% 0,97% 91%,0 100%)}
.alert.style-frame{border-radius:4px;background:rgba(5,9,19,.94);box-shadow:0 0 28px var(--a1)}
.alert.style-frame::before{border-radius:5px;clip-path:polygon(0 0,14% 0,17% 7%,83% 7%,86% 0,100% 0,100% 100%,0 100%)}
.src{font-size:15px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--a2);margin-bottom:2px}
.who{font-size:36px;font-weight:700;line-height:1.25;word-break:break-word}
.amt{background:linear-gradient(90deg,var(--a3),var(--a2));-webkit-background-clip:text;background-clip:text;color:transparent}
.msg{font-size:27px;font-weight:500;margin-top:10px;opacity:.96;word-break:break-word}
.spark{position:absolute;font-size:30px;pointer-events:none;animation:spark 2.2s ease-out forwards}
@keyframes pop{0%{opacity:0;transform:scale(.3) translateY(-60px)}60%{opacity:1;transform:scale(1.07)}100%{opacity:1;transform:scale(1)}}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@keyframes shift{0%{background-position:0% 50%}100%{background-position:300% 50%}}
@keyframes out{to{opacity:0;transform:scale(.85) translateY(-30px)}}
@keyframes spark{0%{opacity:0;transform:translateY(0) scale(.4)}20%{opacity:1}100%{opacity:0;transform:translateY(-120px) scale(1.2) rotate(30deg)}}
/* ---------- now playing ---------- */
#musicbox{position:fixed;left:18px;bottom:18px;display:flex;align-items:center;gap:14px;padding:12px 20px 12px 16px;border-radius:22px;
  background:rgba(12,10,32,.82);box-shadow:0 8px 30px rgba(0,0,0,.45),0 0 26px var(--a1);max-width:min(560px,92vw);
  transform:translateY(130%);opacity:0;transition:transform .6s cubic-bezier(.2,1.2,.4,1),opacity .4s}
#musicbox.on{transform:none;opacity:1}
.eq{display:flex;align-items:flex-end;gap:3px;height:28px}
.eq i{display:block;width:5px;border-radius:3px;background:linear-gradient(var(--a3),var(--a2));height:8px;animation:eq 0.9s ease-in-out infinite}
.eq i:nth-child(2){animation-delay:.15s}.eq i:nth-child(3){animation-delay:.3s}.eq i:nth-child(4){animation-delay:.45s}
#musicbox.paused .eq i{animation-play-state:paused}
.mt{font-size:21px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ma{font-size:15px;font-weight:500;opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mtxt{min-width:0}
@keyframes eq{0%,100%{height:6px}50%{height:28px}}
/* ---------- chat ---------- */
#chatbox{position:fixed;left:14px;right:14px;bottom:14px;display:flex;flex-direction:column;gap:6px;justify-content:flex-end}
.m{align-self:flex-start;max-width:100%;padding:8px 14px;border-radius:15px;background:rgba(10,8,26,.66);font-size:22px;
  font-weight:500;text-shadow:0 1px 3px #000;word-break:break-word;animation:slide .4s cubic-bezier(.2,1.3,.4,1) both}
.m .tag{display:inline-block;font-weight:700;font-size:14px;padding:2px 8px;border-radius:8px;margin-right:8px;color:#06060f;vertical-align:2px}
.m b{margin-right:6px}
.m.style-compact{padding:4px 10px;border-radius:6px;font-size:19px;background:rgba(8,12,22,.72);border-left:3px solid var(--a2)}
.m.style-panel{width:min(100%,560px);padding:10px 14px;border-radius:4px 14px 14px 4px;background:rgba(5,8,18,.88);border-left:4px solid var(--a1)}
.m.style-sakura{border-radius:22px 22px 22px 5px;background:rgba(48,12,42,.76);box-shadow:0 0 14px rgba(244,114,182,.38);border:1px solid rgba(255,174,218,.42)}
.m.old{animation:fade .6s ease-in forwards}
@keyframes slide{from{opacity:0;transform:translateX(-40px)}to{opacity:1;transform:none}}
@keyframes fade{to{opacity:0;transform:translateY(-10px)}}
</style></head>
<body data-mode="__MODE__"><div id="alertbox"></div><div id="chatbox"></div>
<div id="musicbox"><div class="eq"><i></i><i></i><i></i><i></i></div><div class="mtxt"><div class="mt"></div><div class="ma"></div></div></div>
<script>
(function(){
var MODE=document.body.dataset.mode, POLL=window.__POLL||1000, after=-1, cfg={}, queue=[], busy=false;
var COLORS={youtube:'#ff4d4d',twitch:'#9146ff',kick:'#53fc18',tip:'#ffd24d',test:'#22d3ee'};
var LABELS={youtube:'YouTube',twitch:'Twitch',kick:'Kick',tip:'Payment',test:'Test'};
var alertbox=document.getElementById('alertbox'), chatbox=document.getElementById('chatbox');
function applyColors(c){ if(!c||!c.colors) return; var r=document.documentElement.style;
  r.setProperty('--a1',c.colors.a1); r.setProperty('--a2',c.colors.a2); r.setProperty('--a3',c.colors.a3); }
function chime(){ try{ var ac=new (window.AudioContext||window.webkitAudioContext)();
  [660,880,1320].forEach(function(f,i){ var t=ac.currentTime+i*0.12, o=ac.createOscillator(), g=ac.createGain();
    o.type='sine'; o.frequency.value=f; g.gain.setValueAtTime(0.0001,t); g.gain.exponentialRampToValueAtTime(0.25,t+0.02);
    g.gain.exponentialRampToValueAtTime(0.0001,t+0.35); o.connect(g); g.connect(ac.destination); o.start(t); o.stop(t+0.4); }); }catch(e){} }
function sparkle(box){ var s=['✨','💎','🎉','⭐','💜'];
  for(var i=0;i<9;i++){ var n=document.createElement('span'); n.className='spark'; n.textContent=s[i%s.length];
    n.style.left=(5+Math.random()*90)+'%'; n.style.top=(30+Math.random()*50)+'%'; n.style.animationDelay=(Math.random()*0.8)+'s'; box.appendChild(n); } }
function next(){
  if(!queue.length){ busy=false; return; }
  busy=true; var e=queue.shift();
  var box=document.createElement('div'); box.className='alert style-'+(cfg.alertStyle||'neon');
  var src=document.createElement('div'); src.className='src'; src.textContent=LABELS[e.platform]||e.platform||''; box.appendChild(src);
  var who=document.createElement('div'); who.className='who';
  var nm=document.createElement('span'); nm.className='name'; nm.textContent=e.name||'Someone';
  who.appendChild(nm);
  var actions={membership:' became a member',subscriber:' subscribed',follow:' followed',
    subscription:' subscribed',gift:' gifted',raid:' raided'};
  if(actions[e.category]){
    who.appendChild(document.createTextNode(actions[e.category]));
    if(e.amount){ var detail=document.createElement('span'); detail.className='amt'; detail.textContent=' · '+e.amount; who.appendChild(detail); }
  } else {
    var mid=document.createTextNode(' sent '); var am=document.createElement('span'); am.className='amt'; am.textContent=e.amount||'';
    who.appendChild(mid); who.appendChild(am);
  }
  box.appendChild(who);
  var text=(cfg.showMessage===false)?'':(e.message||'');
  if(text){ var m=document.createElement('div'); m.className='msg'; m.textContent=text; box.appendChild(m); }
  alertbox.appendChild(box); sparkle(box);
  if(cfg.soundUrl){ var sound=new Audio(cfg.soundUrl); sound.volume=0.8; sound.play().catch(function(){}); }
  else if(cfg.sound) chime();
  var ms=(cfg.seconds||8)*1000+Math.min(8000,text.length*60);
  setTimeout(function(){ box.classList.add('out'); setTimeout(function(){ box.remove(); setTimeout(next,300); },550); },ms);
}
function addChat(e){
  var m=document.createElement('div'); m.className='m style-'+(cfg.chatStyle||'glass');
  var tag=document.createElement('span'); tag.className='tag'; tag.style.background=COLORS[e.platform]||'#aaa'; tag.textContent=(LABELS[e.platform]||e.platform||'').toUpperCase();
  var b=document.createElement('b'); b.textContent=e.name||''; var t=document.createElement('span'); t.textContent=e.text||'';
  m.appendChild(tag); m.appendChild(b); m.appendChild(t); chatbox.appendChild(m);
  while(chatbox.children.length>(cfg.maxLines||8)) chatbox.removeChild(chatbox.firstChild);
  setTimeout(function(){ m.classList.add('old'); setTimeout(function(){ m.remove(); },650); },(cfg.chatSeconds||20)*1000);
}
var musicbox=document.getElementById('musicbox');
function showMusic(st){
  if(!st||!st.title||!st.playing){ musicbox.classList.remove('on'); return; }
  musicbox.querySelector('.mt').textContent=st.title; musicbox.querySelector('.ma').textContent=st.artist||'';
  musicbox.querySelector('.ma').style.display=st.artist?'block':'none'; musicbox.classList.add('on');
}
function tick(){
  fetch('/poll?type='+MODE+'&after='+after,{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){
    cfg=j.cfg||{}; applyColors(cfg);
    if(MODE==='music'){ showMusic(j.state); return; }
    if(after<0){ after=j.latest; }
    else { j.events.forEach(function(e){ after=Math.max(after,e.id); if(MODE==='alert'){
      var category=e.category||(e.platform==='tip'?'tip':(e.amount?'superchat':'other'));
      if((category==='tip'&&cfg.showTips===false)||(category==='superchat'&&cfg.showSuperchats===false)||
         (category==='membership'&&cfg.showMemberships===false)||(category==='subscriber'&&cfg.showSubscribers===false)||
         (category==='follow'&&cfg.showFollows===false)||(category==='subscription'&&cfg.showSubscriptions===false)||
         (category==='gift'&&cfg.showSubscriptions===false)||
         (category==='raid'&&cfg.showRaids===false)) return;
      queue.push(e); if(!busy) next();
    } else addChat(e); }); }
  }).catch(function(){}).then(function(){ setTimeout(tick,POLL); });
}
tick();
})();
</script></body></html>
"""

INDEX = """<!doctype html><meta charset="utf-8"><title>CHATDOOM overlays</title>
<body style="font:16px sans-serif;background:#10101c;color:#eee;padding:30px">
<h2>CHATDOOM overlays</h2><p style="opacity:.7">CHATDOOM (BETA) by itsmeblitz</p><p>Add these as <b>Browser sources</b> in OBS:</p>
<ul><li><a style="color:#8ab4ff" href="/alert">/alert</a> payment, subscription, and channel-event alerts</li>
<li><a style="color:#8ab4ff" href="/chat">/chat</a> chat on screen</li>
<li><a style="color:#8ab4ff" href="/music">/music</a> now playing</li></ul></body>"""


def page(mode):
    return PAGE.replace("__MODE__", mode)
