// Pixel snapshots: scenes set up from a seeded random and a frozen clock, stepped
// a fixed number of times and drawn once, compared pixel for pixel with
// tests/snapshots/<name>.png. Any change to how the game LOOKS fails here - which
// is the point when it was meant to be a speed-up, and the cue to look and then
// accept it when the change was meant:
//
//   UPDATE_SNAPSHOTS=1 npm test          (or: npm run test:update)
//
// A failure writes tests/out/<name>.actual.png and <name>.diff.png (changed pixels
// in red) to look at. The references depend on Chrome's rasteriser, so after a
// Chrome upgrade they may need re-accepting once. Skipped when no Chrome is installed.
//
// The references are the Canvas 2D look (every scene loads with &2d). A second block,
// "GL matches 2D", renders each scene in WebGL and in 2D and compares the two with a
// tolerance, since GL's filtering and rounding are never bit-identical (the GL side uses
// &shadow=classic). A third block, "GL shadow styles", compares the soft shadow styles with
// tests/snapshots/gl-<scene>-<style>.png (UPDATE_SNAPSHOTS=1 creates them).
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { launch, chromeBin, gameUrl } from "./lib/chrome.mjs";
import { ROOT } from "./lib/sandbox.mjs";

const SNAP = path.join(ROOT, "tests/snapshots"), OUT = path.join(ROOT, "tests/out");
const UPDATE = !!process.env.UPDATE_SNAPSHOTS;
// GL vs 2D: a pixel differs when its largest channel difference is over TOL_CH (0-255);
// a scene fails when more than TOL_PCT percent of its pixels differ.
// GL draws fractional and rotated edges hard where 2D smooths them (as agreed: it is pixel
// art), so a scene full of them gets its own limit: the quake's tilted pipes and rainbow rim.
const TOL_CH = 8, TOL_PCT = 1.0, TOL_SCENE = { quake: 2.0 };

// before the page's own script: one seeded random, a clock that only moves when
// the test says so, and no animation loop of its own (the test steps the game)
const PRELOAD = `
  (() => { let s = 12345; Math.random = () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; }; })();
  window.__now = 0; performance.now = () => window.__now; Date.now = () => 1763500000000 + window.__now;
  window.requestAnimationFrame = () => 0;
  try { localStorage.clear(); } catch (e) {}
`;

