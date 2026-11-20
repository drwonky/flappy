// Draw-cost benchmark, not a test: npm run bench
// Runs three scenes in WebGL and in Canvas 2D (?2d) under CPU throttling, reads the
// ?fps line (perfLine) and prints FPS, SIM and DRAW ms per frame and the DRAW speedup.
// BENCH_THROTTLE sets the CPU slowdown factor (default 6, about a slow TV).
import { launch, chromeBin, gameUrl } from "./lib/chrome.mjs";

if (!chromeBin) { console.error("no Chrome installed"); process.exit(1); }
const RATE = Number(process.env.BENCH_THROTTLE || 6);
const PHONE = { width: 390, height: 844, dpr: 3, mobile: true }, TV = { width: 1920, height: 1080, dpr: 1 };
const SCENES = [
  ["phone", "", PHONE],
  ["tv", "?tvs", TV],
  ["tv snow night", "?tvs&season=3&snow=200&hour=23", TV],
];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const median = a => [...a].sort((x, y) => x - y)[a.length >> 1];

async function measure(browser, search, view) {
  const p = await browser.page(view);
  try {
    await p.send("Emulation.setCPUThrottlingRate", { rate: RATE });
    await p.goto(gameUrl(search + (search ? "&" : "?") + "fps"), 8000);   // let the readout settle
    const fps = [], sim = [], draw = [];
    let renderer = "?";
    for (let i = 0; i < 3; i++) {
      const l = await p.ev("perfLine");   // refreshes about once a second, so 2 s apart gives fresh ones
      const a = /^(\d+) FPS/.exec(l[0] || ""), b = /^SIM ([\d.]+) DRAW ([\d.]+) \d+X\d+(?: (GL|2D))?/.exec(l[1] || "");
      if (a && b) { fps.push(+a[1]); sim.push(+b[1]); draw.push(+b[2]); renderer = b[3] || renderer; }
      if (i < 2) await sleep(2000);
    }
    if (!fps.length) throw new Error("no ?fps readout for " + search);
    return { renderer, fps: median(fps), sim: median(sim), draw: median(draw) };
  } finally { await p.close(); }
}

const browser = await launch();
const rows = [];
try {
  for (const [name, search, view] of SCENES) {
    const gl = await measure(browser, search, view);
    const two = await measure(browser, search + (search ? "&" : "?") + "2d", view);
    rows.push([name, gl, two]);
  }
} finally { await browser.close(); }

const pad = (s, n) => String(s).padEnd(n);
console.log(`CPU throttle x${RATE}`);
console.log(pad("scene", 16) + pad("renderer", 10) + pad("FPS", 6) + pad("SIM ms", 9) + pad("DRAW ms", 10) + "DRAW 2D/GL");
for (const [name, gl, two] of rows) {
  console.log(pad(name, 16) + pad(gl.renderer, 10) + pad(gl.fps, 6) + pad(gl.sim.toFixed(1), 9) + pad(gl.draw.toFixed(1), 10) + (two.draw / Math.max(gl.draw, 0.01)).toFixed(2) + "x");
  console.log(pad("", 16) + pad(two.renderer, 10) + pad(two.fps, 6) + pad(two.sim.toFixed(1), 9) + pad(two.draw.toFixed(1), 10));
}
