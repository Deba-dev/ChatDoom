"""The web pages OBS shows (as a Browser Source): payment/Super Chat alerts, chat, now playing and memes on screen."""

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
#alertbox.pos-top-left,#alertbox.pos-mid-left,#alertbox.pos-bottom-left{left:32px;transform:none;width:min(620px,94vw)}
#alertbox.pos-top-right,#alertbox.pos-mid-right,#alertbox.pos-bottom-right{left:auto;right:32px;transform:none;width:min(620px,94vw)}
#alertbox.pos-mid-center,#alertbox.pos-mid-left,#alertbox.pos-mid-right{top:50%}
#alertbox.pos-mid-center{transform:translate(-50%,-50%)}
#alertbox.pos-mid-left,#alertbox.pos-mid-right{transform:translateY(-50%)}
#alertbox.pos-bottom-center,#alertbox.pos-bottom-left,#alertbox.pos-bottom-right{top:auto;bottom:48px}
.alert{--in:pop;--idle:floaty;--out:out;position:relative;isolation:isolate;margin:0 auto;padding:24px 34px;border-radius:28px;text-align:center;
  background:rgba(12,10,32,.88);box-shadow:0 14px 50px rgba(0,0,0,.55),0 0 46px var(--a1);
  animation:var(--in) .75s cubic-bezier(.2,1.3,.4,1) both,var(--idle) 3s ease-in-out .75s infinite}
.alert::before{content:"";position:absolute;inset:-3px;z-index:-1;border-radius:31px;
  background:linear-gradient(120deg,var(--a1),var(--a2),var(--a3),var(--a1));background-size:300% 300%;animation:shift 4s linear infinite}