// [name, URL query, viewport, setup (in the page), seconds to step after it]
const PH = { width: 600, height: 900 }, TV = { width: 1280, height: 720 };
const TRAP_SET = "score = 5; pipes = pipes.filter(p => p.x + PIPE_W > birdX - HW); pipes[0].x = 200; pipes[0].bot = 250; pipes[0].top = 250 - gap; pipes[0].trap = makeTrap(r => 0.5); Object.assign(pipes[0].trap, { on: true, up: 1, e: 1, open: 1, age: 1 }); bird.y = 150; bird.vy = 0; cooldown = 9;";
const OLD_SCENES = [
  ["spring-day", "?season=0&hour=10", PH, "", 3],
  ["summer-storm", "?season=1&hour=14", PH, "die = () => {}; seasonT = stormWindow()[0] + stormWindow()[1] * 0.35; skin = 0.8; core = 0.6; until(() => ts.I > 0.9, 10); strike(1)", 0.1],   // (the bird can't die: this is about the storm)
  ["summer-sand-heaps", "?season=1&hour=11&sand=140", PH, "", 4],
  ["autumn-dusk", "?season=2&hour=18.4", PH, "", 3],
  ["winter-night-snow", "?season=3&hour=23&snow=120", PH, "", 3],
  ["quake", "?season=0&hour=12", PH, "run(16); startQuake()", 2.5],
  ["quake-loop", "?season=0&hour=12", PH, "run(16); startQuake(); until(() => stunt && stunt.k === 'loop' && stunt.t > stunt.dur * 0.5, 40)", 0.02],   // upside down at the top of a loop
  ["cactus-winter-lights", "?season=3&hour=22&snow=12", PH, "pipes = []; cacti = []; spawnCactus(170)", 0.05],
  ["cactus-spring-blossom", "?season=0&hour=11", PH, "pipes = []; cacti = []; spawnCactus(170)", 0.05],
  ["cactus-autumn-pumpkin", "?season=2&hour=19", PH, "pipes = []; cacti = []; spawnCactus(170); cacti[0].sd = 0.9", 0.05],
  ["trap-open", "?season=0&hour=12", PH, TRAP_SET, 0.01],
  ["trap-chomp", "?season=0&hour=12", PH, TRAP_SET + " pipes[0].x = birdX - PIPE_W / 2; bird.y = 232; pipes[0].trap.mode = 'snap'; until(() => dead, 1)", 0.5],   // jaws shut on the bird, the first feathers out
  ["crash-stats-card", "?season=0&hour=9", PH, "run(4); die(birdX, bird.y, 'pipe')", 2.6],
  ["abduction", "?season=2&hour=23", PH, "ufoNight = null; ufoNext = 0; UFO.abductP = 1; until(() => abducted, 40)", 0.9],
  ["dish-morse", "?season=0&hour=23", PH, "abducted = true; die(); reset()", 5],
  ["disco", "?season=0&hour=12", PH, "startDisco()", 3],
  ["tv-night", "?tvs&season=3&hour=22&burnsafe=0", TV, "", 3],
  ["tv-day-shadows", "?tvs&season=1&hour=12&burnsafe=0", TV, "", 3],
  ["fireworks-night", "?season=1&hour=22&fireworks", PH, "", 4.5],   // the show started at 1 s: about 4 s in
  ["blimp-fire-fall", "?season=1&hour=23&blimpfire", PH, "die = () => {}; seasonT = stormWindow()[0] + stormWindow()[1] * 0.35", 6.3],   // lightning hit it at 3 s: about 3 s into the fall
  ["blimp-wreck-blaze", "?season=0&hour=23&blimpfire", PH, "die = () => {}", 12],   // down at about 8.5 s: the wreck in full blaze
  ["fireworks-finale", "?season=1&hour=19.5&fireworks", PH, "", 9],   // about 8.5 s in: the barrage
];
// (the older scenes are pinned with &holidays=0: Christmas and Good Friday are dates on the year's clock, and the ones that run into them
// - winter-night-snow, tv-night, quake, quake-loop, disco, blimp-wreck-blaze - would otherwise look different, and by the year's Easter)
const PIN = "&holidays=0";
// Christmas and Easter: started by their flags a second in (the scene's setup is the 0.5 s in), the clock set so the sky is as it should be
const EGGS = "run(12.3); for (let i = 0; i < 7; i++) Object.assign(eggs[i], { on: true, ex: dist + 24 + i * 38, y: SKY + 5 + (i % 3) * 2, gy: SKY + 5 + (i % 3) * 2, vx: 0, vy: 0, rest: true, nb: 2, kind: i % 3, col: i % 6 }); " +
  "Object.assign(eggs[7], { on: true, ex: dist + 120, y: SKY - 40, gy: SKY + 7, vx: 0, vy: 0, rest: false, nb: 0, kind: 1, col: 3 }); Object.assign(eggs[8], { on: true, ex: dist + 200, y: SKY - 14, gy: SKY + 6, vx: 0, vy: -90, rest: false, nb: 1, kind: 2, col: 1 });";
const SCENES = [
  ...OLD_SCENES.map(([n, q, ...r]) => [n, q + PIN, ...r]),
  ["christmas-santa", "?santa&hour=22&season=3" + PIN, PH, "die = () => {}; pipes = []; since = -1e9", 6.2],        // Santa half way across at about 5.7 s into it, the star at its brightest
  ["easter-blood-moon", "?easter&hour=22&season=0" + PIN, PH, "", 7.1],     // about 6.6 s into Easter: the shadow most of the way over the moon
  ["tv-burnsafe-hud", "?tvs&season=1&hour=12" + PIN, TV, "hudClock = 200", 3],   // BURNSAFE on (the ?tvs default): the HUD dimmed (score 80%, the rest 65%) and drifted off its place by a px or two
  ["easter-sunrise", "?easter&hour=9&season=0" + PIN, PH, EGGS, 0.45],      // about 12.3 s in: gold, the bunny, lilies, eggs on the ground and two in the air
];

