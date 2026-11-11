const { JSDOM } = require("jsdom"); const fs = require("fs");
let fails = 0; const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function make(file, cfg) {
  const state = { latest: 5, events: [], music: null };
  const dom = new JSDOM(fs.readFileSync(file, "utf8"), { runScripts: "dangerously", pretendToBeVisual: true, beforeParse(w) {
    w.__POLL = 30; w.audioCalls = 0; w.AudioContext = function () { w.audioCalls++; throw new Error("no audio in test"); };
    w.fetch = (url) => { const after = Number(new URL(url, "http://x").searchParams.get("after"));
      const evs = after < 0 ? [] : state.events.filter((e) => e.id > after);
      return Promise.resolve({ json: () => Promise.resolve({ events: evs, latest: state.latest, cfg, state: state.music }) }); };
  } });
  return { dom, push(e) { e.id = ++state.latest; state.events.push(e); }, music(m) { state.music = m; } };
}
(async () => {
  // ---- alerts ----
  let t = make(require("path").join(__dirname, "out", "alert.html"), { seconds: 0.3, showMessage: true, sound: false, colors: { a1: "#aa0000", a2: "#00aa00", a3: "#0000aa" } });
  const doc = t.dom.window.document, seen = [];
  new t.dom.window.MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => { if (n.classList && n.classList.contains("alert")) seen.push(n.textContent); }))).observe(doc.getElementById("alertbox"), { childList: true });
  await sleep(150);
  ok(doc.querySelector(".alert") === null, "old alerts are not replayed when the page loads");
  t.push({ platform: "tip", name: "Rahul", amount: "₹100", message: "Great stream bhai" });
  t.push({ platform: "youtube", name: "<b>Evil</b>", amount: "₹50", message: '<img src=x onerror="window.hacked=1"> नमस्ते' });
  await sleep(250);
  ok(seen.length === 1 && seen[0].includes("Rahul") && seen[0].includes("₹100") && seen[0].includes("Great stream bhai") && seen[0].includes("Payment"), "first alert shows source, name, amount and message");
  ok(doc.querySelectorAll(".alert").length === 1, "second alert waits its turn (one on screen at a time)");
  ok(doc.documentElement.style.getPropertyValue("--a1") === "#aa0000", "theme colours from the app are applied");
  for (let i = 0; i < 80 && seen.length < 2; i++) await sleep(100);
  ok(seen.length === 2 && seen[1].includes("<b>Evil</b>") && seen[1].includes("नमस्ते"), "second alert appears after the first (HTML shown as plain text, Hindi works)");
  ok(doc.querySelector("img") === null && !t.dom.window.hacked, "no injected HTML or scripts can run");
  for (let i = 0; i < 100 && doc.querySelectorAll(".alert").length > 0; i++) await sleep(100);
  ok(doc.querySelectorAll(".alert").length === 0, "alerts remove themselves");
  ok(t.dom.window.audioCalls === 0, "no sound when sound is off");
  t.dom.window.close();
  // ---- message hidden / sound on ----
  t = make(require("path").join(__dirname, "out", "alert.html"), { seconds: 0.3, showMessage: false, sound: true, colors: {} });
  const d2 = t.dom.window.document; await sleep(120); t.push({ platform: "tip", name: "Sam", amount: "$5", message: "secret text" }); await sleep(250);
  ok(d2.querySelector(".alert") && !d2.querySelector(".msg") && t.dom.window.audioCalls === 1, "message hidden when turned off; chime attempted when sound is on");
  t.dom.window.close();
  // ---- alert designs ----
  t = make(require("path").join(__dirname, "out", "alert.html"), { seconds: 5, showMessage: true, sound: false, colors: {}, alertDesigns: {
    default: { look: "comic", enter: "bounce", idle: "wobble", exit: "fade", text: "none", effect: "none", font: "Bangers", position: "bottom-left", size: 120, useColors: true, c1: "#123456", c2: "#654321", c3: "#abcdef" },
    follow: { look: "cyber", enter: "glitch", idle: "none", exit: "blur", text: "wave", effect: "confetti", font: "Poppins", position: "top-center", template: "{name} joined with {amount}!", imageUrl: "/memes/hi.gif", layout: "side" },
    raid: { look: "royal", template: "<img src=x onerror=window.hacked=1> {name}", imageUrl: "https://evil.example/x.png" },
  } });
  const ad1 = t.dom.window.document; await sleep(120);
  t.push({ platform: "tip", category: "tip", name: "Rahul", amount: "₹100", message: "" }); await sleep(120);
  let al = ad1.querySelector(".alert");
  ok(al.className.includes("style-comic") && al.className.includes("in-bounce") && al.className.includes("idle-wobble") && al.className.includes("exit-fade"), "an alert uses the chosen look and animations");
  ok(ad1.getElementById("alertbox").className === "pos-bottom-left" && al.style.fontFamily.includes("Bangers") && al.style.getPropertyValue("--a1") === "#123456", "position, font and own colours are applied");
  ok([...ad1.querySelectorAll("link")].some((l) => l.href.includes("family=Bangers")), "a chosen font is loaded");
  al.remove(); t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "alert.html"), { seconds: 5, showMessage: true, sound: false, colors: {}, alertDesigns: {
    default: { look: "neon" },
    follow: { look: "cyber", text: "wave", effect: "confetti", template: "{name} joined with {amount}!", imageUrl: "/memes/hi.gif", layout: "side" },
  } });
  const ad2 = t.dom.window.document; await sleep(120);
  t.push({ platform: "twitch", category: "follow", name: "<b>Evil</b>", amount: "<i>5</i>", message: "" }); await sleep(120);
  al = ad2.querySelector(".alert");
  ok(al.className.includes("style-cyber") && al.textContent.includes("<b>Evil</b> joined with <i>5</i>!") && !al.querySelector("b,i"), "an alert type gets its own design, and its wording stays plain text");
  ok(al.querySelectorAll(".name .ch").length === "<b>Evil</b>".length && al.querySelectorAll(".spark.bit").length > 0, "text animation splits the name, and particles appear");
  ok(al.querySelector("img.pic").getAttribute("src") === "/memes/hi.gif" && al.className.includes("lay-side"), "the alert shows its picture");
  t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "alert.html"), { seconds: 5, showMessage: true, sound: false, colors: {}, alertDesigns: {
    default: { look: "royal", template: "<img src=x onerror=window.hacked=1> {name}", imageUrl: "https://evil.example/x.png", font: "x');}<style>" },
  } });
  const ad3 = t.dom.window.document; await sleep(120);
  t.push({ platform: "tip", category: "tip", name: "Sam", amount: "", message: "" }); await sleep(120);
  ok(!ad3.querySelector(".alert img") && !t.dom.window.hacked && ![...ad3.querySelectorAll("link")].length, "bad wording, outside pictures and bad font names do nothing");
  t.dom.window.close();
  // ---- tips by amount ----
  const tierCfg = { seconds: 0.2, showMessage: true, sound: false, colors: {}, alertDesigns: { default: { look: "neon" }, tip: { look: "minimal" } },
    tipTiers: [{ from: 100, design: { look: "royal", tier: true } }, { from: 2000, design: { look: "lava", tier: true } }] };
  const looks = [];
  for (const [value, amount] of [[50, "₹50"], [100, "₹100"], [1999, "₹1,999"], [2000, "₹2,000"], [99999, "₹99,999"], [undefined, "$5"]]) {
    t = make(require("path").join(__dirname, "out", "alert.html"), tierCfg);
    const td = t.dom.window.document; await sleep(80);
    t.push({ platform: "tip", category: "tip", name: "Rahul", amount, value, message: "" }); await sleep(100);
    looks.push((td.querySelector(".alert").className.match(/style-(\w+)/) || [])[1]);
    t.dom.window.close();
  }
  ok(looks.join(",") === "minimal,royal,royal,lava,lava,minimal", "a tip gets the highest step it reaches, and a tip with no rupee amount the normal Tips design: " + looks.join(","));
  t = make(require("path").join(__dirname, "out", "alert.html"), tierCfg);
  const sc = t.dom.window.document; await sleep(80);
  t.push({ platform: "youtube", category: "superchat", name: "Neha", amount: "₹5,000", value: 5000, message: "" }); await sleep(100);
  ok(sc.querySelector(".alert").className.includes("style-neon"), "steps are only for tips, not Super Chats");
  t.dom.window.close();
  // ---- chat ----
  t = make(require("path").join(__dirname, "out", "chat.html"), { chatSeconds: 0.4, maxLines: 8, colors: {} });
  const d3 = t.dom.window.document; await sleep(120);
  for (let i = 0; i < 10; i++) t.push({ platform: i % 2 ? "twitch" : "youtube", name: "u" + i, text: "msg " + i });
  await sleep(250);
  const lines = d3.querySelectorAll("#chatbox .m");
  ok(lines.length === 8 && lines[7].textContent.includes("msg 9") && !d3.getElementById("chatbox").textContent.includes("msg 0"), "chat keeps only the newest 8 lines");
  ok(lines[7].querySelector(".tag").textContent === "TWITCH" && lines[6].querySelector(".tag").textContent === "YOUTUBE", "platform tags shown");
  await sleep(1400); ok(d3.querySelectorAll("#chatbox .m").length === 0, "chat lines fade away after the set time");
  t.dom.window.close();
  // ---- chat designs ----
  t = make(require("path").join(__dirname, "out", "chat.html"), { chatSeconds: 5, maxLines: 8, colors: {}, designs: { chat: {
    skin: "comic", enter: "drop", exit: "blur", idle: "none", text: "wave", font: "Bangers", size: 120, opacity: 80, align: "center", edge: "top", newest: "start",
    width: 60, maxLines: 3, showTag: false, nameColour: "platform", hideCommands: true, keep: true, useColors: true, c1: "#123456", c2: "#222222", c3: "#333333" } } });
  const dc = t.dom.window.document, cb = dc.getElementById("chatbox"); await sleep(120);
  for (let i = 0; i < 5; i++) t.push({ platform: "twitch", name: "<b>u" + i + "</b>", text: "<img src=x onerror=window.hacked=1> m" + i });
  t.push({ platform: "twitch", name: "cmd", text: "!points" });
  await sleep(200);
  const styled = dc.querySelectorAll("#chatbox .m");
  ok(styled.length === 3 && styled[0].className.includes("skin-comic") && styled[0].className.includes("in-drop") && styled[0].className.includes("exit-blur"), "chat lines use the chosen skin, animations and line limit");
  ok(cb.className === "edge-top new-start align-center" && cb.style.right === "40%" && cb.style.fontFamily.includes("Bangers") && cb.style.opacity === "0.8" && cb.style.getPropertyValue("--a1") === "#123456", "chat layout, font, see-through and colours are applied");
  ok(!styled[0].querySelector(".tag") && styled[0].querySelectorAll("b .ch").length > 0 && !cb.textContent.includes("!points"), "tags can be hidden, names animate and !commands can be hidden");
  ok(!cb.querySelector("img") && !t.dom.window.hacked && cb.textContent.includes("<b>u4</b>"), "styled chat stays plain text");
  await sleep(300); ok(dc.querySelectorAll("#chatbox .m").length === 3, "kept lines stay until newer ones push them out");
  t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "music.html"), { colors: {}, designs: { music: { skin: "neon", enter: "rise", exit: "drop", idle: "none", position: "top-right", showEq: false, showArtist: false, text: "wave", font: "Poppins" } } });
  const dm = t.dom.window.document, mb = dm.getElementById("musicbox"); await sleep(120);
  t.music({ title: "<i>Song</i>", artist: "Aria", playing: true }); await sleep(150);
  ok(mb.className.includes("skin-neon") && mb.className.includes("at-top-right") && mb.className.includes("no-eq") && mb.classList.contains("on") && mb.querySelector(".ma").style.display === "none", "now playing uses its skin, corner and options");
  ok(mb.querySelector(".mt").textContent === "<i>Song</i>" && !mb.querySelector("i i, .mt i"), "an animated song title stays plain text");
  t.music({ title: "x", artist: "", playing: false }); await sleep(150);
  ok(!mb.classList.contains("on") && mb.classList.contains("out"), "now playing leaves with its exit animation");
  t.dom.window.close();
  // ---- detail options ----
  t = make(require("path").join(__dirname, "out", "chat.html"), { chatSeconds: 5, maxLines: 8, colors: {}, designs: { chat: {
    skin: "glass", useBg: true, bgColor: "#102030", bgOpacity: 50, borderWidth: 3, borderColor: "red;}body{display:none", radius: 12, shadow: "glow", shadowColor: "#00ff00", weight: "800", textCase: "uppercase",
    textShadow: "outline", speed: 200, offsetX: 20, offsetY: -10, tilt: 4, tagStyle: "short", nameEnd: "colon", showTime: true, lineGap: 11, nameSize: 150, stacked: true, useMsgColour: true, msgColour: "#abcdef",
    usePlatformColours: true, twitchColour: "#111111", highlightMods: true, modColour: "#00ff00", highlightWord: "boss", wordColour: "#ff0000", hideLinks: true, hideUsers: "Nightbot, spammer", maxChars: 10, css: ".m{letter-spacing:1px}" } } });
  const dd = t.dom.window.document; await sleep(120);
  t.push({ platform: "twitch", name: "ana", text: "hello there everyone", mod: true });
  t.push({ platform: "twitch", name: "bo", text: "hey Boss" });
  t.push({ platform: "twitch", name: "NIGHTBOT", text: "bot line" });
  t.push({ platform: "twitch", name: "cy", text: "go to evil.com now" });
  await sleep(200);
  const rows = dd.querySelectorAll("#chatbox .m"), sheet = dd.getElementById("css-chat").textContent;
  ok(rows.length === 2 && rows[0].querySelector(".tag").textContent === "TW" && rows[0].querySelector("b").textContent === "ana:" && rows[0].querySelector(".tm"), "tag style, name ending and time work, and hidden viewers and links stay out");
  ok(rows[0].querySelector(".tx").textContent === "hello ther\u2026" && rows[0].querySelector(".tag").style.background.includes("17, 17, 17"), "long messages are cut and platform colours apply");
  ok(rows[0].style.outline.includes("rgb(0, 255, 0)") || rows[0].style.outline.includes("#00ff00"), "moderators are highlighted");
  ok(rows[1].style.outline.includes("rgb(255, 0, 0)") || rows[1].style.outline.includes("#ff0000"), "lines with the word are highlighted");
  ok(sheet.includes("rgba(16,32,48,0.5)") && sheet.includes("border-radius:12px") && sheet.includes("0 0 22px #00ff00") && sheet.includes("font-weight:800") && sheet.includes("text-transform:uppercase") && sheet.includes("translate:20px -10px") && sheet.includes("rotate:4deg") && sheet.includes("gap:11px") && sheet.includes(".m{letter-spacing:1px}"), "box, text, motion and custom CSS options all become rules");
  ok(!sheet.includes("body{display:none") && sheet.includes("#22d3ee"), "a bad colour cannot add its own CSS");
  t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "widgets.html"), { colors: {}, designs: { widgets: { showPoll: false, showGiveaway: false, showCounters: true, showGoals: true, showLatest: false, panelWidth: 600, barStyle: "stripes", barHeight: 20, barRadius: 2, goalText: "percent", countersRow: true, counterOrder: "label", queueNames: 2, groupGap: 30 } } });
  const dw = t.dom.window.document; await sleep(120);
  t.music({ counters: [{ label: "Wins", value: 1 }], poll: { question: "Hidden?", active: true, total: 1, endsIn: 9, result: "", options: [{ text: "A", votes: 1 }, { text: "B", votes: 0 }] }, giveaway: { keyword: "join", open: true, entries: 1, winner: "" },
            goals: [{ title: "Subs", value: 32, target: 50 }], latest: [{ label: "Latest tip", value: "x" }], queue: { open: true, count: 4, names: ["a", "b", "c", "d"] } });
  await sleep(150);
  const wsheet = dw.getElementById("css-widgets").textContent;
  ok(dw.getElementById("pollbox").hidden && dw.getElementById("givebox").hidden && !dw.querySelector(".late") && dw.querySelector(".counter"), "each widget can be switched off");
  ok(dw.querySelector(".goal .gl").textContent.includes("64%") && dw.querySelectorAll("#queuebox .opt").length === 2, "goal numbers and the queue length follow the design");
  ok(wsheet.includes("min(600px,92vw)") && wsheet.includes("repeating-linear-gradient") && wsheet.includes("height:20px") && wsheet.includes("flex-direction:row") && wsheet.includes("row-reverse"), "panel size, bar style and counter layout are applied");
  t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "music.html"), { colors: {}, designs: { music: { prefix: "<b>Now playing</b>", maxWidth: 800, titleSize: 150, marquee: true, eqBars: 7, autoHide: 1 } } });
  const dn = t.dom.window.document, nb = dn.getElementById("musicbox"); await sleep(120);
  t.music({ title: "Song", artist: "A", playing: true }); await sleep(150);
  ok(nb.querySelector(".mp").textContent === "<b>Now playing</b>" && nb.querySelectorAll(".eq i").length === 7 && nb.querySelector(".mt").classList.contains("marq") && nb.classList.contains("on"), "label, bars and scrolling title work");
  await sleep(1100); ok(!nb.classList.contains("on"), "now playing can hide itself after a while");
  t.dom.window.close();
  t = make(require("path").join(__dirname, "out", "meme.html"), { memeSeconds: 3, colors: {}, designs: { meme: { captionAt: "above", pictureRadius: 40, pictureGlow: false, captionSize: 150 } } });
  const dq = t.dom.window.document; await sleep(120);
  t.push({ name: "m", user: "U", image: "/memes/a.gif", caption: "Top" }); await sleep(150);
  const qs = dq.getElementById("css-meme").textContent;
  ok(dq.querySelector(".meme").firstChild.className.includes("cap") && qs.includes("border-radius:40px") && qs.includes("box-shadow:none"), "meme caption place and picture options work");
  t.dom.window.close();
  // ---- now playing ----
  t = make(require("path").join(__dirname, "out", "music.html"), { colors: {} });
  const d4 = t.dom.window.document, box = d4.getElementById("musicbox"); await sleep(120);
  ok(!box.classList.contains("on"), "now-playing box is hidden when nothing plays");
  t.music({ title: "First Song", artist: "Aria", playing: true }); await sleep(150);
  ok(box.classList.contains("on") && box.querySelector(".mt").textContent === "First Song" && box.querySelector(".ma").textContent === "Aria", "shows the title and artist while playing");
  t.music({ title: "<img src=x onerror=1>", artist: "", playing: true }); await sleep(150);
  ok(box.querySelector(".mt").textContent === "<img src=x onerror=1>" && !d4.querySelector("img") && box.querySelector(".ma").style.display === "none", "titles are shown as plain text and an empty artist line is hidden");
  t.music({ title: "First Song", artist: "Aria", playing: false }); await sleep(150);
  ok(!box.classList.contains("on"), "hides again when the music is paused");
  t.dom.window.close();
  // ---- memes ----
  t = make(require("path").join(__dirname, "out", "meme.html"), { memeSeconds: 0.3, colors: {} });
  const d5 = t.dom.window.document; await sleep(120);
  t.push({ name: "bruh", user: "Fan", image: "/memes/bruh.gif", caption: "bruh moment" });
  t.push({ name: "evil", user: "<b>x</b>", image: "https://evil.example/x.gif", caption: '<img src=x onerror="window.hacked=1">' });
  await sleep(150);
  const first = d5.querySelectorAll("#memebox .meme");
  ok(first.length === 1 && first[0].querySelector("img").getAttribute("src") === "/memes/bruh.gif"
     && first[0].querySelector(".cap").textContent === "bruh moment" && first[0].textContent.includes("!bruh") && first[0].textContent.includes("Fan"),
     "a meme shows its picture, caption and who played it, one at a time");
  for (let i = 0; i < 40 && !(d5.querySelector("#memebox .meme") && d5.querySelector("#memebox .meme").textContent.includes("evil")); i++) await sleep(50);
  const second = d5.querySelector("#memebox .meme");
  ok(second && !second.querySelector("img") && second.querySelector(".cap").textContent.includes("<img") && !t.dom.window.hacked,
     "pictures from outside the memes folder are not loaded and captions are plain text");
  for (let i = 0; i < 40 && d5.querySelectorAll("#memebox .meme").length; i++) await sleep(50);
  ok(d5.querySelectorAll("#memebox .meme").length === 0, "memes clear themselves after the set time");
  t.dom.window.close();
  // ---- widgets: counters, poll, giveaway ----
  t = make(require("path").join(__dirname, "out", "widgets.html"), { colors: {} });
  const d6 = t.dom.window.document; await sleep(120);
  ok(!d6.querySelector(".counter") && d6.getElementById("pollbox").hidden && d6.getElementById("givebox").hidden, "widgets stay empty until there is something to show");
  t.music({ counters: [{ label: "Deaths", value: 2 }], poll: { question: "<b>Next?</b>", active: true, total: 3, endsIn: 40, result: "",
            options: [{ text: "Valorant", votes: 2 }, { text: "GTA", votes: 1 }] }, giveaway: { keyword: "join", open: true, entries: 5, winner: "" } });
  await sleep(150);
  const bars = d6.querySelectorAll("#pollbox .opt .bar");
  ok(d6.querySelector(".counter .n").textContent === "2" && d6.querySelector(".counter").textContent.includes("Deaths"), "counters show their label and value");
  ok(d6.querySelector("#pollbox h3").textContent === "<b>Next?</b>" && bars.length === 2 && bars[0].style.width === "67%" && d6.getElementById("pollbox").textContent.includes("40s left"),
     "the poll shows plain-text question, vote bars and time left");
  ok(!d6.getElementById("givebox").hidden && d6.getElementById("givebox").textContent.includes("!join") && d6.getElementById("givebox").textContent.includes("5 entered"), "an open giveaway shows how to enter");
  t.music({ counters: [{ label: "Deaths", value: 3 }], poll: null, giveaway: { keyword: "join", open: false, entries: 5, winner: "Rahul" } });
  await sleep(150);
  ok(d6.querySelector(".counter .n").textContent === "3" && d6.querySelector(".counter").classList.contains("bump"), "a counter change bumps on screen");
  ok(d6.getElementById("pollbox").hidden && d6.querySelector("#givebox .winner").textContent === "Rahul", "the giveaway winner is shown big");
  t.music({ counters: [], poll: null, giveaway: null }); await sleep(150);
  ok(!d6.querySelector(".counter") && d6.getElementById("givebox").hidden, "removed counters and cleared giveaways disappear");
  t.dom.window.close();
  console.log(fails ? fails + " FAILED" : "ALL PASSED"); process.exit(fails ? 1 : 0);
})();
