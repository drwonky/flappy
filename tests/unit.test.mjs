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

describe("quake stunts", () => {
  const TAU = Math.PI * 2, wrap = a => a - TAU * Math.round(a / TAU);
  // one seeded quake, from its start to 8 s after the last pipe has stood up again; calls each(g) every step
  // (stops early if the bird dies, which is for the caller to judge)
  function quakeRun(seed, each) {
    const g = loadGame({ search: "?flair=0&season=1", seed });
    g.run(4); g.ev("startQuake()");
    let over = 0;
    for (let i = 0; i < 120 * 90 && over <= 120 * 8; i++) {
      g.run(1 / 120);
      each(g, over / 120);
      if (g.ev("dead")) break;
      if (!g.ev("quake")) over++;
    }
    return g;
  }
  it("loop the bird at least once in a free pass, and never kill it from the rumble to 8 s after the rise", () => {
    // (the autopilot flying a normal pipe, a few s after the rise, can still miss now and then - 1 game in 40 with or without
    // stunts - so a death in the last 5 s of the window is tolerated up to twice; in the quake or just after it never)
    let late = 0;
    for (let seed = 1; seed <= 20; seed++) {
      let spin = 0, prev = null;
      const g = quakeRun(seed, (g, after) => {
        if (g.ev("dead")) { assert.ok(after >= 3, `seed ${seed}: the bird died ${after.toFixed(1)} s after the rise (quake t ${g.ev("quake && quake.t")})`); late++; return; }
        const [on, rot] = g.ev("[!!stunt, birdRot()]");
        if (on) { if (prev !== null) spin += Math.abs(wrap(rot - prev)); }
        prev = on ? rot : null;
      });
      assert.ok(spin >= TAU * 0.98, `seed ${seed}: turned only ${(spin / TAU).toFixed(2)} turns`);
    }
    assert.ok(late <= 2, `${late} of 20 died late in the window`);
  });
  it("keep the bird inside the safe band, and its y and angle continuous", () => {
    for (let seed = 21; seed <= 26; seed++) {
      let py = null, pr = null, was = false;
      quakeRun(seed, g => {
        const [on, y, rot, SKY] = g.ev("[!!stunt, bird.y, birdRot(), SKY]");
        if (on) { assert.ok(y >= 36 && y <= SKY - 36, `y ${y} left the band`); }
        if (on && was) {                              // within a stunt (the blend in and the path itself)
          assert.ok(Math.abs(y - py) < 5, `y jumped ${y - py}`);
          assert.ok(Math.abs(wrap(rot - pr)) < 0.25, `angle jumped ${wrap(rot - pr)}`);
        }
        py = y; pr = rot; was = on;
      });
    }
  });
  it("only run in their window, and are off once the quake is over", () => {
    for (let seed = 31; seed <= 35; seed++) {
      let seen = 0;
      quakeRun(seed, g => {
        const [on, q, from, end, rise] = g.ev("[!!stunt, quake ? quake.t : -1, STUNT.from, STUNT.end, quakeT1()]");
        if (on) { seen++; assert.ok(q >= from && q <= rise - end + 0.02, `stunt at quake t=${q}`); }
        if (q < 0) assert.equal(on, false, "stunt after the quake");
      });
      assert.ok(seen > 120 * 15, `seed ${seed}: only ${seen} steps of stunts`);
    }
  });
  it("end with the bird level in a gap before the pipes rise, and clear on reset and on death", () => {
    const g = loadGame({ search: "?flair=0&season=1", seed: 3 });
    g.run(4); g.ev("startQuake()");
    g.run(5);
    assert.ok(g.ev("!!stunt"));
    g.ev("die(); reset()");
    assert.equal(g.ev("stunt"), null);
    assert.equal(g.ev("stX"), 0);
    g.run(4); g.ev("startQuake()"); g.run(5);
    assert.ok(g.ev("!!stunt"));
    g.run(g.ev("quakeT1()") - 5 - g.ev("quake.t") + 0.1);
    assert.equal(g.ev("stunt"), null);
    assert.ok(Math.abs(g.ev("bird.vy")) < 400);
  });
  it("stop for a hawk or the saucer", () => {
    const g = loadGame({ search: "?flair=0&season=1", seed: 3 });
    g.run(4); g.ev("startQuake()"); g.run(5);
    assert.ok(g.ev("!!stunt"));
    g.ev("hawk = {}"); g.run(0.05);
    assert.equal(g.ev("stunt"), null);
    g.ev("hawk = null; ufo = {}"); g.run(0.05);
    assert.equal(g.ev("stunt"), null);
  });
});