// render one scene on a fresh page; returns { p, png } (the caller closes p)
async function render(browser, search, view, setup, secs) {
  const p = await browser.page({ ...view, dpr: 1, preload: PRELOAD });
  try {
    await p.goto(gameUrl(search + "&lowres"), 0);   // ?lowres: one canvas pixel per game pixel, small files
    const png = await p.ev(`(() => {
      const run = s => { for (let i = 0, n = Math.round(s * 120); i < n; i++) { step(1 / 120); window.__now += 1000 / 120; } };
      const until = (f, s) => { for (let i = 0; i < s * 120 && !f(); i++) run(1 / 120); };
      run(0.5);
      ${setup};
      run(${secs});
      draw();
      return buf.toDataURL("image/png");
    })()`);
    assert.deepEqual(p.errors, [], "errors in the page");
    return { p, png };
  } catch (e) { await p.close(); throw e; }
}

// compare two PNG data URLs in the page (it can decode PNGs): the number of pixels whose
// largest channel difference is over tol, and a diff image (changed pixels in red)
function compare(p, a, b, tol) {
  return p.ev(`(async () => {
    const load = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
    const [a, b] = await Promise.all([load(${JSON.stringify(a)}), load(${JSON.stringify(b)})]);
    if (a.width !== b.width || a.height !== b.height) return { size: [a.width, a.height, b.width, b.height] };
    const px = img => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; const x = c.getContext("2d"); x.drawImage(img, 0, 0); return x.getImageData(0, 0, c.width, c.height); };
    const A = px(a), B = px(b), d = new ImageData(a.width, a.height);
    let n = 0;
    for (let i = 0; i < A.data.length; i += 4) {
      const m = Math.max(Math.abs(A.data[i] - B.data[i]), Math.abs(A.data[i + 1] - B.data[i + 1]), Math.abs(A.data[i + 2] - B.data[i + 2]), Math.abs(A.data[i + 3] - B.data[i + 3]));
      const same = m <= ${tol};
      if (!same) n++;
      d.data[i] = same ? A.data[i] * 0.3 : 255; d.data[i + 1] = same ? A.data[i + 1] * 0.3 : 0; d.data[i + 2] = same ? A.data[i + 2] * 0.3 : 0; d.data[i + 3] = 255;
    }
    const c = document.createElement("canvas"); c.width = a.width; c.height = a.height; c.getContext("2d").putImageData(d, 0, 0);
    return { n, total: A.data.length / 4, diff: n ? c.toDataURL("image/png") : null };
  })()`);
}

const bytes = url => Buffer.from(url.split(",")[1], "base64");
const dataUrl = buf => "data:image/png;base64," + buf.toString("base64");
const writeOut = (file, data) => { fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, file), data); };

describe("pixel snapshots", { skip: chromeBin ? false : "no Chrome installed", concurrency: 4 }, () => {
  let browser;
  before(async () => { browser = await launch(); fs.mkdirSync(SNAP, { recursive: true }); });
  after(async () => { await browser?.close(); });

  for (const [name, search, view, setup, secs] of SCENES) {
    it(name, async () => {
      const { p, png } = await render(browser, search + "&2d", view, setup, secs);
      try {
        const file = path.join(SNAP, name + ".png");
        const actual = bytes(png);
        if (UPDATE || !fs.existsSync(file)) { fs.writeFileSync(file, actual); return; }   // accepted (or the first run: the reference)
        const r = await compare(p, png, dataUrl(fs.readFileSync(file)), 0);
        if (r.size) assert.fail(`${name}: size changed from ${r.size[2]}x${r.size[3]} to ${r.size[0]}x${r.size[1]}`);
        if (r.n) {
          writeOut(name + ".actual.png", actual);
          writeOut(name + ".diff.png", bytes(r.diff));
        }
        assert.equal(r.n, 0, `${name}: ${r.n} of ${r.total} pixels changed - see tests/out/${name}.diff.png (UPDATE_SNAPSHOTS=1 to accept)`);
      } finally { await p.close(); }
    });
  }
});

