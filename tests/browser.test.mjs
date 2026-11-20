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

  it("keeps the canvas under BUF_MAX pixels even on a 4K screen", async () => {
    const p = await open("?tvs", { width: 1920, height: 1080, dpr: 2 });
    try {
      const b = await p.ev("[buf.width, buf.height, BUF_MAX, R]");
      assert.ok(b[0] * b[1] <= b[2], `canvas ${b[0]}x${b[1]}`);
      assert.equal(b[3], 2);
      await healthy(p, "4K");
    } finally { await p.close(); }
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
      assert.match(fps[1], /^SIM [\d.]+ DRAW [\d.]+ \d+X\d+$/);
      assert.ok(prof.length >= 3, "no profiler lines");
    } finally { await p.close(); }
  });
});
