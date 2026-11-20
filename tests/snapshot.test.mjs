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
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { launch, chromeBin, gameUrl } from "./lib/chrome.mjs";
import { ROOT } from "./lib/sandbox.mjs";

const SNAP = path.join(ROOT, "tests/snapshots"), OUT = path.join(ROOT, "tests/out");
const UPDATE = !!process.env.UPDATE_SNAPSHOTS;

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
const SCENES = [
  ["spring-day", "?season=0&hour=10", PH, "", 3],
  ["summer-storm", "?season=1&hour=14", PH, "die = () => {}; seasonT = stormWindow()[0] + stormWindow()[1] * 0.35; skin = 0.8; core = 0.6; until(() => ts.I > 0.9, 10); strike(1)", 0.1],   // (the bird can't die: this is about the storm)
  ["summer-sand-heaps", "?season=1&hour=11&sand=140", PH, "", 4],
  ["autumn-dusk", "?season=2&hour=18.4", PH, "", 3],
  ["winter-night-snow", "?season=3&hour=23&snow=120", PH, "", 3],
  ["quake", "?season=0&hour=12", PH, "run(16); startQuake()", 2.5],
  ["crash-stats-card", "?season=0&hour=9", PH, "run(4); die(birdX, bird.y, 'pipe')", 2.6],
  ["abduction", "?season=2&hour=23", PH, "ufoNight = null; ufoNext = 0; UFO.abductP = 1; until(() => abducted, 40)", 0.9],
  ["dish-morse", "?season=0&hour=23", PH, "abducted = true; die(); reset()", 5],
  ["disco", "?season=0&hour=12", PH, "startDisco()", 3],
  ["tv-night", "?tvs&season=3&hour=22", TV, "", 3],
  ["tv-day-shadows", "?tvs&season=1&hour=12", TV, "", 3],
];

describe("pixel snapshots", { skip: chromeBin ? false : "no Chrome installed", concurrency: 4 }, () => {
  let browser;
  before(async () => { browser = await launch(); fs.mkdirSync(SNAP, { recursive: true }); });
  after(async () => { await browser?.close(); });

  for (const [name, search, view, setup, secs] of SCENES) {
    it(name, async () => {
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
        const file = path.join(SNAP, name + ".png");
        const actual = Buffer.from(png.split(",")[1], "base64");
        if (UPDATE || !fs.existsSync(file)) { fs.writeFileSync(file, actual); return; }   // accepted (or the first run: the reference)
        // compare in the page (it can decode PNGs): how many pixels differ, and a diff image
        const ref = "data:image/png;base64," + fs.readFileSync(file).toString("base64");
        const r = await p.ev(`(async () => {
          const load = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
          const [a, b] = await Promise.all([load(${JSON.stringify(png)}), load(${JSON.stringify(ref)})]);
          if (a.width !== b.width || a.height !== b.height) return { size: [a.width, a.height, b.width, b.height] };
          const px = img => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height; const x = c.getContext("2d"); x.drawImage(img, 0, 0); return x.getImageData(0, 0, c.width, c.height); };
          const A = px(a), B = px(b), d = new ImageData(a.width, a.height);
          let n = 0;
          for (let i = 0; i < A.data.length; i += 4) {
            const same = A.data[i] === B.data[i] && A.data[i + 1] === B.data[i + 1] && A.data[i + 2] === B.data[i + 2] && A.data[i + 3] === B.data[i + 3];
            if (!same) n++;
            d.data[i] = same ? A.data[i] * 0.3 : 255; d.data[i + 1] = same ? A.data[i + 1] * 0.3 : 0; d.data[i + 2] = same ? A.data[i + 2] * 0.3 : 0; d.data[i + 3] = 255;
          }
          const c = document.createElement("canvas"); c.width = a.width; c.height = a.height; c.getContext("2d").putImageData(d, 0, 0);
          return { n, total: A.data.length / 4, diff: n ? c.toDataURL("image/png") : null };
        })()`);
        if (r.size) assert.fail(`${name}: size changed from ${r.size[2]}x${r.size[3]} to ${r.size[0]}x${r.size[1]}`);
        if (r.n) {
          fs.mkdirSync(OUT, { recursive: true });
          fs.writeFileSync(path.join(OUT, name + ".actual.png"), actual);
          fs.writeFileSync(path.join(OUT, name + ".diff.png"), Buffer.from(r.diff.split(",")[1], "base64"));
        }
        assert.equal(r.n, 0, `${name}: ${r.n} of ${r.total} pixels changed - see tests/out/${name}.diff.png (UPDATE_SNAPSHOTS=1 to accept)`);
      } finally { await p.close(); }
    });
  }
});