.alert.out{animation:var(--out) .55s ease-in both}
.alert.style-sakura{border-radius:48px;background:linear-gradient(110deg,rgba(47,8,35,.94),rgba(20,10,38,.94));box-shadow:0 14px 48px rgba(0,0,0,.55),0 0 36px #f472b6}
.alert.style-sakura::before{border-radius:52px;background:linear-gradient(120deg,#ff71b8,#ffe0ef,#c15aff,#ff71b8)}
.alert.style-brush{border-radius:8px 42px 8px 42px;background:linear-gradient(105deg,rgba(8,13,30,.97),rgba(25,9,35,.9));box-shadow:0 10px 38px rgba(0,0,0,.6),0 0 24px var(--a2)}
.alert.style-brush::before{border-radius:8px 42px 8px 42px;clip-path:polygon(3% 10%,100% 0,97% 91%,0 100%)}
.alert.style-frame{border-radius:4px;background:rgba(5,9,19,.94);box-shadow:0 0 28px var(--a1)}
.alert.style-frame::before{border-radius:5px;clip-path:polygon(0 0,14% 0,17% 7%,83% 7%,86% 0,100% 0,100% 100%,0 100%)}
.alert.style-glass{background:rgba(255,255,255,.12);backdrop-filter:blur(14px);box-shadow:0 14px 44px rgba(0,0,0,.4)}
.alert.style-glass::before{opacity:.35}
.alert.style-comic{border-radius:6px;background:#fff7d6;color:#14131f;box-shadow:9px 9px 0 #14131f;transform-origin:center}
.alert.style-comic::before{inset:-5px;border-radius:9px;background:#14131f}
.alert.style-comic .src{color:#d11f4a}.alert.style-comic .msg{color:#2c2a3d}
.alert.style-cyber{border-radius:0;background:linear-gradient(rgba(34,211,238,.09) 1px,transparent 1px) 0 0/100% 7px,rgba(3,8,20,.95);box-shadow:0 0 34px var(--a2);clip-path:polygon(0 0,calc(100% - 26px) 0,100% 26px,100% 100%,26px 100%,0 calc(100% - 26px))}
.alert.style-cyber::before{display:none}
.alert.style-minimal{border-radius:14px;background:rgba(10,12,20,.92);box-shadow:0 10px 28px rgba(0,0,0,.45)}
.alert.style-minimal::before{inset:auto 0 0 0;height:4px;border-radius:0 0 14px 14px}
.alert.style-arcade{border-radius:0;background:#100c2e;box-shadow:0 0 0 6px #100c2e,0 0 0 12px var(--a2),0 0 0 18px #100c2e,0 0 26px 18px var(--a1)}
.alert.style-arcade::before{display:none}
.alert.style-royal{border-radius:14px;background:linear-gradient(135deg,rgba(38,20,4,.97),rgba(18,10,28,.97));box-shadow:0 12px 46px rgba(0,0,0,.6),0 0 40px #e9b949}
.alert.style-royal::before{background:linear-gradient(120deg,#8a5a12,#ffe9a8,#c9962e,#ffe9a8,#8a5a12);background-size:300% 300%;border-radius:17px}
.alert.style-royal .src{color:#ffd978}.alert.style-royal .amt{background:linear-gradient(90deg,#ffe9a8,#e9b949);-webkit-background-clip:text;background-clip:text}
.alert.style-ribbon{border-radius:0;background:linear-gradient(90deg,var(--a1),var(--a3));clip-path:polygon(0 0,100% 0,96% 50%,100% 100%,0 100%,4% 50%);padding:24px 70px}
.alert.style-ribbon::before{display:none}.alert.style-ribbon .src{color:#fff}.alert.style-ribbon .amt{background:none;color:#fff;-webkit-text-fill-color:#fff}
.alert.style-paper{border-radius:3px;background:#fdf6e3;color:#2b2438;box-shadow:0 12px 30px rgba(0,0,0,.45);rotate:-1.4deg}
.alert.style-paper::before{inset:-10px auto auto 50%;width:120px;height:26px;margin-left:-60px;border-radius:2px;background:rgba(255,226,130,.85)}
.alert.style-paper .src{color:#a33f6a}.alert.style-paper .msg{color:#463c55}
.alert.style-terminal{border-radius:8px;background:rgba(2,10,4,.96);color:#7dff9b;text-align:left;box-shadow:0 0 26px rgba(61,255,120,.35);text-shadow:0 0 8px rgba(61,255,120,.6)}
.alert.style-terminal::before{inset:-2px;border-radius:9px;background:#1f7a3a}
.alert.style-terminal .src{color:#b9ffc9}.alert.style-terminal .src::before{content:"> "}
.alert.style-terminal .amt{background:none;color:#eaffef;-webkit-text-fill-color:#eaffef}
.alert.style-bubble{border-radius:60px;background:linear-gradient(135deg,var(--a3),var(--a1));box-shadow:0 14px 40px rgba(0,0,0,.4)}
.alert.style-bubble::before{display:none}.alert.style-bubble .src{color:#fff}.alert.style-bubble .amt{background:none;color:#fff;-webkit-text-fill-color:#fff}
.alert.style-ticket{border-radius:12px;background:radial-gradient(circle 18px at 0 50%,transparent 97%,#17122f) left/51% 100% no-repeat,radial-gradient(circle 18px at 100% 50%,transparent 97%,#17122f) right/51% 100% no-repeat;box-shadow:none;filter:drop-shadow(0 10px 22px rgba(0,0,0,.55))}
.alert.style-ticket::before{display:none}
.alert.style-holo{border-radius:20px;background:linear-gradient(115deg,rgba(34,211,238,.2),rgba(168,85,247,.22),rgba(244,114,182,.2));box-shadow:0 0 30px var(--a2),inset 0 0 28px rgba(255,255,255,.1)}
.alert.style-holo::before{opacity:.55}
.alert.style-lava{border-radius:22px;background:linear-gradient(180deg,rgba(40,6,0,.96),rgba(90,14,0,.94));box-shadow:0 10px 40px rgba(0,0,0,.6),0 0 44px #ff5a1f}
.alert.style-lava::before{background:linear-gradient(120deg,#ff2d00,#ffb300,#ff5a1f,#ff2d00);background-size:300% 300%;border-radius:25px}
.alert.style-lava .src{color:#ffc266}.alert.style-lava .amt{background:linear-gradient(90deg,#ffd166,#ff7a1f);-webkit-background-clip:text;background-clip:text}
.alert.style-ice{border-radius:18px;background:linear-gradient(160deg,rgba(214,244,255,.22),rgba(40,92,140,.55));backdrop-filter:blur(10px);box-shadow:0 10px 36px rgba(0,0,0,.45),0 0 34px #8fe3ff}
.alert.style-ice::before{background:linear-gradient(120deg,#e6fbff,#6fcdf5,#ffffff,#e6fbff);background-size:300% 300%;border-radius:21px}
.alert.style-ice .src{color:#d8f7ff}
/* Every look keeps its own dark or solid background, so the moving colour layer is only a thin ring and the text stays readable. */
.alert:not(.style-minimal):not(.style-paper)::before{  padding:3px;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
.alert.style-comic::before{padding:5px}
.in-pop{--in:pop}.in-left{--in:inleft}.in-right{--in:inright}.in-drop{--in:indrop}.in-rise{--in:inrise}.in-flip{--in:inflip}.in-zoom{--in:inzoom}
.in-spin{--in:inspin}.in-bounce{--in:inbounce}.in-glitch{--in:inglitch}.in-blur{--in:inblur}.in-swing{--in:inswing}.in-unfold{--in:inunfold}.in-warp{--in:inwarp}
.idle-float{--idle:floaty}.idle-pulse{--idle:ipulse}.idle-wobble{--idle:iwobble}.idle-glow{--idle:iglow}.idle-tilt{--idle:itilt}.idle-breathe{--idle:ibreathe}.idle-jitter{--idle:ijitter}.idle-none{--idle:none}
.exit-out{--out:out}.exit-fade{--out:xfade}.exit-left{--out:xleft}.exit-right{--out:xright}.exit-drop{--out:xdrop}.exit-rise{--out:xrise}.exit-zoom{--out:xzoom}.exit-spin{--out:xspin}.exit-blur{--out:xblur}.exit-flip{--out:xflip}
.alert img.pic{display:block;margin:0 auto 12px;max-width:100%;max-height:240px;border-radius:14px}
.alert.lay-side{display:flex;align-items:center;gap:22px;text-align:left}.alert.lay-side img.pic{margin:0;max-width:38%}.alert.lay-side .words{min-width:0;flex:1}
.alert.lay-behind img.pic{position:absolute;inset:0;z-index:-1;width:100%;height:100%;max-height:none;margin:0;object-fit:cover;opacity:.4}
.ch{display:inline-block;white-space:pre}
.t-wave .ch{animation:twave 1.4s ease-in-out infinite;animation-delay:calc(var(--i)*70ms)}
.t-bounce .ch{animation:tbounce .9s ease infinite;animation-delay:calc(var(--i)*60ms)}
.t-type .ch{opacity:0;animation:ttype .01s linear forwards;animation-delay:calc(.5s + var(--i)*65ms)}
.t-rainbow .ch{animation:trainbow 2.4s linear infinite;animation-delay:calc(var(--i)*-120ms)}
.t-shake .ch{animation:tshake .35s linear infinite;animation-delay:calc(var(--i)*-40ms)}
.t-glow .ch{animation:tglow 1.8s ease-in-out infinite}
.t-pop .ch{animation:tpop .5s cubic-bezier(.2,1.6,.4,1) both;animation-delay:calc(.35s + var(--i)*45ms)}
.t-flicker .ch{animation:tflicker 2.2s linear infinite;animation-delay:calc(var(--i)*-310ms)}
.t-slide .ch{animation:tslide .5s ease-out both;animation-delay:calc(.35s + var(--i)*40ms)}
.src{font-size:15px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--a2);margin-bottom:2px}
.who{font-size:36px;font-weight:700;line-height:1.25;word-break:break-word}
.amt{background:linear-gradient(90deg,var(--a3),var(--a2));-webkit-background-clip:text;background-clip:text;color:transparent}
.msg{font-size:27px;font-weight:500;margin-top:10px;opacity:.96;word-break:break-word}
.spark{position:absolute;font-size:30px;pointer-events:none;animation:spark 2.2s ease-out forwards}
.spark.fall{animation-name:sparkfall}
.spark.bit{width:11px;height:16px;border-radius:2px}
@keyframes pop{0%{opacity:0;transform:scale(.3) translateY(-60px)}60%{opacity:1;transform:scale(1.07)}100%{opacity:1;transform:scale(1)}}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@keyframes shift{0%{background-position:0% 50%}100%{background-position:300% 50%}}
@keyframes out{to{opacity:0;transform:scale(.85) translateY(-30px)}}
@keyframes spark{0%{opacity:0;transform:translateY(0) scale(.4)}20%{opacity:1}100%{opacity:0;transform:translateY(-120px) scale(1.2) rotate(30deg)}}
@keyframes sparkfall{0%{opacity:0;transform:translateY(-90px) rotate(0)}15%{opacity:1}100%{opacity:0;transform:translateY(130px) rotate(260deg)}}
@keyframes inleft{from{opacity:0;transform:translateX(-120%)}to{opacity:1;transform:none}}
@keyframes inright{from{opacity:0;transform:translateX(120%)}to{opacity:1;transform:none}}
@keyframes indrop{from{opacity:0;transform:translateY(-140%)}to{opacity:1;transform:none}}
@keyframes inrise{from{opacity:0;transform:translateY(140%)}to{opacity:1;transform:none}}
@keyframes inflip{from{opacity:0;transform:perspective(900px) rotateX(-95deg)}to{opacity:1;transform:perspective(900px) rotateX(0)}}
@keyframes inzoom{from{opacity:0;transform:scale(2.4)}to{opacity:1;transform:none}}
@keyframes inspin{from{opacity:0;transform:rotate(-540deg) scale(.1)}to{opacity:1;transform:none}}
@keyframes inbounce{0%{opacity:0;transform:translateY(-130%)}55%{opacity:1;transform:translateY(0)}72%{transform:translateY(-16%)}88%{transform:translateY(0)}94%{transform:translateY(-5%)}100%{opacity:1;transform:none}}
@keyframes inglitch{0%{opacity:0;transform:translateX(-30px) skewX(30deg)}25%{opacity:1;transform:translateX(24px) skewX(-22deg)}50%{transform:translateX(-14px) skewX(12deg)}75%{transform:translateX(8px) skewX(-6deg)}100%{opacity:1;transform:none}}
@keyframes inblur{from{opacity:0;filter:blur(26px);transform:scale(1.12)}to{opacity:1;filter:blur(0);transform:none}}
@keyframes inswing{0%{opacity:0;transform:rotate(-24deg);transform-origin:top center}55%{opacity:1;transform:rotate(11deg)}80%{transform:rotate(-5deg)}100%{opacity:1;transform:none}}
@keyframes inunfold{from{opacity:0;transform:scaleX(.02)}to{opacity:1;transform:none}}
@keyframes inwarp{from{opacity:0;transform:scale(.2) skewY(24deg);filter:hue-rotate(180deg)}to{opacity:1;transform:none;filter:none}}
@keyframes ipulse{0%,100%{transform:scale(1)}50%{transform:scale(1.04)}}
@keyframes iwobble{0%,100%{transform:rotate(-1.4deg)}50%{transform:rotate(1.4deg)}}
@keyframes iglow{0%,100%{filter:brightness(1)}50%{filter:brightness(1.25)}}
@keyframes itilt{0%,100%{transform:perspective(900px) rotateY(-6deg)}50%{transform:perspective(900px) rotateY(6deg)}}
@keyframes ibreathe{0%,100%{opacity:1}50%{opacity:.84}}
@keyframes ijitter{0%,100%{transform:none}25%{transform:translate(1px,-1px)}50%{transform:translate(-1px,1px)}75%{transform:translate(1px,1px)}}
@keyframes xfade{to{opacity:0}}
@keyframes xleft{to{opacity:0;transform:translateX(-120%)}}
@keyframes xright{to{opacity:0;transform:translateX(120%)}}
@keyframes xdrop{to{opacity:0;transform:translateY(140%)}}
@keyframes xrise{to{opacity:0;transform:translateY(-140%)}}
@keyframes xzoom{to{opacity:0;transform:scale(.1)}}
@keyframes xspin{to{opacity:0;transform:rotate(360deg) scale(.1)}}
@keyframes xblur{to{opacity:0;filter:blur(24px)}}
@keyframes xflip{to{opacity:0;transform:perspective(900px) rotateX(95deg)}}
@keyframes twave{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}
@keyframes tbounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-14px)}}
@keyframes ttype{to{opacity:1}}
@keyframes trainbow{0%{color:var(--a3);filter:hue-rotate(0)}100%{color:var(--a3);filter:hue-rotate(360deg)}}
@keyframes tshake{0%,100%{transform:translate(0,0)}25%{transform:translate(1px,-2px)}75%{transform:translate(-2px,1px)}}
@keyframes tglow{0%,100%{text-shadow:0 0 4px var(--a2)}50%{text-shadow:0 0 18px var(--a2),0 0 34px var(--a1)}}
@keyframes tpop{from{opacity:0;transform:scale(0)}to{opacity:1;transform:none}}
@keyframes tflicker{0%,18%,22%,62%,66%,100%{opacity:1}20%,64%{opacity:.25}}
@keyframes tslide{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
/* ---------- skins and motion shared by chat, now playing, memes and widgets ---------- */
.fx.fx{--in:pop;--idle:none;--out:xfade;animation:var(--in) .6s cubic-bezier(.2,1.2,.4,1) both,var(--idle) 3s ease-in-out .6s infinite}
.fx.fx.out{animation:var(--out) .5s ease-in both}
.in-nudge{--in:slide}
.skin.skin-glass{background:rgba(255,255,255,.13);backdrop-filter:blur(12px);box-shadow:0 8px 24px rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.22)}
.skin.skin-compact{border-radius:6px;background:rgba(8,12,22,.76);box-shadow:none;border-left:3px solid var(--a2)}
.skin.skin-panel{border-radius:4px 14px 14px 4px;background:rgba(5,8,18,.9);box-shadow:0 6px 20px rgba(0,0,0,.4);border-left:4px solid var(--a1)}
.skin.skin-neon{border-radius:16px;background:rgba(12,10,32,.9);border:2px solid var(--a2);box-shadow:0 0 16px var(--a1),inset 0 0 12px rgba(139,92,246,.25)}
.skin.skin-sakura{border-radius:22px 22px 22px 6px;background:rgba(48,12,42,.82);border:1px solid rgba(255,174,218,.5);box-shadow:0 0 14px rgba(244,114,182,.4)}
.skin.skin-brush{border-radius:6px 24px 6px 24px;background:linear-gradient(105deg,rgba(8,13,30,.96),rgba(25,9,35,.9));box-shadow:0 8px 22px rgba(0,0,0,.5),0 0 14px var(--a2)}
.skin.skin-frame{border-radius:3px;background:rgba(5,9,19,.94);border:2px solid var(--a1);box-shadow:0 0 16px var(--a1)}
.skin.skin-comic{border-radius:5px;background:#fff7d6;color:#14131f;border:3px solid #14131f;box-shadow:5px 5px 0 #14131f;text-shadow:none}
.skin.skin-cyber{border-radius:0;background:linear-gradient(rgba(34,211,238,.09) 1px,transparent 1px) 0 0/100% 6px,rgba(3,8,20,.95);box-shadow:0 0 16px var(--a2);clip-path:polygon(0 0,calc(100% - 12px) 0,100% 12px,100% 100%,12px 100%,0 calc(100% - 12px))}
.skin.skin-minimal{border-radius:10px;background:rgba(10,12,20,.9);box-shadow:0 6px 16px rgba(0,0,0,.4)}
.skin.skin-arcade{border-radius:0;background:#100c2e;border:3px solid var(--a2);box-shadow:0 0 0 3px #100c2e,0 0 12px 3px var(--a1)}
.skin.skin-royal{border-radius:10px;background:linear-gradient(135deg,rgba(38,20,4,.97),rgba(18,10,28,.97));border:2px solid #e9b949;box-shadow:0 0 16px rgba(233,185,73,.55)}
.skin.skin-ribbon{border-radius:0;background:linear-gradient(90deg,var(--a1),var(--a3));clip-path:polygon(0 0,100% 0,98% 50%,100% 100%,0 100%,2% 50%);box-shadow:none}
.skin.skin-paper{border-radius:3px;background:#fdf6e3;color:#2b2438;box-shadow:0 8px 18px rgba(0,0,0,.4);text-shadow:none}
.skin.skin-terminal{border-radius:6px;background:rgba(2,10,4,.96);color:#7dff9b;border:1px solid #1f7a3a;box-shadow:0 0 14px rgba(61,255,120,.3);text-shadow:0 0 6px rgba(61,255,120,.6)}
.skin.skin-bubble{border-radius:30px;background:linear-gradient(135deg,var(--a3),var(--a1));box-shadow:0 8px 20px rgba(0,0,0,.35)}
.skin.skin-ticket{border-radius:10px;background:#17122f;border:2px dashed rgba(255,255,255,.3);box-shadow:0 8px 18px rgba(0,0,0,.45)}
.skin.skin-holo{border-radius:14px;background:linear-gradient(115deg,rgba(34,211,238,.22),rgba(168,85,247,.24),rgba(244,114,182,.22));border:1px solid rgba(255,255,255,.35);box-shadow:0 0 16px var(--a2)}
.skin.skin-lava{border-radius:14px;background:linear-gradient(180deg,rgba(40,6,0,.96),rgba(90,14,0,.94));border:2px solid #ff5a1f;box-shadow:0 0 16px #ff5a1f}
.skin.skin-ice{border-radius:12px;background:linear-gradient(160deg,rgba(214,244,255,.22),rgba(40,92,140,.6));backdrop-filter:blur(8px);border:1px solid #bfefff;box-shadow:0 0 14px #8fe3ff}
.skin.skin-plain{background:none;box-shadow:none;border:none;padding-left:0;padding-right:0;text-shadow:0 0 3px #000,0 1px 4px #000,0 0 10px #000}
/* ---------- now playing ---------- */
#musicbox{position:fixed;left:18px;bottom:18px;display:flex;align-items:center;gap:14px;padding:12px 20px 12px 16px;border-radius:22px;
  background:rgba(12,10,32,.82);box-shadow:0 8px 30px rgba(0,0,0,.45),0 0 26px var(--a1);max-width:min(560px,92vw);
  transform:translateY(130%);opacity:0;transition:transform .6s cubic-bezier(.2,1.2,.4,1),opacity .4s}
#musicbox.on{transform:none;opacity:1}
#musicbox.at-bottom-right{left:auto;right:18px}
#musicbox.at-top-left{bottom:auto;top:18px}
#musicbox.at-top-right{bottom:auto;top:18px;left:auto;right:18px}
#musicbox.no-eq .eq{display:none}
.eq{display:flex;align-items:flex-end;gap:3px;height:28px}
.eq i{display:block;width:5px;border-radius:3px;background:linear-gradient(var(--a3),var(--a2));height:8px;animation:eq 0.9s ease-in-out infinite}
.eq i:nth-child(2){animation-delay:.15s}.eq i:nth-child(3){animation-delay:.3s}.eq i:nth-child(4){animation-delay:.45s}
#musicbox.paused .eq i{animation-play-state:paused}
.mt{font-size:21px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ma{font-size:15px;font-weight:500;opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mtxt{min-width:0;overflow:hidden}
.mp{font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--a2)}
.emote{height:1.5em;vertical-align:middle}
.mt.marq{display:inline-block;overflow:visible;text-overflow:clip;animation:marq 12s linear infinite}
@keyframes marq{0%,12%{transform:translateX(0)}88%,100%{transform:translateX(-55%)}}
@keyframes eq{0%,100%{height:6px}50%{height:28px}}
/* ---------- chat ---------- */
#chatbox{position:fixed;left:14px;right:14px;bottom:14px;display:flex;flex-direction:column;gap:6px;justify-content:flex-end}
.m{align-self:flex-start;max-width:100%;padding:8px 14px;border-radius:15px;background:rgba(10,8,26,.66);font-size:22px;
  font-weight:500;text-shadow:0 1px 3px #000;word-break:break-word;animation:slide .4s cubic-bezier(.2,1.3,.4,1) both}
.m .tag{display:inline-block;font-weight:700;font-size:14px;padding:2px 8px;border-radius:8px;margin-right:8px;color:#06060f;vertical-align:2px}
.m b{margin-right:6px}
.m .tag.dot{width:10px;height:10px;padding:0;border-radius:50%;vertical-align:1px}
.m .tm{font-size:.7em;opacity:.65;margin-right:7px}
.m.style-compact{padding:4px 10px;border-radius:6px;font-size:19px;background:rgba(8,12,22,.72);border-left:3px solid var(--a2)}
.m.style-panel{width:min(100%,560px);padding:10px 14px;border-radius:4px 14px 14px 4px;background:rgba(5,8,18,.88);border-left:4px solid var(--a1)}
.m.style-sakura{border-radius:22px 22px 22px 5px;background:rgba(48,12,42,.76);box-shadow:0 0 14px rgba(244,114,182,.38);border:1px solid rgba(255,174,218,.42)}
.m.old{animation:fade .6s ease-in forwards}
#chatbox.edge-top{top:14px;bottom:auto;justify-content:flex-start}
#chatbox.new-start{flex-direction:column-reverse}
#chatbox.edge-top.new-start{justify-content:flex-end}
#chatbox.align-center{align-items:center;text-align:center}
#chatbox.align-center .m{align-self:center}
#chatbox.align-right{align-items:flex-end;text-align:right}
#chatbox.align-right .m{align-self:flex-end}
/* ---------- memes ---------- */
#memebox{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;padding:24px;box-sizing:border-box}
#memebox.at-top-center,#memebox.at-top-left,#memebox.at-top-right{align-items:flex-start}
#memebox.at-bottom-center,#memebox.at-bottom-left,#memebox.at-bottom-right{align-items:flex-end}
#memebox.at-top-left,#memebox.at-bottom-left{justify-content:flex-start}
#memebox.at-top-right,#memebox.at-bottom-right{justify-content:flex-end}
.meme .cap.skin{padding:8px 18px}
.meme{position:relative;display:flex;flex-direction:column;align-items:center;gap:12px;animation:pop .6s cubic-bezier(.2,1.5,.4,1) both}
.meme img{max-width:86vw;max-height:72vh;border-radius:18px;box-shadow:0 14px 50px rgba(0,0,0,.55),0 0 34px var(--a1)}
.meme .cap{max-width:86vw;font-size:34px;font-weight:700;text-align:center;word-break:break-word;
  text-shadow:0 2px 6px #000,0 0 18px var(--a1)}
.meme .by{font-size:16px;font-weight:500;opacity:.85;text-shadow:0 1px 3px #000}
.meme.out{animation:out .5s ease-in both}
/* ---------- widgets: counters, poll, giveaway ---------- */
body[data-mode="preview"]{background:#0b0d17 radial-gradient(circle at 50% 0,#1b2040,#0b0d17 70%)}
body[data-mode="preview"] #alertbox{zoom:.62}
body[data-mode="preview"].show-widgets #widgets{display:block}
body[data-mode="preview"].show-widgets,body[data-mode="preview"].show-chat,body[data-mode="preview"].show-music,body[data-mode="preview"].show-meme{zoom:.6}
#widgets{position:fixed;inset:18px;display:none;pointer-events:none}
body[data-mode="widgets"] #widgets{display:block}
.counters{position:absolute;left:0;top:0;display:flex;flex-direction:column;gap:8px}
.counter{display:flex;align-items:center;gap:12px;padding:8px 16px;border-radius:16px;background:rgba(12,10,32,.82);
  box-shadow:0 6px 24px rgba(0,0,0,.45),0 0 18px var(--a1);font-size:22px;font-weight:700;animation:slide .4s both}
.counter .n{min-width:44px;text-align:center;padding:2px 10px;border-radius:10px;background:linear-gradient(90deg,var(--a1),var(--a2));color:#08080f}
.counter.bump .n{animation:bump .5s}
.panel{position:absolute;right:0;width:min(440px,92vw);padding:16px 20px;border-radius:20px;background:rgba(12,10,32,.86);
  box-shadow:0 10px 36px rgba(0,0,0,.5),0 0 26px var(--a1);animation:pop .6s cubic-bezier(.2,1.5,.4,1) both}
.panel h3{margin:0 0 10px;font-size:22px;line-height:1.25;word-break:break-word}
.panel .meta{font-size:15px;opacity:.8;margin-top:8px}
.opt{position:relative;margin:7px 0;padding:7px 12px;border-radius:12px;background:rgba(255,255,255,.08);overflow:hidden;font-size:18px;font-weight:600}
.opt .bar{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,var(--a1),var(--a2));opacity:.55;transition:width .6s ease}
.opt span{position:relative}
.opt .v{float:right;position:relative}
.goals{position:absolute;left:0;bottom:0;display:flex;flex-direction:column;gap:9px;width:min(440px,92vw)}
.goal{padding:9px 15px;border-radius:15px;background:rgba(12,10,32,.84);box-shadow:0 6px 24px rgba(0,0,0,.45),0 0 16px var(--a1)}
.goal .gl{display:flex;justify-content:space-between;gap:12px;font-size:18px;font-weight:700}
.goal .track{height:13px;margin-top:6px;border-radius:7px;background:rgba(255,255,255,.12);overflow:hidden}
.goal .fill{height:100%;border-radius:7px;background:linear-gradient(90deg,var(--a1),var(--a2));transition:width .7s ease}
.latest{position:absolute;right:0;bottom:0;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
#widgets.side-left .panel{right:auto;left:0}
#widgets.c-top-right .counters,#widgets.c-bottom-right .counters{left:auto;right:0}
#widgets.c-bottom-left .counters,#widgets.c-bottom-right .counters{top:auto;bottom:0}
#widgets.g-top-left .goals,#widgets.g-top-right .goals{bottom:auto;top:0}
#widgets.g-top-right .goals,#widgets.g-bottom-right .goals{left:auto;right:0}
#widgets.l-top-left .latest,#widgets.l-top-right .latest{bottom:auto;top:0}
#widgets.l-top-left .latest,#widgets.l-bottom-left .latest{right:auto;left:0;align-items:flex-start}
.late{padding:6px 13px;border-radius:12px;background:rgba(12,10,32,.82);font-size:17px;font-weight:600}
.late span{opacity:.7;font-weight:500;margin-right:7px}
.winner{font-size:30px;font-weight:700;background:linear-gradient(90deg,var(--a3),var(--a2));-webkit-background-clip:text;background-clip:text;color:transparent}
@keyframes bump{0%{transform:scale(1)}40%{transform:scale(1.35)}100%{transform:scale(1)}}
@keyframes slide{from{opacity:0;transform:translateX(-40px)}to{opacity:1;transform:none}}
@keyframes fade{to{opacity:0;transform:translateY(-10px)}}
</style></head>
<body data-mode="__MODE__"><div id="alertbox"></div><div id="chatbox"></div><div id="memebox"></div>
<div id="widgets"><div class="counters"></div><div class="panel" id="pollbox" hidden></div><div class="panel" id="betbox" hidden></div><div class="panel" id="givebox" hidden></div><div class="panel" id="queuebox" hidden></div><div class="goals"></div><div class="latest"></div></div>
<div id="musicbox"><div class="eq"><i></i><i></i><i></i><i></i></div><div class="mtxt"><div class="mp"></div><div class="mt"></div><div class="ma"></div></div></div>
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
var FX={sparkles:['✨','💎','⭐','💜'],hearts:['💖','💘','💕','❤️'],stars:['⭐','🌟','💫'],money:['💸','💰','🪙','💵'],fire:['🔥','🔥','✨'],
  party:['🎉','🎊','🥳','🎈'],snow:['❄️','❅','❆'],flowers:['🌸','🌺','🌼','🌷'],bolts:['⚡','⚡','✨']};
var FALLING={snow:1,flowers:1,money:1};
function effect(box,kind){
  if(kind==='none') return;
  if(kind==='confetti'){ var cols=['--a1','--a2','--a3'];
    for(var c=0;c<26;c++){ var b=document.createElement('span'); b.className='spark fall bit'; b.style.background='var('+cols[c%3]+')';
      b.style.left=(2+Math.random()*96)+'%'; b.style.top=(Math.random()*30)+'%'; b.style.animationDelay=(Math.random()*1.1)+'s'; box.appendChild(b); }
    return; }
  var s=FX[kind]||FX.sparkles;
  for(var i=0;i<10;i++){ var n=document.createElement('span'); n.className='spark'+(FALLING[kind]?' fall':''); n.textContent=s[i%s.length];
    n.style.left=(5+Math.random()*90)+'%'; n.style.top=(FALLING[kind]?Math.random()*30:30+Math.random()*50)+'%'; n.style.animationDelay=(Math.random()*0.8)+'s'; box.appendChild(n); } }
var fontsAsked={};
function useFont(f){ if(!f||f==='Poppins'||fontsAsked[f]||!/^[A-Za-z0-9 ]{1,40}$/.test(f)) return; fontsAsked[f]=1;
  var l=document.createElement('link'); l.rel='stylesheet'; l.href='https://fonts.googleapis.com/css2?display=swap&family='+f.replace(/ /g,'+'); document.head.appendChild(l); }
function letters(node,text,fx){ var parts=[];
  if(window.Intl&&Intl.Segmenter){ var it=new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text); for(var g of it) parts.push(g.segment); }
  else parts=Array.from(text);
  node.classList.add('t-'+fx);
  parts.forEach(function(p,i){ var c=document.createElement('span'); c.className='ch'; c.style.setProperty('--i',i); c.textContent=p; node.appendChild(c); }); }
function nameNode(text,fx){ var n=document.createElement('span'); n.className='name'; if(fx&&fx!=='none') letters(n,text,fx); else n.textContent=text; return n; }
function amountNode(text){ var a=document.createElement('span'); a.className='amt'; a.textContent=text; return a; }
function category(e){ return e.category||(e.platform==='tip'?'tip':(e.amount?'superchat':'other')); }
function designFor(cat){ var all=cfg.alertDesigns||{}; return all[cat]||all.default||{look:cfg.alertStyle||'neon'}; }
function wordsNode(e,d){
  var who=document.createElement('div'); who.className='who'; var name=e.name||'Someone';
  if(d.template){                                    // {name} and {amount} are filled in as plain text, never as HTML
    d.template.split(/(\{name\}|\{amount\})/).forEach(function(p){
      if(p==='{name}') who.appendChild(nameNode(name,d.text)); else if(p==='{amount}') who.appendChild(amountNode(e.amount||''));
      else if(p) who.appendChild(document.createTextNode(p)); });
    return who; }
  who.appendChild(nameNode(name,d.text));
  var actions={membership:' became a member',subscriber:' subscribed',follow:' followed',
    subscription:' subscribed',gift:' gifted',raid:' raided'};
  if(actions[e.category]){
    who.appendChild(document.createTextNode(actions[e.category]));
    if(e.amount) who.appendChild(amountNode(' · '+e.amount));
  } else { who.appendChild(document.createTextNode(' sent ')); who.appendChild(amountNode(e.amount||'')); }
  return who;
}
function render(e,d){
  var box=document.createElement('div'), kind=category(e);
  box.className='alert style-'+(d.look||'neon')+' in-'+(d.enter||'pop')+' idle-'+(d.idle||'float')+' exit-'+(d.exit||'out')+' k-'+kind;
  setCss('alert-'+kind,detailCss('.alert.k-'+kind,'.alert.k-'+kind,d)+(d.css||''));
  alertbox.className='pos-'+(d.position||'top-center');
  if(d.size&&d.size!==100) box.style.zoom=d.size/100;
  if(d.font){ useFont(d.font); box.style.fontFamily="'"+d.font+"',Poppins,'Noto Sans Devanagari',sans-serif"; }
  if(d.useColors){ box.style.setProperty('--a1',d.c1); box.style.setProperty('--a2',d.c2); box.style.setProperty('--a3',d.c3); }
  var holder=box;
  if(d.imageUrl&&/^\/memes\/[^\/]+$/.test(d.imageUrl)){ var img=document.createElement('img'); img.className='pic'; img.alt=''; img.src=d.imageUrl; box.appendChild(img);
    box.classList.add('lay-'+(d.layout||'above')); if(d.layout==='side'){ holder=document.createElement('div'); holder.className='words'; box.appendChild(holder); } }
  var src=document.createElement('div'); src.className='src'; src.textContent=LABELS[e.platform]||e.platform||''; holder.appendChild(src);
  holder.appendChild(wordsNode(e,d));
  var text=(cfg.showMessage===false)?'':(e.message||'');
  if(text){ var m=document.createElement('div'); m.className='msg'; m.textContent=text; holder.appendChild(m); }
  alertbox.appendChild(box); effect(box,d.effect||'sparkles');
  return {box:box,text:text};
}
// The alert type's own sound wins, then the design's, then the normal sound.
function playSound(kind,d){
  var own=(cfg.typeSounds||{})[kind], s=own||d;
  if(s.noSound) return;
  var pick=s.soundRandom&&s.soundRandom.length?s.soundRandom[Math.floor(Math.random()*s.soundRandom.length)]:'';
  var url=pick||s.soundUrl||d.soundUrl||cfg.soundUrl;
  var level=typeof d.soundVolume==='number'?d.soundVolume:(typeof cfg.soundVolume==='number'?cfg.soundVolume:80);
  if(url){ var sound=new Audio(url); sound.volume=Math.max(0,Math.min(1,level/100)); sound.play().catch(function(){}); }
  else if(cfg.sound) chime();
}
function next(){
  if(!queue.length){ busy=false; return; }
  busy=true; var e=queue.shift(), d=designFor(category(e)), shown=render(e,d);
  playSound(category(e),d);
  var ms=(d.seconds||cfg.seconds||8)*1000+Math.min(8000,shown.text.length*60);
  setTimeout(function(){ shown.box.classList.add('out'); setTimeout(function(){ shown.box.remove(); setTimeout(next,300); },550); },ms);
}
// The app's Alerts page calls this to show a design while it is being edited.
window.zdPreview=function(d,e){ cfg.showMessage=true; alertbox.textContent=''; render(e,d); };
// The app's Overlay styles page calls this with the design being edited and some sample content.
window.zdOverlay=function(kind,d,sample){
  cfg.designs=cfg.designs||{}; cfg.designs[kind]=d; cfg.chatSeconds=100000; document.body.className='show-'+kind;
  chatbox.textContent=''; memebox.textContent=''; alertbox.textContent=''; delete musicbox.dataset.look; musicbox.className=''; lastCounts={}; counterbox.textContent='';
  if(kind==='chat') sample.forEach(addChat);
  if(kind==='music'){ musicbox.querySelector('.mt').dataset.title=''; showMusic(sample); } else musicbox.classList.remove('on');
  if(kind==='meme'){ memes=[]; memeBusy=true; memes.push(sample); nextMemeOnce(); }
  showWidgets(kind==='widgets'?sample:{});
};
var HEXRX=/^#[0-9a-fA-F]{6}$/;
function hx(v,alt){ return HEXRX.test(v||'')?v:alt; }
function nm(v,alt){ v=Number(v); return isFinite(v)?v:alt; }
function tint(h,a){ h=hx(h,'#000000'); return 'rgba('+parseInt(h.slice(1,3),16)+','+parseInt(h.slice(3,5),16)+','+parseInt(h.slice(5,7),16)+','+a+')'; }
var BOX_SHADOW={none:'none',soft:'0 6px 18px rgba(0,0,0,.4)',strong:'0 12px 34px rgba(0,0,0,.75)'};
var TEXT_SHADOW={none:'none',soft:'0 1px 3px rgba(0,0,0,.8)',strong:'0 2px 8px #000,0 0 14px #000',outline:'-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000'};
var CASES={none:1,uppercase:1,lowercase:1,capitalize:1}, WEIGHTS={400:1,500:1,600:1,700:1,800:1,900:1};
function pct(v){ return nm(v,100)/100; }
// Every value is checked as a number or colour here, so a design can only ever produce these rules.
function detailCss(item,outer,d){
  var r=[],o=[],I=' !important',p=nm(d.padding,100),s=nm(d.speed,100),x=nm(d.offsetX,0),y=nm(d.offsetY,0),t=nm(d.tilt,0),css='';
  if(d.useBg) r.push('background:'+tint(d.bgColor,nm(d.bgOpacity,85)/100)+I);
  if(nm(d.blur,0)>0) r.push('backdrop-filter:blur('+nm(d.blur,0)+'px)'+I);
  if(nm(d.borderWidth,0)>0) r.push('border:'+nm(d.borderWidth,0)+'px solid '+hx(d.borderColor,'#22d3ee')+I);
  if(nm(d.radius,-1)>=0) r.push('border-radius:'+nm(d.radius,0)+'px'+I);
  if(p!==100) r.push('padding:'+(10*p/100)+'px '+(16*p/100)+'px'+I);
  if(d.shadow==='glow') r.push('box-shadow:0 0 22px '+hx(d.shadowColor,'#8b5cf6')+I); else if(BOX_SHADOW[d.shadow]) r.push('box-shadow:'+BOX_SHADOW[d.shadow]+I);
  if(nm(d.letterSpacing,0)!==0) r.push('letter-spacing:'+nm(d.letterSpacing,0)+'px'+I);
  if(nm(d.lineHeight,0)>0) r.push('line-height:'+nm(d.lineHeight,0)/100+I);
  if(CASES[d.textCase]&&d.textCase!=='none') r.push('text-transform:'+d.textCase+I);
  if(d.italic) r.push('font-style:italic'+I);
  if(d.useInk) r.push('color:'+hx(d.ink,'#ffffff')+I);
  if(TEXT_SHADOW[d.textShadow]) r.push('text-shadow:'+TEXT_SHADOW[d.textShadow]+I);
  if(s!==100) r.push('animation-duration:'+(60/s).toFixed(2)+'s,'+(300/s).toFixed(2)+'s'+I);
  if(r.length) css+=item+'{'+r.join(';')+'}';
  if(WEIGHTS[d.weight]) css+=item+','+item+' *{font-weight:'+d.weight+I+'}';
  if(x||y) o.push('translate:'+x+'px '+y+'px');
  if(t) o.push('rotate:'+t+'deg');
  if(o.length) css+=outer+'{'+o.join(';')+'}';
  return css;
}
function setCss(id,css){ var s=document.getElementById('css-'+id); if(!s){ s=document.createElement('style'); s.id='css-'+id; document.head.appendChild(s); } if(s.textContent!==css) s.textContent=css; }
function designOf(kind){ var all=cfg.designs||{}; return all[kind]||{}; }
function motion(d){ return ' fx in-'+(d.enter||'pop')+' idle-'+(d.idle||'none')+' exit-'+(d.exit||'fade'); }
function skin(d){ return d.skin&&d.skin!=='classic'?' skin skin-'+d.skin:''; }
function dressBox(box,d){                             // what a whole overlay shares: font, size, see-through and colours
  useFont(d.font);
  box.style.fontFamily=d.font?"'"+d.font+"',Poppins,'Noto Sans Devanagari',sans-serif":'';
  box.style.zoom=d.size&&d.size!==100?d.size/100:'';
  box.style.opacity=d.opacity&&d.opacity!==100?d.opacity/100:'';
  ['--a1','--a2','--a3'].forEach(function(v,i){ if(d.useColors) box.style.setProperty(v,d['c'+(i+1)]); else box.style.removeProperty(v); });
}
function setClass(el,name){ if(el.dataset.look!==name){ el.dataset.look=name; el.className=name; } }
function layoutChat(d){
  dressBox(chatbox,d);
  chatbox.className='edge-'+(d.edge||'bottom')+' new-'+(d.newest||'end')+' align-'+(d.align||'left');
  chatbox.style.right=d.width&&d.width<100?(100-d.width)+'%':'';
  var css=detailCss('#chatbox .m','#chatbox',d);
  if(d.lineGap!==undefined) css+='#chatbox{gap:'+nm(d.lineGap,6)+'px}';
  if(nm(d.nameSize,100)!==100) css+='#chatbox .m b{font-size:'+nm(d.nameSize,100)+'%}';
  if(nm(d.textSize,100)!==100) css+='#chatbox .m .tx{font-size:'+nm(d.textSize,100)+'%}';
  if(d.useMsgColour) css+='#chatbox .m .tx{color:'+hx(d.msgColour,'#e8e8f0')+'}';
  if(d.stacked) css+='#chatbox .m .tx{display:block;margin-top:2px}';
  setCss('chat',css+(d.css||''));
}
function platformColour(p,d){ return d.usePlatformColours&&HEXRX.test(d[p+'Colour']||'')?d[p+'Colour']:(COLORS[p]||'#aaa'); }
var SHORT={youtube:'YT',twitch:'TW',kick:'KK',tip:'TIP',test:'TEST'};
function hiddenChat(e,d){
  var text=e.text||'';
  if(d.hideCommands&&text.charAt(0)==='!') return true;
  if(d.hideLinks&&/https?:\/\/|www\.|\b[\w-]+\.(com|net|org|in|gg|tv|io|xyz|ru)\b/i.test(text)) return true;
  return (d.hideUsers||'').toLowerCase().split(',').map(function(u){ return u.trim(); }).indexOf((e.name||'').toLowerCase())>=0;
}
// Viewers' words stay text nodes. Only addresses the app accepted become pictures.
function fillWords(node,words,emotes){
  var names=Object.keys(emotes||{});
  if(!names.length){ node.textContent=words; return; }
  words.split(/(\s+)/).forEach(function(w){
    var url=emotes[w];
    if(typeof url==='string'&&url.indexOf('https://')===0){ var i=document.createElement('img'); i.className='emote'; i.src=url; i.alt=w; node.appendChild(i); }
    else node.appendChild(document.createTextNode(w));
  });
}
function addChat(e){
  var d=designOf('chat'), style=d.skin||cfg.chatStyle||'glass';
  if(hiddenChat(e,d)) return;
  layoutChat(d);
  var m=document.createElement('div'); m.className='m style-'+style+(d.skin?skin(d)+motion(d):'');
  var tag=document.createElement('span'); tag.className='tag'; tag.style.background=platformColour(e.platform,d); tag.textContent=(LABELS[e.platform]||e.platform||'').toUpperCase();
  if(d.tagStyle==='short') tag.textContent=SHORT[e.platform]||tag.textContent; else if(d.tagStyle==='dot'){ tag.textContent=''; tag.classList.add('dot'); }
  var end={colon:':',arrow:' \u203a'}[d.nameEnd]||'', who=(e.name||'')+end;
  var b=document.createElement('b'); if(d.text&&d.text!=='none') letters(b,who,d.text); else b.textContent=who;
  if(d.nameColour==='platform') b.style.color=platformColour(e.platform,d); else if(d.nameColour==='accent') b.style.color='var(--a2)';
  var words=e.text||'', most=nm(d.maxChars,0);
  if(most>0&&words.length>most) words=words.slice(0,most)+'\u2026';
  var t=document.createElement('span'); t.className='tx'; fillWords(t,words,e.emotes);
  if(d.showTime){ var now=new Date(), tm=document.createElement('span'); tm.className='tm'; tm.textContent=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2); m.appendChild(tm); }
  if(d.showTag!==false) m.appendChild(tag);
  var word=(d.highlightWord||'').toLowerCase();
  if(word&&(e.text||'').toLowerCase().indexOf(word)>=0) m.style.outline='2px solid '+hx(d.wordColour,'#fbbf24');
  else if(d.highlightMods&&e.mod) m.style.outline='2px solid '+hx(d.modColour,'#34d399');
  m.appendChild(b); m.appendChild(t); chatbox.appendChild(m);
  while(chatbox.children.length>(d.maxLines||cfg.maxLines||8)) chatbox.removeChild(chatbox.firstChild);
  if(!d.keep) setTimeout(function(){ m.classList.add(d.skin?'out':'old'); setTimeout(function(){ m.remove(); },650); },(cfg.chatSeconds||20)*1000);
}
var memebox=document.getElementById('memebox'), memes=[], memeBusy=false;
function nextMeme(){
  if(!memes.length){ memeBusy=false; return; }
  memeBusy=true; var e=memes.shift(), d=designOf('meme');
  dressBox(memebox,d); memebox.className='at-'+(d.position||'mid-center');
  var memeCss=detailCss('#memebox .cap','#memebox',d);
  if(nm(d.captionSize,100)!==100) memeCss+='#memebox .cap{font-size:'+(34*nm(d.captionSize,100)/100)+'px}';
  if(d.pictureRadius!==undefined) memeCss+='#memebox img{border-radius:'+nm(d.pictureRadius,18)+'px}';
  if(d.pictureGlow===false) memeCss+='#memebox img{box-shadow:none}';
  setCss('meme',memeCss+(d.css||''));
  var box=document.createElement('div'); box.className='meme'+(d.skin?motion(d):'');
  if(e.image && /^\/memes\/[^\/]+$/.test(e.image)){ var img=document.createElement('img'); img.src=e.image; img.alt=''; if(d.picture&&d.picture<100){ img.style.maxWidth=(86*d.picture/100)+'vw'; img.style.maxHeight=(72*d.picture/100)+'vh'; } box.appendChild(img); }
  if(e.caption&&d.showCaption!==false){ var cap=document.createElement('div'); cap.className='cap'+skin(d); if(d.text&&d.text!=='none') letters(cap,e.caption,d.text); else cap.textContent=e.caption; if(d.captionAt==='above') box.insertBefore(cap,box.firstChild); else box.appendChild(cap); }
  if(e.user&&d.showWho!==false){ var by=document.createElement('div'); by.className='by'; by.textContent='!'+(e.name||'')+' · '+e.user; box.appendChild(by); }
  memebox.appendChild(box);
  if(d.effect) effect(box,d.effect);
  setTimeout(function(){ box.classList.add('out'); setTimeout(function(){ box.remove(); setTimeout(nextMeme,200); },500); },(cfg.memeSeconds||6)*1000);
}
function nextMemeOnce(){ var keep=cfg.memeSeconds; cfg.memeSeconds=100000; nextMeme(); cfg.memeSeconds=keep; }
var counterbox=document.querySelector('#widgets .counters'), pollbox=document.getElementById('pollbox'), givebox=document.getElementById('givebox'), lastCounts={};
var betbox=document.getElementById('betbox'), queuebox=document.getElementById('queuebox'), goalbox=document.querySelector('#widgets .goals'), latestbox=document.querySelector('#widgets .latest');
function el(tag,cls,text){ var n=document.createElement(tag); if(cls) n.className=cls; if(text!==undefined) n.textContent=text; return n; }
var widgetsbox=document.getElementById('widgets');
function showWidgets(st){
  st=st||{};
  var d=designOf('widgets'), seen={}, look=skin(d), moves=d.skin?motion(d):'', space=nm(d.groupGap,16);
  dressBox(widgetsbox,d);
  var bar={solid:'var(--a1)',stripes:'repeating-linear-gradient(45deg,var(--a1) 0 12px,var(--a2) 12px 24px)'}[d.barStyle];
  var css=detailCss('#widgets .counter,#widgets .panel,#widgets .goal,#widgets .late','#widgets',d);
  if(d.panelWidth) css+='#widgets .panel{width:min('+nm(d.panelWidth,440)+'px,92vw)}';
  if(nm(d.titleSizeW,100)!==100) css+='#widgets .panel h3{font-size:'+(22*nm(d.titleSizeW,100)/100)+'px}';
  if(bar) css+='#widgets .fill,#widgets .opt .bar{background:'+bar+'}';
  if(d.barHeight) css+='#widgets .track{height:'+nm(d.barHeight,13)+'px}';
  if(d.barRadius!==undefined) css+='#widgets .track,#widgets .fill{border-radius:'+nm(d.barRadius,7)+'px}';
  if(d.countersRow) css+='#widgets .counters{flex-direction:row}';
  if(d.counterOrder==='label') css+='#widgets .counter{flex-direction:row-reverse}';
  if(d.latestRow) css+='#widgets .latest{flex-direction:row}';
  setCss('widgets',css+(d.css||''));
  if(d.showCounters===false) st.counters=[];
  if(d.showPoll===false) st.poll=null;
  if(d.showPrediction===false) st.prediction=null;
  if(d.showGiveaway===false) st.giveaway=null;
  if(d.showQueue===false) st.queue=null;
  if(d.showGoals===false) st.goals=[];
  if(d.showLatest===false) st.latest=[];
  widgetsbox.className='side-'+(d.panelSide||'right')+' c-'+(d.countersAt||'top-left')+' g-'+(d.goalsAt||'bottom-left')+' l-'+(d.latestAt||'bottom-right');
  [pollbox,betbox,givebox,queuebox].forEach(function(p){ setClass(p,'panel'+look+moves); });
  (st.counters||[]).forEach(function(c){
    seen[c.label]=1; var row=Array.prototype.find.call(counterbox.children,function(r){ return r.dataset.label===c.label; });
    if(!row){ row=el('div','counter'+look+moves); row.dataset.label=c.label; row.appendChild(el('span','n')); row.appendChild(el('span','l',c.label)); counterbox.appendChild(row); }
    var n=row.querySelector('.n'); if(n.textContent!==String(c.value)){ n.textContent=String(c.value);
      if(c.label in lastCounts){ row.classList.remove('bump'); void row.offsetWidth; row.classList.add('bump'); } }
    lastCounts[c.label]=c.value;
  });
  Array.prototype.slice.call(counterbox.children).forEach(function(row){ if(!seen[row.dataset.label]) row.remove(); });
  var p=st.poll, top=0;
  if(p&&(p.active||p.result)){
    pollbox.hidden=false; pollbox.style.top='0px'; pollbox.textContent='';
    pollbox.appendChild(el('h3','',p.question));
    var total=Math.max(1,p.total);
    p.options.forEach(function(o,i){ var row=el('div','opt'); var bar=el('div','bar'); bar.style.width=Math.round(100*o.votes/total)+'%';
      row.appendChild(bar); row.appendChild(el('span','',(i+1)+'. '+o.text)); row.appendChild(el('span','v',String(o.votes))); pollbox.appendChild(row); });
    pollbox.appendChild(el('div','meta',p.active?('Type !vote 1-'+p.options.length+' \u00b7 '+p.endsIn+'s left \u00b7 '+p.total+' votes'):p.result));
    top=pollbox.offsetHeight+space;
  } else pollbox.hidden=true;
  var b=st.prediction;
  if(b&&(b.open||b.locked||b.result)){
    betbox.hidden=false; betbox.style.top=top+'px'; betbox.textContent='';
    betbox.appendChild(el('h3','',b.question));
    var pool=Math.max(1,b.total);
    b.options.forEach(function(o,i){ var row=el('div','opt'); var bar=el('div','bar'); bar.style.width=Math.round(100*o.pool/pool)+'%';
      row.appendChild(bar); row.appendChild(el('span','',(i+1)+'. '+o.text)); row.appendChild(el('span','v',String(o.pool))); betbox.appendChild(row); });
    betbox.appendChild(el('div','meta',b.result?b.result:(b.open?('Type !bet 1 100 \u00b7 '+b.endsIn+'s left'):'Bets are locked')));
    top+=betbox.offsetHeight+space;
  } else betbox.hidden=true;
  var g=st.giveaway;
  if(g&&(g.open||g.winner)){
    givebox.hidden=false; givebox.style.top=top+'px'; givebox.textContent='';
    givebox.appendChild(el('h3','',g.winner?'Giveaway winner':'Giveaway open'));
    if(g.winner) givebox.appendChild(el('div','winner',g.winner));
    givebox.appendChild(el('div','meta',g.open?('Type !'+g.keyword+' to enter \u00b7 '+g.entries+' entered'):(g.entries+' entered')));
    top+=givebox.offsetHeight+space;
  } else givebox.hidden=true;
  var q=st.queue;
  if(q&&q.open){
    queuebox.hidden=false; queuebox.style.top=top+'px'; queuebox.textContent='';
    queuebox.appendChild(el('h3','','Viewer queue'));
    q.names.slice(0,nm(d.queueNames,5)).forEach(function(n,i){ queuebox.appendChild(el('div','opt',(i+1)+'. '+n)); });
    queuebox.appendChild(el('div','meta','Type !queue to join \u00b7 '+q.count+' waiting'));
  } else queuebox.hidden=true;
  goalbox.textContent='';
  (st.goals||[]).forEach(function(o){ var row=el('div','goal'+look), line=el('div','gl'), track=el('div','track'), fill=el('div','fill');
    var done=Math.round(100*o.value/Math.max(1,o.target));
    line.appendChild(el('span','',o.title)); line.appendChild(el('span','',d.goalText==='percent'?done+'%':o.value+' / '+o.target+(d.goalText==='all'?' \u00b7 '+done+'%':'')));
    fill.style.width=Math.min(100,Math.round(100*o.value/Math.max(1,o.target)))+'%'; track.appendChild(fill); row.appendChild(line); row.appendChild(track); goalbox.appendChild(row); });
  latestbox.textContent='';
  (st.latest||[]).forEach(function(o){ var row=el('div','late'+look); row.appendChild(el('span','',o.label)); row.appendChild(document.createTextNode(o.value)); latestbox.appendChild(row); });
}
var musicbox=document.getElementById('musicbox');
var musicTitle='', musicSince=0;
function eqBars(n){ var eq=musicbox.querySelector('.eq'); n=Math.max(2,Math.min(8,nm(n,4))); while(eq.children.length<n){ var i=document.createElement('i'); i.style.animationDelay=(eq.children.length*0.15)+'s'; eq.appendChild(i); } while(eq.children.length>n) eq.removeChild(eq.lastChild); }
function showMusic(st){
  var d=designOf('music'), base=(d.skin?skin(d)+motion(d):'')+' at-'+(d.position||'bottom-left')+(d.showEq===false?' no-eq':'');
  dressBox(musicbox,d); eqBars(d.eqBars);
  var css=detailCss('#musicbox','#musicbox',d);
  if(d.maxWidth) css+='#musicbox{max-width:min('+nm(d.maxWidth,560)+'px,92vw)}';
  if(nm(d.titleSize,100)!==100) css+='#musicbox .mt{font-size:'+(21*nm(d.titleSize,100)/100)+'px}';
  if(nm(d.artistSize,100)!==100) css+='#musicbox .ma{font-size:'+(15*nm(d.artistSize,100)/100)+'px}';
  setCss('music',css+(d.css||''));
  var label=musicbox.querySelector('.mp'); label.textContent=d.prefix||''; label.style.display=d.prefix?'block':'none';
  musicbox.querySelector('.mt').classList.toggle('marq',!!d.marquee);
  if(st&&st.title!==musicTitle){ musicTitle=st.title; musicSince=Date.now(); }
  if(st&&nm(d.autoHide,0)>0&&Date.now()-musicSince>d.autoHide*1000) st={};
  if(!st||!st.title||!st.playing){ if(musicbox.classList.contains('on')) musicbox.className=base+(d.skin?' out':''); musicbox.dataset.look=''; return; }
  var title=musicbox.querySelector('.mt');
  if(title.dataset.title!==st.title||title.dataset.fx!==(d.text||'')){ title.dataset.title=st.title; title.dataset.fx=d.text||''; title.textContent=''; if(d.text&&d.text!=='none') letters(title,st.title,d.text); else title.textContent=st.title; }
  musicbox.querySelector('.ma').textContent=st.artist||'';
  musicbox.querySelector('.ma').style.display=st.artist&&d.showArtist!==false?'block':'none'; setClass(musicbox,base+' on');
}
function tick(){
  fetch('/poll?type='+MODE+'&after='+after,{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){
    cfg=j.cfg||{}; applyColors(cfg);
    if(MODE==='chat') layoutChat(designOf('chat'));
    if(MODE==='music'){ showMusic(j.state); return; }
    if(MODE==='widgets'){ showWidgets(j.state); return; }
    if(after<0){ after=j.latest; }
    else { j.events.forEach(function(e){ after=Math.max(after,e.id); if(MODE==='alert'){
      var kind=category(e);
      if((kind==='tip'&&cfg.showTips===false)||(kind==='superchat'&&cfg.showSuperchats===false)||
         (kind==='membership'&&cfg.showMemberships===false)||(kind==='subscriber'&&cfg.showSubscribers===false)||
         (kind==='follow'&&cfg.showFollows===false)||(kind==='subscription'&&cfg.showSubscriptions===false)||
         (kind==='gift'&&cfg.showSubscriptions===false)||
         (kind==='raid'&&cfg.showRaids===false)) return;
      queue.push(e); if(!busy) next();
    } else if(MODE==='meme'){ if(e.image||e.caption){ memes.push(e); if(!memeBusy) nextMeme(); } }
    else addChat(e); }); }
  }).catch(function(){}).then(function(){ setTimeout(tick,POLL); });
}
if(MODE==='preview'){ fetch('/poll?type=alert&after=-1',{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){ cfg=j.cfg||{}; applyColors(cfg); }).catch(function(){}); }
else tick();
})();
</script></body></html>
"""

INDEX = """<!doctype html><meta charset="utf-8"><title>CHATDOOM overlays</title>
<body style="font:16px sans-serif;background:#10101c;color:#eee;padding:30px">
<h2>CHATDOOM overlays</h2><p style="opacity:.7">CHATDOOM, developed and powered by ZUNIMILABS</p><p>Add these as <b>Browser sources</b> in OBS:</p>
<ul><li><a style="color:#8ab4ff" href="/alert">/alert</a> payment, subscription, and channel-event alerts</li>
<li><a style="color:#8ab4ff" href="/chat">/chat</a> chat on screen</li>
<li><a style="color:#8ab4ff" href="/music">/music</a> now playing</li>
<li><a style="color:#8ab4ff" href="/meme">/meme</a> meme pictures and GIFs from chat !commands</li>
<li><a style="color:#8ab4ff" href="/widgets">/widgets</a> counters, chat poll and giveaway</li></ul></body>"""


def page(mode):
    return PAGE.replace("__MODE__", mode)