describe("GL matches 2D", { skip: chromeBin ? false : "no Chrome installed", concurrency: 4 }, () => {
  let browser;
  before(async () => { browser = await launch(); });
  after(async () => { await browser?.close(); });

  for (const [name, search, view, setup, secs] of SCENES) {
    it(name, async t => {
      const gl = await render(browser, search + "&shadow=classic", view, setup, secs);   // (the new shadow styles have no 2D twin)
      let two;
      try {
        const r = await gl.p.ev("typeof RENDERER === 'undefined' ? null : RENDERER");
        if (r !== "GL") { t.skip(`WebGL unavailable here (RENDERER is ${r})`); return; }
        two = await render(browser, search + "&2d", view, setup, secs);
        assert.equal(await two.p.ev("RENDERER"), "2D");
        const d = await compare(gl.p, gl.png, two.png, TOL_CH);
        if (d.size) assert.fail(`${name}: GL is ${d.size[0]}x${d.size[1]}, 2D is ${d.size[2]}x${d.size[3]}`);
        const pct = 100 * d.n / d.total;
        const lim = TOL_SCENE[name] ?? TOL_PCT;
        if (pct > lim) {
          writeOut(name + ".gl.png", bytes(gl.png));
          writeOut(name + ".2d.png", bytes(two.png));
          writeOut(name + ".gldiff.png", bytes(d.diff));
        }
        assert.ok(pct <= lim, `${name}: ${pct.toFixed(2)}% of pixels differ by more than ${TOL_CH} (limit ${lim}%) - see tests/out/${name}.gldiff.png`);
        if (process.env.GL_DIFF_LOG) console.log(`GLDIFF ${name} ${pct.toFixed(3)}%`);
      } finally { await gl.p.close(); await two?.p.close(); }
    });
  }
});

// the soft shadow styles (GL only): references of their own, a small tolerance since SwiftShader
// is deterministic on one machine but not necessarily across versions
const STYLE_SCENES = [
  ["summer-long", "?season=1&hour=8", PH, "", 3],
  ["tv-afternoon", "?tvs&season=1&hour=16&burnsafe=0", TV, "", 3],
];
const STYLES = ["dither", "smooth", "blocky", "off"];
describe("GL shadow styles", { skip: chromeBin ? false : "no Chrome installed", concurrency: 4 }, () => {
  let browser;
  before(async () => { browser = await launch(); fs.mkdirSync(SNAP, { recursive: true }); });
  after(async () => { await browser?.close(); });

  for (const [scene, search, view, setup, secs] of STYLE_SCENES) {
    const shots = {};
    for (const style of STYLES) {
      it(`${scene} ${style}`, async t => {
        const name = `gl-${scene}-${style}`, r = await render(browser, search + "&shadow=" + style, view, setup, secs);
        try {
          if (await r.p.ev("RENDERER") !== "GL") { t.skip("WebGL unavailable here"); return; }
          assert.equal(await r.p.ev("SHADOW_STYLE"), style);
          shots[style] = r.png;
          const file = path.join(SNAP, name + ".png"), actual = bytes(r.png);
          if (UPDATE || !fs.existsSync(file)) { fs.writeFileSync(file, actual); return; }
          const d = await compare(r.p, r.png, dataUrl(fs.readFileSync(file)), TOL_CH);
          if (d.size) assert.fail(`${name}: size changed from ${d.size[2]}x${d.size[3]} to ${d.size[0]}x${d.size[1]}`);
          const pct = 100 * d.n / d.total;
          if (pct > TOL_PCT) { writeOut(name + ".actual.png", actual); writeOut(name + ".diff.png", bytes(d.diff)); }
          assert.ok(pct <= TOL_PCT, `${name}: ${pct.toFixed(2)}% of pixels differ by more than ${TOL_CH} (limit ${TOL_PCT}%) - see tests/out/${name}.diff.png (UPDATE_SNAPSHOTS=1 to accept)`);
        } finally { await r.p.close(); }
      });
    }
    it(`${scene}: shadows actually draw (off differs from dither)`, async t => {
      const [a, b] = await Promise.all([render(browser, search + "&shadow=off", view, setup, secs), render(browser, search + "&shadow=dither", view, setup, secs)]);
      try {
        if (await a.p.ev("RENDERER") !== "GL") { t.skip("WebGL unavailable here"); return; }
        const d = await compare(a.p, a.png, b.png, 0);
        assert.ok(d.n > 200, `${scene}: dither differs from off in only ${d.n} pixels`);
      } finally { await a.p.close(); await b.p.close(); }
    });
  }
});

