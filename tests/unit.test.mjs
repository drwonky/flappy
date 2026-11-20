// Logic tests: the game's script runs in Node (tests/lib/sandbox.mjs), no browser.
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { loadGame, memoryStorage } from "./lib/sandbox.mjs";

const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg ?? ""} expected ${b} +- ${eps}, got ${a}`);

describe("morse transmission", () => {
  const g = loadGame();
  it("has a code for every letter the dish can send", () => {
    const msgs = g.ev("DISH_MSGS"), MORSE = g.ev("MORSE");
    for (const m of msgs) for (const ch of m) if (ch !== " ") assert.ok(MORSE[ch], `no morse for "${ch}" in "${m}"`);
    for (const ch of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") assert.match(MORSE[ch], /^[.-]+$/);
  });
  it("uses standard timing: dot 1, dash 3, gaps 1 / 3 / 7 units", () => {
    const plan = g.ev("morsePlan");
    assert.deepEqual(plan("ET").on.map(o => [o[0], o[1]]), [[0, 1], [4, 7]]);   // E . then a letter gap of 3, T -
    assert.equal(plan("E").len, 4);                                              // a letter is followed by a letter gap
    assert.equal(plan("EE").len, 8);
    assert.equal(plan("E E").len, 12);                                           // a word gap is 7
    assert.equal(plan("S").len, 1 + 1 + 1 + 1 + 1 + 3);
  });
  it("plans the four messages at their known lengths", () => {
    const lens = g.ev("DISH_MSGS.map(m => morsePlan(m).len)");
    assert.deepEqual(lens, [114, 106, 122, 326]);
  });
  it("keys long messages faster so none runs past DISH.maxTx", () => {
    const maxTx = g.ev("DISH.maxTx"), unit = g.ev("DISH.unit");
    for (let i = 0; i < 40; i++) {
      const d = g.ev("makeDish()");
      assert.ok(g.ev("DISH_MSGS").includes(d.msg));
      assert.ok(d.unit <= unit + 1e-9);
      assert.ok(d.plan.len * d.unit <= maxTx + 1e-9, `${d.msg} takes ${d.plan.len * d.unit}s`);
    }
  });
  it("picks every message sooner or later", () => {
    const seen = new Set();
    for (let i = 0; i < 200; i++) seen.add(g.ev("makeDish().msg"));
    assert.equal(seen.size, 4);
  });
});

describe("ENV slider scale", () => {
  const g = loadGame();
  const s2w = g.ev("sliderToWind"), w2s = g.ev("windToSlider"), label = g.ev("windLabel");
  it("has OFF at the far left and x20 at the far right", () => {
    assert.equal(s2w(0), 0);
    assert.equal(s2w(1000), 20);
    assert.equal(w2s(0), 0);
  });
  it("snaps to the x1 default", () => {
    assert.equal(s2w(w2s(1)), 1);
    assert.equal(s2w(w2s(1) + 3), 1);
  });
  it("round-trips readable values", () => {
    for (const w of [0.1, 0.2, 0.5, 2, 3, 5, 10, 20]) near(s2w(w2s(w)), w, w * 0.06, `x${w}`);
  });
  it("never goes down as the thumb moves right", () => {
    let prev = -1;
    for (let t = 0; t <= 1000; t++) { const w = s2w(t); assert.ok(w >= prev, `slider ${t}: ${w} < ${prev}`); prev = w; }
  });
  it("labels the settings", () => {
    assert.equal(label(0), "off");
    assert.equal(label(1), "x1");
    assert.equal(label(3), "x3 harsh");
    assert.equal(label(20), "x20 extreme");
  });
});

describe("stats", () => {
  it("puts each ENV value in the right bracket", () => {
    const g = loadGame();
    const br = v => g.ev(`ENV_BR[ENV_BR.findIndex(b => b[1](${v}))][0]`);
    const want = { 0: "OFF", 0.1: "x0.1-1", 0.99: "x0.1-1", 1: "x1", 1.05: "x1-2", 2: "x1-2", 2.1: "x2-20", 19: "x2-20", 20: "x20", 50: "x20" };
    for (const [v, b] of Object.entries(want)) assert.equal(br(v), b, `env ${v}`);
  });
  it("records runs, causes, the average and max per bracket, and the max score", () => {
    const g = loadGame();
    g.ev(`sunMul = 1; score = 10; recordRun("pipe"); score = 30; recordRun("hawk"); sunMul = 0; score = 7; recordRun("ufo")`);
    const s = g.ev("stats");
    assert.equal(s.runs, 3);
    assert.equal(s.max, 30);
    assert.equal(s.d.pipe, 1); assert.equal(s.d.hawk, 1); assert.equal(s.d.ufo, 1); assert.equal(s.d.zap, 0);
    assert.deepEqual(s.e[2], [40, 2, 30]);           // x1: sum, runs, max
    assert.deepEqual(s.e[0], [7, 1, 7]);             // OFF
    assert.equal(g.ev("lastKind"), "ufo"); assert.equal(g.ev("lastBr"), 0);
  });
  it("names each kind of death", () => {
    const g = loadGame();
    const kind = setup => { g.ev(`reset(); ${setup}`); return g.ev("lastKind"); };
    assert.equal(kind(`die(birdX, bird.y, "pipe")`), "pipe");
    assert.equal(kind(`die(birdX, SKY - 2, "ground")`), "ground");
    assert.equal(kind(`die(birdX, 2, "ground")`), "ceiling");
    assert.equal(kind(`struck = true; die()`), "zap");
    assert.equal(kind(`grabbed = true; die()`), "hawk");
    assert.equal(kind(`abducted = true; die()`), "ufo");
    assert.equal(g.ev("stats.runs"), 6);
  });
  it("keeps the stats in the browser across visits", () => {
    const storage = memoryStorage();
    const a = loadGame({ storage });
    a.ev(`score = 12; recordRun("pipe")`);
    const b = loadGame({ storage });
    assert.equal(b.ev("stats.runs"), 1);
    assert.equal(b.ev("stats.max"), 12);
    assert.equal(b.ev("stats.d.pipe"), 1);
  });
  it("clears them with ?resetstats", () => {
    const storage = memoryStorage();
    loadGame({ storage }).ev(`score = 5; recordRun("pipe")`);
    const b = loadGame({ storage, search: "?resetstats" });
    assert.equal(b.ev("stats.runs"), 0);
    assert.equal(storage.getItem("flappy-stats"), null);
  });
  it("survives a corrupt or old saved record", () => {
    for (const bad of ["{not json", '{"runs":"x","d":5,"e":[1,[2]]}', "null"]) {
      const g = loadGame({ storage: memoryStorage({ "flappy-stats": bad }) });
      assert.ok(Number.isFinite(g.ev("stats.runs")));
      g.ev(`score = 3; recordRun("pipe")`);
      assert.equal(g.ev("stats.e.length"), 6);
    }
  });
  it("adds the run when the bird dies (once per death)", () => {
    const g = loadGame();
    g.run(2);
    g.ev(`die(birdX, bird.y, "pipe")`);
    g.run(1);
    assert.equal(g.ev("stats.runs"), 1);
  });
});

describe("frame pacing", () => {
  // drive paceFrame() with made-up rAF timestamps and look at how far each frame moves the world
  // work: [min, max] ms a frame takes to make; a frame still being made when the next refresh comes misses it
  function drive({ hz, jitter = 0, frames = 900, work = null, hzcap = 0, seed = 3 }) {
    const g = loadGame({ seed });
    const make = g.ev("makePacer"), pace = g.ev("paceFrame"), FIXED = g.FIXED;
    let r = seed; const rnd = () => ((r = (r * 16807) % 2147483647) / 2147483647);
    const P = make(0, hzcap), out = [];
    let busy = 0;
    for (let v = 1; v <= frames; v++) {
      const now = v * 1000 / hz + (rnd() * 2 - 1) * jitter;
      if (now < busy) continue;                     // still working on the last frame: this refresh is missed
      const f = pace(P, now);
      if (f && v > frames / 3) out.push(f);
      if (f && work) busy = now + work[0] + (work[1] - work[0]) * rnd();
    }
    for (const f of out) assert.ok(f.h <= FIXED * 1.12 + 1e-9, `sub-step ${f.h} too long`);
    const dts = out.map(f => f.n * f.h * 1000);
    const mean = dts.reduce((a, b) => a + b, 0) / dts.length;
    const sd = Math.sqrt(dts.reduce((a, b) => a + (b - mean) ** 2, 0) / dts.length);
    return { P, out, mean, sd, steps: new Set(out.map(f => f.n)) };
  }
  for (const [hz, steps, jitter] of [[60, 2, 2], [59.94, 2, 2], [50, 3, 2], [120, 1, 1], [144, 1, 1]]) {
    it(`moves every frame the same amount at ${hz} Hz despite +-${jitter} ms of timer jitter`, () => {
      const r = drive({ hz, jitter });
      near(1 / r.P.vsync, hz, hz * 0.02, "learned refresh");
      near(r.mean, 1000 / hz, 0.1, "frame time");
      assert.ok(r.sd < 0.2, `frame-to-frame spread ${r.sd} ms`);
      assert.deepEqual([...r.steps], [steps]);
    });
  }
  it("covers a dropped frame with exactly two refreshes' worth", () => {
    const g = loadGame();
    const P = g.ev("makePacer")(0, 0), pace = g.ev("paceFrame");
    let t = 0;
    for (let i = 0; i < 120; i++) pace(P, (t += 1000 / 60));
    const f = pace(P, (t += 2000 / 60));
    near(f.n * f.h, 2 / 60, 1e-3);
    assert.equal(f.k, 2);
  });
  it("settles a 120 Hz screen it can't keep up with on a steady 60", () => {
    const r = drive({ hz: 120, work: [6, 8.75], frames: 2400 });   // ~15% of frames take longer than 8.3 ms
    assert.equal(r.P.every, 2);
    const steady = r.out.filter(f => Math.abs(f.n * f.h * 1000 - 1000 / 60) < 0.2).length / r.out.length;
    assert.ok(steady >= 0.99, `only ${(100 * steady).toFixed(1)}% of frames at 16.7 ms`);
  });
  it("leaves a 120 Hz screen alone when it keeps up", () => {
    const r = drive({ hz: 120, frames: 2400 });
    assert.equal(r.P.every, 1);
  });
  it("never halves a 60 Hz screen, even when it misses frames", () => {
    assert.equal(drive({ hz: 60, work: [10, 19], frames: 1200 }).P.every, 1);
  });
  it("honours ?hz=60 on a 120 Hz screen and still learns the true refresh", () => {
    const r = drive({ hz: 120, hzcap: 60, frames: 1200 });
    assert.equal(r.P.every, 2);
    near(1 / r.P.vsync, 120, 2);
    near(r.mean, 1000 / 60, 0.2);
  });
  it("moves nothing on a first frame stamped before the page started", () => {
    const g = loadGame();
    const P = g.ev("makePacer")(1000, 0);
    assert.equal(g.ev("paceFrame")(P, 990).n, 0);
  });
  it("plays slow rather than catching up more than 0.1 s at once", () => {
    const g = loadGame();
    const P = g.ev("makePacer")(0, 0), pace = g.ev("paceFrame");
    pace(P, 16.7);
    const f = pace(P, 16.7 + 900);
    near(f.n * f.h, 0.1, 1e-9);
  });
});

describe("visual-only effects step once per drawn frame", () => {
  it("moves the rain once per frame in the game loop, every step otherwise", () => {
    const g = loadGame({ search: "?season=0" });
    let calls = 0;
    g.ev("stepRain = (f => dt => { __calls(); return f(dt); })(stepRain)".replace("__calls()", "globalThis.__rainCalls = (globalThis.__rainCalls || 0) + 1"));
    globalThis.__rainCalls = 0;
    g.run(1);                                       // direct step() calls: lastSub stays true
    calls = globalThis.__rainCalls;
    assert.equal(calls, 120);
    globalThis.__rainCalls = 0;
    g.ev("for (let f = 0; f < 60; f++) for (let i = 0; i < 2; i++) { lastSub = i === 1; step(1/120); } lastSub = true");
    assert.equal(globalThis.__rainCalls, 60);
    delete globalThis.__rainCalls;
  });
});

describe("quakes", () => {
  it("never come twice in one pass of the seasons (112 s)", () => {
    const g = loadGame({ search: "?season=1", seed: 9 });
    const starts = [];
    globalThis.__q = () => starts.push(g.ev("airClock"));
    g.ev("QUAKE.rate = 1/20; startQuake = (f => () => { if (!quake && !dead) globalThis.__q(); return f(); })(startQuake)");
    g.run(20 * 60);
    delete globalThis.__q;
    const pass = 4 * g.ev("SEASON.len");          // the requirement, not the game's own setting
    assert.equal(pass, 112);
    assert.ok(starts.length >= 3, `only ${starts.length} quakes in 20 minutes at a high rate`);
    for (let i = 1; i < starts.length; i++) assert.ok(starts[i] - starts[i - 1] >= pass, `quakes ${(starts[i] - starts[i - 1]).toFixed(0)} s apart`);
  });
  it("bring the pipes back up in a band around the middle, never all at one height", () => {
    const g = loadGame({ search: "?season=1", seed: 4 });
    const tops = [];
    for (let i = 0; i < 60; i++) { g.ev("quake = { t: 2, fell: true }; spawn(); quakeSpawn()"); const f = g.ev("fallen[fallen.length - 1]"); if (f) tops.push(f.p.top); g.ev("fallen = []; quake = null"); }
    assert.ok(tops.length > 30, "quakeSpawn made no fallen pipes");
    const mid = g.ev("QUAKE.mid - GAP0 / 2"), spread = g.ev("QUAKE.spread");
    for (const t of tops) assert.ok(Math.abs(t - mid) <= spread + 1e-6, `top ${t} outside ${mid} +- ${spread}`);
    assert.ok(Math.max(...tops) - Math.min(...tops) > spread, "heights barely vary");
  });
});

describe("flying saucer", () => {
  it("visits at most once a night, and most nights", () => {
    const g = loadGame({ search: "?daylen=60&hour=17", seed: 5 });
    const visits = {};
    globalThis.__v = n => (visits[n] = (visits[n] || 0) + 1);
    let had = false;
    g.run(60 * 12, () => {                          // a 60 s day: 12 nights
      const now = !!g.ev("ufo");
      if (now && !had) globalThis.__v(g.ev("hour >= 12 ? dayN : dayN - 1"));
      had = now;
    });
    delete globalThis.__v;
    const counts = Object.values(visits);
    assert.ok(Math.max(...counts) === 1, `a night had ${Math.max(...counts)} visits`);
    assert.ok(counts.length >= 6, `only ${counts.length} of ~12 nights had a visit`);
  });
  it("leaves a dish behind in the next round after an abduction", () => {
    const g = loadGame();
    g.ev("abducted = true; die(); reset()");
    const d = g.ev("dish");
    assert.ok(d && g.ev("DISH_MSGS").includes(d.msg));
    g.ev("die(birdX, bird.y, 'pipe'); reset()");
    assert.equal(g.ev("dish"), null);
  });
  it("never comes with ?noclock", () => {
    const g = loadGame({ search: "?noclock&daylen=60", seed: 5 });
    let seen = false;
    g.run(300, () => { if (g.ev("ufo")) seen = true; });
    assert.equal(seen, false);
  });
});

describe("determinism", () => {
  it("plays the same game twice from the same seed", () => {
    const trace = () => { const g = loadGame({ seed: 77 }); const s = []; g.run(90, i => { if (i % 600 === 0) s.push(g.ev("[score, Math.round(bird.y), pipes.length, dead]").join(",")); }); return s.join("|"); };
    assert.equal(trace(), trace());
  });
});