describe("cacti", () => {
  const seen = (search, secs, seed = 4) => {
    const g = loadGame({ search, seed });
    const c = [];
    globalThis.__c = x => c.push(x);
    g.ev("spawnCactus = (f => x => { f(x); globalThis.__c(cacti[cacti.length - 1]); })(spawnCactus)");
    g.run(secs);
    delete globalThis.__c;
    return c;
  };
  it("grow in winter too, in their winter lights", () => {
    const c = seen("?season=3&seasonlen=99999&hour=12", 120);
    assert.ok(c.length >= 5, `only ${c.length} cacti in two minutes of winter`);
    assert.ok(c.every(x => x.deco === 3), "a winter cactus without lights");
  });
  it("wear each season's dress", () => {
    for (const [s, d] of [[0, 0], [1, 1], [2, 2]]) {
      const c = seen(`?season=${s}&seasonlen=99999&hour=12`, 100);
      assert.ok(c.length >= 3, `season ${s}: ${c.length} cacti`);
      assert.ok(c.every(x => x.deco === d), `season ${s}: wrong decoration`);
    }
  });
  it("with ?flair=0 are summer only, and bare", () => {
    for (const s of [0, 2, 3]) assert.equal(seen(`?flair=0&season=${s}&seasonlen=99999&hour=12`, 100).length, 0, `cacti in season ${s}`);
    const c = seen("?flair=0&season=1&seasonlen=99999&hour=12", 60);
    assert.ok(c.length >= 3 && c.every(x => x.deco === -1));
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

describe("flytrap", () => {
  // a game with a plant fully up in the next pipe, which is held right at the bird
  const withTrap = (search = "?season=0&hour=12", seed = 9) => {
    const g = loadGame({ search, seed });
    g.run(1);
    g.ev("score = 5; pipes = pipes.filter(p => p.x + PIPE_W > birdX - HW); const p = pipes[0]; p.trap = makeTrap(); Object.assign(p.trap, { on: true, up: 1, e: 1, open: 1 }); 0");
    return g;
  };
  const hold = (g, y) => g.run(0.6, () => g.ev(`pipes[0].x = birdX - PIPE_W / 2; cooldown = 9; if (!dead) { bird.y = ${y}; bird.vy = 0; } 0`));
  it("snaps at a bird in reach and kills it: the stats count a trap, and it restarts", () => {
    const g = withTrap();
    hold(g, "pipes[0].bot - 20");
    assert.equal(g.ev("dead"), true);
    assert.equal(g.ev("lastKind"), "trap");
    assert.equal(g.ev("stats.d.trap"), 1);
    assert.equal(g.ev("stats.runs"), 1);
    assert.equal(g.ev("pipes[0].trap.mode"), "hold");
    g.run(8);                                       // chewed, dragged down, the card, and the next round
    assert.equal(g.ev("dead"), false);
    assert.equal(g.ev("trapped"), null);
  });
  it("lets a bird well above it be", () => {
    const g = withTrap();
    hold(g, "pipes[0].bot - 80");
    assert.equal(g.ev("dead"), false);
    assert.equal(g.ev("pipes[0].trap.mode"), "idle");
  });
  it("drags the bird down into the pipe and out of sight", () => {
    const g = withTrap();
    hold(g, "pipes[0].bot - 20");
    g.run(2.5);
    assert.ok(g.ev("bird.y - HH > trapped.bot - 40") && g.ev("trapHy(trapped) > trapped.bot"), "still above the lip");
  });
  it("is not there with ?trap=0 or ?flair=0, over a long run, and is with ?trap=5", () => {
    const made = (search, secs) => {
      const g = loadGame({ search, seed: 11 });
      let n = 0; globalThis.__t = () => n++;
      g.ev("makeTrap = (f => (...a) => { globalThis.__t(); return f(...a); })(makeTrap)");
      g.run(secs);
      delete globalThis.__t;
      return n;
    };
    assert.equal(made("?trap=0", 400), 0);
    assert.equal(made("?flair=0&trap=5", 400), 0);
    assert.ok(made("?trap=5", 400) > 0, "none even at ?trap=5");
  });
  it("is not born in a quake", () => {
    const g = loadGame({ search: "?season=0&hour=12", seed: 6 });
    let inQuake = 0, before = 0; globalThis.__t = q => { if (q) inQuake++; else before++; };
    g.ev("TRAP.rate = 1000; makeTrap = (f => (...a) => { globalThis.__t(!!quake); return f(...a); })(makeTrap)");
    for (let i = 0; i < 60 && !(g.ev("score") >= 3 && !g.ev("dead")); i++) g.run(1);
    g.ev("startQuake()");
    g.run(25);
    delete globalThis.__t;
    assert.ok(before > 0, "the plant never came before the quake");
    assert.equal(inQuake, 0);
    assert.equal(g.ev("pipes.some(p => p.trap) && !!quake"), false);
  });
  it("makes the autopilot aim higher for an open one, and not for one that has had its snap", () => {
    const g = withTrap();
    assert.ok(g.ev("trapDodge(pipes[0])") > 0);
    g.ev("pipes[0].trap.done = true");
    assert.equal(g.ev("trapDodge(pipes[0])"), 0);
  });
  it("does not snap in a quake's free pass, and a crash during a snap is one death", () => {
    const g = withTrap();
    g.ev("startQuake()"); hold(g, "pipes[0].bot - 20");
    assert.equal(g.ev("stats.d.trap"), 0);
    const h = withTrap();
    h.ev("pipes[0].x = birdX - PIPE_W / 2; bird.y = pipes[0].bot - 20; bird.vy = 0; cooldown = 9; pipes[0].trap.mode = 'snap'; pipes[0].trap.mt = 1; bird.y = SKY - 2; 0");
    h.run(0.05);
    assert.equal(h.ev("stats.runs"), 1);
  });
  it("loads old saved stats with no trap count as zero, and the card draws", () => {
    const g = loadGame({ storage: memoryStorage({ "flappy-stats": JSON.stringify({ runs: 7, max: 30, d: { pipe: 5, hawk: 2 }, e: [] }) }) });
    assert.equal(g.ev("stats.d.trap"), 0);
    assert.equal(g.ev("stats.d.pipe"), 5);
    assert.equal(g.ev("DEATHS.some(d => d[0] === 'trap')"), true);
    g.ev("dead = true; offT = 1; drawStats()");
  });
});

describe("determinism", () => {
  it("plays the same game twice from the same seed", () => {
    const trace = () => { const g = loadGame({ seed: 77 }); const s = []; g.run(90, i => { if (i % 600 === 0) s.push(g.ev("[score, Math.round(bird.y), pipes.length, dead]").join(",")); }); return s.join("|"); };
    assert.equal(trace(), trace());
  });
});