// the CRT screen styles (GL only): the snapshots above are of the SCENE, taken before the last pass, so the
// scanline beams, phosphor masks and bloom are checked here, on the screen canvas itself. A viewport where
// the game is drawn 3 device px per game px (the whole-pixel size the delta/slot styles use), at DPR 1.
const SCREEN_VIEW = { width: 900, height: 1700 }, SCREEN_CROP = [200, 300, 420, 420];
const SCREEN_STYLES = [["delta", "?scan=delta"], ["slot", "?scan=slot"], ["delta-nobloom", "?scan=delta&bloom=0"], ["lines", "?scan=lines"]];
describe("GL screen styles", { skip: chromeBin ? false : "no Chrome installed", concurrency: 1 }, () => {
  let browser;
  const shots = {};
  before(async () => { browser = await launch(); fs.mkdirSync(SNAP, { recursive: true }); });
  after(async () => { await browser?.close(); });

  for (const [style, q] of SCREEN_STYLES) {
    it(style, async t => {
      const name = `gl-screen-${style}`;
      const p = await browser.page({ ...SCREEN_VIEW, dpr: 1, preload: PRELOAD });
      try {
        await p.goto(gameUrl(q + "&season=0&hour=10&lowres&crtfit=exact"), 0);   // (exact: one device px grid to compare)
        const png = await p.ev(`(() => {
          if (RENDERER !== "GL") return null;
          for (let i = 0, n = Math.round(3.5 * 120); i < n; i++) { step(1 / 120); window.__now += 1000 / 120; }
          draw();
          return GLR.screenDataURL(${SCREEN_CROP.join(", ")});
        })()`);
        if (!png) { t.skip("WebGL unavailable here"); return; }
        assert.deepEqual(p.errors, [], "errors in the page");
        if (style !== "lines") assert.equal(await p.ev("DS"), 3, "this viewport should give 3 device px per game px");
        shots[style] = png;
        const file = path.join(SNAP, name + ".png"), actual = bytes(png);
        if (UPDATE || !fs.existsSync(file)) { fs.writeFileSync(file, actual); return; }
        const d = await compare(p, png, dataUrl(fs.readFileSync(file)), TOL_CH);
        if (d.size) assert.fail(`${name}: size changed from ${d.size[2]}x${d.size[3]} to ${d.size[0]}x${d.size[1]}`);
        const pct = 100 * d.n / d.total;
        if (pct > TOL_PCT) { writeOut(name + ".actual.png", actual); writeOut(name + ".diff.png", bytes(d.diff)); }
        assert.ok(pct <= TOL_PCT, `${name}: ${pct.toFixed(2)}% of pixels differ by more than ${TOL_CH} (limit ${TOL_PCT}%) - see tests/out/${name}.diff.png (UPDATE_SNAPSHOTS=1 to accept)`);
      } finally { await p.close(); }
    });
  }
  it("delta differs from lines, and bloom=0 from bloom", async t => {
    if (!shots.delta || !shots.lines || !shots["delta-nobloom"]) { t.skip("the style tests above did not run"); return; }
    const p = await browser.page({ width: 300, height: 300 });
    try {
      await p.goto("about:blank", 0);
      const a = await compare(p, shots.delta, shots.lines, 8), b = await compare(p, shots.delta, shots["delta-nobloom"], 8);
      assert.ok(a.n > a.total * 0.3, `delta looks like lines (${a.n} of ${a.total} pixels differ)`);
      assert.ok(b.n > 200, `bloom=0 looks like bloom (${b.n} pixels differ)`);
    } finally { await p.close(); }
  });
});
