// The real page in headless Chrome: every mode and URL option loads and runs with
// no errors and no page overflow, and every event can happen without breaking it.
// Skipped (not failed) when no Chrome is installed.
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { launch, chromeBin, gameUrl } from "./lib/chrome.mjs";

const PHONE = { width: 390, height: 844, dpr: 3, mobile: true };
const DESKTOP = { width: 1280, height: 800, dpr: 1 };
const TVSIZE = { width: 1920, height: 1080, dpr: 1 };

describe("in the browser", { skip: chromeBin ? false : "no Chrome installed", concurrency: 4 }, () => {
  let browser;
  before(async () => { browser = await launch(); });
  after(async () => { await browser?.close(); });

  async function open(search, view = PHONE, settle = 1500) {
    const p = await browser.page(view);
    await p.goto(gameUrl(search), settle);
    return p;
  }
  // the page fits the window, the canvas has a size, and the game clock moves
  async function healthy(p, label) {
    const s = await p.ev(`({ sw: document.documentElement.scrollWidth, iw: innerWidth, sh: document.documentElement.scrollHeight, ih: innerHeight,
      cw: document.getElementById("game").width, ch: document.getElementById("game").height, t: airClock })`);
    assert.ok(s.sw <= s.iw && s.sh <= s.ih, `${label}: page overflows the window (${s.sw}x${s.sh} in ${s.iw}x${s.ih})`);
    assert.ok(s.cw > 0 && s.ch > 0, `${label}: canvas has no size`);
    await p.sleep(400);
    assert.ok((await p.ev("airClock")) > s.t, `${label}: the game is not running`);
    assert.deepEqual(p.errors, [], `${label}: errors in the page`);
  }

  const VARIANTS = [
    ["", PHONE], ["", DESKTOP], ["?noclock", PHONE], ["?tod", PHONE], ["?tv", TVSIZE], ["?tvs", TVSIZE],
    ["?env=0", PHONE], ["?env=20", PHONE], ["?fps&prof", PHONE], ["?lowres", TVSIZE], ["?hz=30", PHONE],
    ["?daylen=30&hour=17", PHONE], ["?season=3&snow=200&hour=23", PHONE], ["?season=1&sand=200", PHONE],
    ["?resetstats", PHONE], ["?tvs&tod&fps", TVSIZE],
    ["?fireworks", PHONE], ["?fireworks&tvs&hour=21", TVSIZE], ["?fireworks&2d&season=1", PHONE], ["?fireworks&scan=delta&hour=22", TVSIZE],
    ["?2d", PHONE], ["?2d", DESKTOP], ["?scan=soft", TVSIZE], ["?scan=grille", TVSIZE], ["?scan=off", TVSIZE], ["?2d&scan=off", PHONE],
    ["?scan=delta", TVSIZE], ["?scan=slot", TVSIZE], ["?scan=delta", PHONE], ["?scan=slot", PHONE], ["?scan=delta&bloom=0", PHONE],
    ["?scan=lines&bloom=2", PHONE], ["?2d&scan=slot", PHONE],
    ["?shadow=dither", TVSIZE], ["?shadow=smooth", TVSIZE], ["?shadow=blocky", TVSIZE], ["?shadow=off", TVSIZE], ["?2d&shadow=smooth", PHONE],
  ];
  for (const [search, view] of VARIANTS) {
    it(`loads and runs: ${search || "(no options)"} at ${view.width}x${view.height}`, async () => {
      const p = await open(search, view);
      try { await healthy(p, search || "default"); } finally { await p.close(); }
    });
  }

  it("sizes the world to the screen in the TV modes and the phone layout", async () => {
    const tv = await open("?tvs", TVSIZE), ph = await open("", PHONE);
    try {
      assert.equal(await tv.ev("W"), 910);
      assert.equal(await ph.ev("W"), 288);
    } finally { await tv.close(); await ph.close(); }
  });

  for (const mode of ["", "&2d"]) {
    it(`keeps the canvas under BUF_MAX pixels even on a 4K screen${mode ? " (2D)" : ""}`, async () => {
      const p = await open("?tvs" + mode, { width: 1920, height: 1080, dpr: 2 });
      try {
        const b = await p.ev("[buf.width, buf.height, BUF_MAX, R]");
        assert.ok(b[0] * b[1] <= b[2], `canvas ${b[0]}x${b[1]}`);
        assert.equal(b[3], 2);
        await healthy(p, "4K" + mode);
      } finally { await p.close(); }
    });
  }

  // the visible canvas is a GL one (anything but #game) in GL mode
  const shown = `(() => {
    const vis = e => e && getComputedStyle(e).display !== "none";
    const gl = GLR && GLR.gl.canvas;
    return { game: vis(document.getElementById("game")), scan: vis(document.getElementById("scan")),
      gl: !!gl && vis(gl), glw: gl ? gl.width : 0, glh: gl ? gl.height : 0 };
  })()`;

  it("uses WebGL by default and Canvas 2D with ?2d", async () => {
    const a = await open("", DESKTOP), b = await open("?2d", DESKTOP);
    try {
      assert.equal(await a.ev("RENDERER"), "GL", "WebGL did not start by default");
      assert.equal(await b.ev("RENDERER"), "2D");
      assert.equal(await b.ev("GLR"), null);
    } finally { await a.close(); await b.close(); }
  });

  it("shows the GL canvas and hides #game and #scan in GL mode; #game in 2D", async () => {
    const a = await open("", DESKTOP), b = await open("?2d", DESKTOP);
    try {
      assert.equal(await a.ev("RENDERER"), "GL");
      const g = await a.ev(shown);
      assert.ok(g.gl && g.glw > 0 && g.glh > 0, `no visible GL canvas: ${JSON.stringify(g)}`);
      assert.ok(!g.game && !g.scan, `#game / #scan still shown in GL mode: ${JSON.stringify(g)}`);
      const d = await b.ev(shown);
      assert.ok(d.game && !d.gl, `2D mode: ${JSON.stringify(d)}`);
    } finally { await a.close(); await b.close(); }
  });

  it("falls back to 2D when the WebGL context is lost, and keeps running", async () => {
    const p = await open("?scan=delta", DESKTOP);
    try {
      assert.equal(await p.ev("RENDERER"), "GL");
      assert.equal(await p.ev("SCAN_STYLE"), "delta");
      assert.equal(await p.ev("BLOOM"), 1);
      assert.equal(await p.ev(`(() => { const e = GLR.gl.getExtension("WEBGL_lose_context"); if (!e) return false; e.loseContext(); return true; })()`), true, "no WEBGL_lose_context");
      await p.sleep(1000);
      assert.equal(await p.ev("RENDERER"), "2D");
      assert.equal(await p.ev("GLR"), null);
      assert.equal(await p.ev("SHADOW_STYLE"), "classic", "the soft shadows need GL");
      assert.equal(await p.ev("SCAN_STYLE"), "lines", "delta needs GL");
      assert.equal(await p.ev("BLOOM"), 0, "the bloom needs GL");
      assert.ok((await p.ev(shown)).game, "#game is not shown after the fallback");
      await healthy(p, "after context loss");
    } finally { await p.close(); }
  });

  it("takes the shadow style from ?shadow=, and 2D only has classic and off", async () => {
    for (const [q, want] of [["", "dither"], ["?shadow=smooth", "smooth"], ["?shadow=blocky", "blocky"], ["?shadow=classic", "classic"], ["?shadow=off", "off"],
                             ["?2d", "classic"], ["?2d&shadow=smooth", "classic"], ["?2d&shadow=off", "off"]]) {
      const p = await open(q, DESKTOP, 500);
      try { assert.equal(await p.ev("SHADOW_STYLE"), want, q || "default"); } finally { await p.close(); }
    }
  });

  it("takes the scanline style from ?scan=", async () => {
    for (const [q, want] of [["", "lines"], ["?scan=soft", "soft"], ["?scan=grille", "grille"], ["?scan=off", "off"],
                             ["?scan=delta", "delta"], ["?scan=slot", "slot"], ["?2d&scan=delta", "lines"], ["?2d&scan=slot", "lines"], ["?2d&scan=soft", "soft"]]) {
      const p = await open(q, DESKTOP, 500);
      try { assert.equal(await p.ev("SCAN_STYLE"), want, q || "default"); } finally { await p.close(); }
    }
  });

  it("takes the bloom strength from ?bloom= (1 for delta and slot, 0 elsewhere, none in 2D)", async () => {
    for (const [q, want] of [["", 0], ["?scan=delta", 1], ["?scan=slot", 1], ["?scan=delta&bloom=0", 0], ["?scan=delta&bloom=2.5", 2.5],
                             ["?scan=lines&bloom=1", 1], ["?scan=grille&bloom=0.5", 0.5], ["?bloom=2", 2], ["?scan=soft&bloom=", 0], ["?2d&scan=slot", 0], ["?2d&bloom=2", 0]]) {
      const p = await open(q, DESKTOP, 500);
      try { assert.equal(await p.ev("BLOOM"), want, q || "default"); } finally { await p.close(); }
    }
  });

  it("draws delta and slot a whole number of device px per game px, on a whole device px, at a fractional DPR", async () => {
    // the picture is W*k x H*k inside the canvas: one size up when that crops at most CRT_OVERSCAN (a TV's
    // overscan), else one down with black bars. 390x844 @3 is the case that used to lose a quarter of the screen
    for (const [q, view] of [["?scan=delta&crtfit=exact", { width: 390, height: 844, dpr: 2.75, mobile: true }], ["?scan=slot&tvs&crtfit=exact", { width: 1920, height: 1080, dpr: 1.25 }],
                             ["?scan=delta&tvs&crtfit=exact", { width: 1280, height: 720, dpr: 1.5 }], ["?scan=slot&crtfit=exact", { width: 390, height: 844, dpr: 3, mobile: true }]]) {
      const p = await open(q, view, 800);
      try {
        const r = await p.ev(`(() => { const c = GLR.cv, b = c.getBoundingClientRect(), d = devicePixelRatio;
          return { k: DS, W, H, os: CRT_OVERSCAN, pic: GLR.pic(), cw: c.width, ch: c.height, x: b.left * d, y: b.top * d, w: b.width * d, h: b.height * d }; })()`);
        const lab = `${q} at dpr ${view.dpr}`;
        assert.ok(Number.isInteger(r.k) && r.k >= 2, `${lab}: ${r.k} device px per game px`);
        assert.equal(r.pic.w, r.W * r.k, `${lab}: the picture is not W*k wide`);
        assert.equal(r.pic.h, r.H * r.k, `${lab}: the picture is not H*k tall`);
        assert.ok(Number.isInteger(r.pic.x) && Number.isInteger(r.pic.y), `${lab}: picture at ${r.pic.x},${r.pic.y} in the canvas`);
        assert.ok(r.cw >= r.pic.w * (1 - r.os) - 1 && r.ch >= r.pic.h * (1 - r.os) - 1, `${lab}: more than ${r.os * 100}% cropped`);
        if (view.dpr === 3) assert.ok(Math.min(r.cw / r.pic.w, r.ch / r.pic.h) > 0.9, `${lab}: the picture uses only ${(Math.min(r.cw / r.pic.w, r.ch / r.pic.h) * 100).toFixed(0)}% of the canvas`);
        assert.ok(Math.abs(r.w - r.cw) < 0.1 && Math.abs(r.h - r.ch) < 0.1, `${lab}: shown at ${r.w}x${r.h}, not 1:1`);
        assert.ok(Math.abs(r.x - Math.round(r.x)) < 0.01 && Math.abs(r.y - Math.round(r.y)) < 0.01, `${lab}: at ${r.x},${r.y}, not a whole device px`);
        await healthy(p, lab);
      } finally { await p.close(); }
    }
  });

  it("fills the window with delta and slot by default (crtfit=fill): made at whole px offscreen, resized smoothly", async () => {
    for (const [q, view] of [["?scan=delta", { width: 1280, height: 800, dpr: 2 }], ["?scan=slot&tvs", { width: 1440, height: 900, dpr: 1 }]]) {
      const p = await open(q, view, 800);
      try {
        const r = await p.ev(`({ fit: CRT_FIT, k: DS, W, H, pic: GLR.pic(), cw: GLR.cv.width, ch: GLR.cv.height })`);
        const lab = `${q} at ${view.width}x${view.height}@${view.dpr}`;
        assert.equal(r.fit, "fill");
        assert.ok(r.pic.fill, `${lab}: not drawn offscreen`);
        assert.ok(Number.isInteger(r.k) && r.pic.w === r.W * r.k && r.pic.h === r.H * r.k, `${lab}: the offscreen picture is not whole px per game px`);
        assert.ok(r.pic.w >= r.cw - 1 && r.pic.h >= r.ch - 1, `${lab}: made smaller than the screen (${r.pic.w}x${r.pic.h} for ${r.cw}x${r.ch})`);
        await healthy(p, lab);
      } finally { await p.close(); }
    }
  });

  it("crashes, shows the stats card, counts the run and starts again", async () => {
    const p = await open("");
    try {
      await p.ev(`die(birdX, bird.y, "pipe")`);
      let card = false;
      for (let i = 0; i < 40 && !card; i++) { await p.sleep(100); card = await p.ev("dead && offT > 0"); }
      assert.ok(card, "the stats card never came up");
      assert.equal(await p.ev("stats.runs"), 1);
      assert.equal(await p.ev("lastKind"), "pipe");
      assert.equal(JSON.parse(await p.ev(`localStorage.getItem("flappy-stats")`)).runs, 1);
      let back = false;
      for (let i = 0; i < 90 && !back; i++) { await p.sleep(100); back = await p.ev("!dead"); }
      assert.ok(back, "it never restarted");
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
  });

  it("is abducted by the saucer at night, and the next round sends morse", async () => {
    const p = await open("?hour=23");
    try {
      await p.ev("ufoNight = null; ufoNext = 0; UFO.abductP = 1; 0");
      let gone = false;
      for (let i = 0; i < 300 && !gone; i++) { await p.sleep(100); gone = await p.ev("abducted && dead"); if (i % 10 === 0) await p.ev("if (ufo) ufo.hold = 0; 0"); }
      assert.ok(gone, "the saucer never took the bird");
      assert.equal(await p.ev("lastKind"), "ufo");
      let dish = null;
      for (let i = 0; i < 120 && !dish; i++) { await p.sleep(100); dish = await p.ev("dish && !dead ? dish.msg : null"); }
      assert.ok(dish, "no dish in the round after");
      assert.ok((await p.ev("DISH_MSGS")).includes(dish));
      await p.sleep(3500);
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
  });

  it("puts on a July 4th show with ?fireworks, and it ends within about 12 s", async () => {
    const p = await open("?fireworks&hour=22");
    try {
      let on = false, t0 = 0;
      for (let i = 0; i < 100 && !on; i++) { await p.sleep(100); on = await p.ev("!!fireworks"); }
      assert.ok(on, "no show started");
      t0 = await p.ev("airClock");
      await p.sleep(3000);
      assert.ok((await p.ev("fwN")) > 0, "no sparks in the air");
      assert.equal(await p.ev("dead"), false);
      let over = false;   // game time, not wall time: on a busy machine the game clock lags the real one
      for (let i = 0; i < 300 && !over; i++) { await p.sleep(100); over = await p.ev("!fireworks"); }
      assert.ok(over, "the show never ended");
      assert.ok((await p.ev("airClock")) - t0 <= 12, "it ran too long");
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
  });

  it("is chomped by a flytrap, shows the card and starts again; ?trap=0 grows none", async () => {
    const p = await open("?season=0&hour=12");
    try {
      await p.ev(`(() => { score = 5; pipes = pipes.filter(q => q.x + PIPE_W > birdX - HW); const q = pipes[0]; q.trap = makeTrap(); Object.assign(q.trap, { on: true, up: 1, e: 1, open: 1 });
        q.x = birdX - PIPE_W / 2 + 8; bird.y = q.bot - 20; bird.vy = 0; cooldown = 9; return 1; })()`);
      let card = false;
      for (let i = 0; i < 60 && !card; i++) { await p.sleep(100); card = await p.ev("dead && offT > 0"); }
      assert.ok(card, "the plant never took the bird");
      assert.equal(await p.ev("lastKind"), "trap");
      assert.equal(await p.ev("!!trapped"), true);
      assert.equal(await p.ev("stats.d.trap"), 1);
      let back = false;
      for (let i = 0; i < 90 && !back; i++) { await p.sleep(100); back = await p.ev("!dead"); }
      assert.ok(back, "it never restarted");
      assert.equal(await p.ev("trapped"), null);
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
    for (const [q, want] of [["?trap=0", false], ["?trap=5", true]]) {
      const b = await open(q);
      try {
        const got = await b.ev("TRAP.rate = 1000; score = 5; let n = 0; for (let i = 0; i < 30; i++) { spawn(); if (pipes[pipes.length - 1].trap) n++; } n > 0");
        assert.equal(got, want, q);
        assert.deepEqual(b.errors, []);
      } finally { await b.close(); }
    }
  });

  it("gets through a quake, a thunderstorm, a hawk and lightning", async () => {
    const p = await open("?season=1");
    try {
      await p.ev("startQuake(); 0"); await p.sleep(2500);
      assert.ok(await p.ev("!!quake"), "no quake");
      await p.ev("quake = null; quakeK = 0; fallen = []; reset(); seasonT = stormWindow()[0] + stormWindow()[1] * 0.4; 0"); await p.sleep(2000);
      assert.ok((await p.ev("ts.I")) > 0.3, "no storm");
      await p.ev("strike(2); strike(1); strike(0); 0"); await p.sleep(800);
      await p.ev("hawk = makeHawk(); 0"); await p.sleep(2000);
      await p.ev("struck = true; die(); 0"); await p.sleep(2500);
      assert.equal(await p.ev("lastKind"), "zap");
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
  });

  it("spends a quake's free pass on stunts", async () => {
    const p = await open("?season=1&flair=0");
    try {
      await p.ev("startQuake(); 0");
      // game time, not wall time: on a busy machine the game clock lags the real one
      let st = false;
      for (let i = 0; i < 150 && !st; i++) { await p.sleep(100); st = await p.ev("!!stunt || (!!quake && quake.t > QUAKE.rumble + 8)"); }
      assert.ok(await p.ev("!!quake && quake.fell"), "no quake");
      assert.ok(await p.ev("!!stunt"), "not in stunt mode in the free pass");
      assert.equal(await p.ev("dead"), false);
      const t0 = await p.ev("quake.t");
      for (let i = 0; i < 150 && (await p.ev("quake ? quake.t : 99")) < t0 + 6; i++) await p.sleep(100);   // a loop comes within a soar or two
      assert.equal(await p.ev("dead"), false);
      assert.deepEqual(p.errors, []);
    } finally { await p.close(); }
  });

  it("runs DISCO from the button, and puts everything back after", async () => {
    const p = await open("", PHONE);
    try {
      const before = await p.ev("[sunMul, SEASON.len]");
      await p.tap("#disco");
      await p.sleep(300);
      assert.ok(await p.ev("!!disco"), "the button did not start it");
      assert.equal(await p.ev(`document.getElementById("disco").getAttribute("aria-pressed")`), "true");
      assert.equal(await p.ev("sunMul"), 20);
      await p.sleep(2000);
      await p.ev("disco.t = 0.05; 0"); await p.sleep(400);
      assert.equal(await p.ev("disco"), null);
      assert.deepEqual(await p.ev("[sunMul, SEASON.len]"), before);
      await healthy(p, "after disco");
    } finally { await p.close(); }
  });

  it("moves the ENV setting from the slider and keeps it in the URL", async () => {
    const p = await open("", DESKTOP);
    try {
      await p.ev(`(() => { const w = document.getElementById("wind"); w.value = "1000"; w.dispatchEvent(new Event("input")); })()`);
      assert.equal(await p.ev("sunMul"), 20);
      assert.match(await p.ev("location.search"), /env=20/);
      assert.equal(await p.ev(`document.getElementById("windval").textContent`), "x20 extreme");
      await p.ev(`(() => { const w = document.getElementById("wind"); w.value = "0"; w.dispatchEvent(new Event("input")); })()`);
      assert.equal(await p.ev("sunMul"), 0);
      await healthy(p, "env off");
    } finally { await p.close(); }
  });

  it("shows ?fps and ?prof readouts", async () => {
    const p = await open("?fps&prof", TVSIZE, 3000);
    try {
      const [fps, prof] = await p.ev("[perfLine, profLines]");
      assert.match(fps[0], /^\d+ FPS \d+HZ/);
      assert.match(fps[1], /^SIM [\d.]+ DRAW [\d.]+ \d+X\d+ (GL|2D)$/);
      assert.ok(prof.length >= 3, "no profiler lines");
    } finally { await p.close(); }
  });
});
