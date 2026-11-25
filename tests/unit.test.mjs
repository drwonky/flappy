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

describe("July 4th fireworks", () => {
  // the shows of a run: [start, length] in game seconds, seen from the outside (the `fireworks` state)
  const shows = (search, secs, seed = 3) => {
    const g = loadGame({ search, seed }), out = []; let t0 = null;
    g.run(secs, i => { const on = !!g.ev("fireworks"); if (on && t0 === null) t0 = i / 120; if (!on && t0 !== null) { out.push([t0, i / 120 - t0]); t0 = null; } });
    return { g, out };
  };
  it("puts July 4th early in summer: day 185, the cycle starting at the March equinox", () => {
    const g = loadGame({ search: "?season=0" });
    near(g.ev("FW.at") * 4 * 28, 32.5, 0.05, "seconds into the year");
    assert.equal(g.ev("yearFrac(79)"), 0);
    near(g.ev("yearFrac(79 + 365 / 4)"), 0.25, 1e-9);
  });
  it("starts exactly one show a year, at the July 4th point, for about 10 s", () => {
    const { g, out } = shows("?season=0", 112);
    assert.equal(out.length, 1, JSON.stringify(out));
    near(out[0][0], g.ev("FW.at * 4 * SEASON.len"), 1 / 60, "start");
    assert.ok(out[0][1] >= 9.5 && out[0][1] <= 11, `lasts ${out[0][1]} s`);
    assert.equal(g.ev("fwShows"), 1);
  });
  it("starts two in two years, and none with ?flair=0", () => {
    assert.equal(shows("?season=0", 224).out.length, 2);
    const { g, out } = shows("?season=0&flair=0", 112);
    assert.equal(out.length, 0); assert.equal(g.ev("fwShows"), 0);
    assert.equal(shows("?season=0&flair=0&fireworks", 5).out.length, 0);
  });
  it("is not fooled by the wrap, a big step or a change of pace (DISCO)", () => {
    const g = loadGame({ search: "?season=3" });
    g.ev("seasonT = 4 * SEASON.len - 0.001; stepFireworks(1, 0)");   // through the wrap, past nothing
    g.ev("stepSeason(0.01); stepFireworks(0.01, 0)");
    assert.equal(g.ev("fwShows"), 0);
    g.ev("seasonT = FW.at * 4 * SEASON.len - 0.5; stepFireworks(0, 0); stepSeason(2); stepFireworks(2, 0)");   // one step right over it
    assert.equal(g.ev("fwShows"), 1);
    g.ev("fireworks = null; stepSeason(1); stepFireworks(1, 0)");
    assert.equal(g.ev("fwShows"), 1);
    g.ev("startDisco(); stepFireworks(0.01, 0)");                  // the same point in the year at another pace: nothing new
    assert.equal(g.ev("fwShows"), 1);
  });
  it("is rained out: a storm at July 4th puts the show off until it clears (still summer), else skips it", () => {
    const g = loadGame({ search: "?season=1&seasonlen=60" });   // a long summer, with the storm window inside it
    g.ev("TSTORM.dur = 12");
    // a storm over the trigger, clearing well before summer ends
    g.ev("const [s0, d] = stormWindow(); globalThis.__w = [s0, d]; seasonT = FW.at * 4 * SEASON.len - 0.01; fwPrev = seasonT / (4 * SEASON.len); ts.I = 0.8; ts.on = true; stepSeason(0.02); stepFireworks(0.02, 0)");
    assert.equal(g.ev("fwShows"), 0); assert.equal(g.ev("fwWait"), true);
    g.ev("ts.I = 0.5; stepFireworks(1, 0)"); assert.equal(g.ev("fwShows"), 0, "still raining");
    g.ev("ts.I = 0.1; seasonT = Math.min(seasonT, stormWindow()[0] - 1); stepFireworks(1, 0)");
    assert.equal(g.ev("fwShows"), 1); assert.equal(g.ev("fwWait"), false);
    // a storm that outlasts the summer: no show this year
    const h = loadGame({ search: "?season=1" });
    h.ev("seasonT = FW.at * 4 * SEASON.len - 0.01; fwPrev = seasonT / (4 * SEASON.len); ts.I = 0.8; stepSeason(0.02); stepFireworks(0.02, 0)");
    assert.equal(h.ev("fwWait"), true);
    h.ev("seasonT = SEASON.len * 2 + 0.5; stepSeason(0.01); ts.I = 0.8; stepFireworks(0.01, 0)");   // autumn now, the storm still on
    assert.equal(h.ev("fwWait"), false); assert.equal(h.ev("fwShows"), 0);
    h.ev("ts.I = 0; stepFireworks(1, 0)"); assert.equal(h.ev("fwShows"), 0);
    // ?fireworks goes ahead in any weather
    const k = loadGame({ search: "?season=1&fireworks" });
    k.ev("ts.I = 0.9; ts.on = true; stepFireworks(1.1, 0)"); assert.equal(k.ev("fwShows"), 1);
  });
  it("starts one with ?fireworks, a second in", () => {
    const { g, out } = shows("?season=0&fireworks", 20);
    assert.equal(out.length, 1);
    near(out[0][0], 1, 0.02, "start");
    near(out[0][1], 10, 0.5, "length");
    assert.ok(g.ev("fwN") === 0, "sparks left");
  });
  it("launches singles, a middle and a finale of 9-12, stays under the spark cap and draws", () => {
    const g = loadGame({ search: "?season=0&fireworks" });
    let peak = 0, bursts = [];
    g.ev("fwBurst = (f => s => { globalThis.__b(s.t); return f(s); })(fwBurst)");
    globalThis.__b = () => bursts.push(g.ev("fireworks ? fireworks.t : 10"));
    g.run(12, i => { peak = Math.max(peak, g.ev("fwN")); if (i % 8 === 0) g.ev("drawFireworks()"); });
    globalThis.__b = () => {};
    assert.ok(peak > 100 && peak <= 600, `peak ${peak}`);
    assert.ok(bursts.length >= 15 && bursts.length <= 40, `${bursts.length} shells`);
    const fin = bursts.filter(t => t > 8.3);
    assert.ok(fin.length >= 8, `finale of ${fin.length}`);
    assert.ok(bursts.filter(t => t < 3.5).length <= 4, "the opening is a few single shells");
    for (const k of [0, 1, 2, 3, 4, 5, 6]) {                      // every kind of burst draws and dies away
      g.ev(`fwN = 0; fwBurst({ x1: 100, y1: 150, kind: ${k}, c0: 0, c1: 2, fin: false }); fwBurst({ x1: 100, y1: 150, kind: ${k}, c0: 3, c1: 3, fin: true })`);
      assert.ok(g.ev("fwN") > 3);
      g.run(3, i => { if (i % 24 === 0) g.ev("drawFireworks()"); });
      assert.equal(g.ev("fwN"), 0, `kind ${k}`);
    }
  });
  it("never changes the game: the same seed plays the same with and without a show", () => {
    const play = search => {
      const g = loadGame({ search, seed: 21 }), s = [];
      g.run(28, i => { if (i % 240 === 0) s.push(g.ev("[score, bird.y, stats.runs, dead, pipes.length]").join(",")); });
      return { s: s.join("|"), shows: g.ev("fwShows") };
    };
    const a = play("?season=0"), b = play("?season=0&fireworks");
    assert.equal(a.shows, 0); assert.equal(b.shows, 1);
    assert.equal(a.s, b.s);
  });
  it("keeps the game's Math.random out of it", () => {
    const g = loadGame({ search: "?season=0&fireworks" }); let n = 0;
    g.ev("Math.random = (f => () => { globalThis.__r++; return f(); })(Math.random)"); globalThis.__r = 0;
    const base = (() => { const h = loadGame({ search: "?season=0" }); let c = 0; h.ev("Math.random = (f => () => { globalThis.__r2++; return f(); })(Math.random)"); globalThis.__r2 = 0; h.run(12); return globalThis.__r2; })();
    g.run(12); n = globalThis.__r; delete globalThis.__r; delete globalThis.__r2;
    assert.equal(n, base);
  });
});

describe("Christmas and Easter", () => {
  // the events of a run, from the outside: [start, length] of the span `ex` is truthy, in game seconds
  const spans = (search, secs, ex, seed = 3) => {
    const g = loadGame({ search, seed }), out = []; let t0 = null;
    g.run(secs, i => { const on = !!g.ev(ex); if (on && t0 === null) t0 = i / 120; if (!on && t0 !== null) { out.push([t0, i / 120 - t0]); t0 = null; } });
    return { g, out };
  };
  const patchGradients = g => g.ev("ctx.createLinearGradient = ctx.createRadialGradient = () => ({ addColorStop() {} })");   // (the stub canvas has none: draw() needs them)
  it("finds Easter Sunday for known years (Anonymous Gregorian computus)", () => {
    const g = loadGame();
    for (const [y, m, d] of [[2024, 3, 31], [2025, 4, 20], [2026, 4, 5], [2027, 3, 28], [2000, 4, 23], [2019, 4, 21], [2038, 4, 25], [1818, 3, 22]])
      assert.deepEqual(g.ev(`easterSunday(${y})`), [m, d], `Easter ${y}`);
  });
  it("puts Christmas on day 359 and Good Friday two days before Easter, on the year's clock", () => {
    const g = loadGame({ search: "?easteryear=2026" });
    near(g.ev("XM.at * 4 * SEASON.len"), (359 - 79) / 365 * 112, 1e-6, "Christmas, s into the year");
    near(g.ev("EA.at * 4 * SEASON.len"), (93 - 79) / 365 * 112, 1e-6, "Good Friday 2026 is 3 April, day 93");
    near(loadGame({ search: "?easteryear=2024" }).ev("EA.at * 4 * SEASON.len"), (89 - 79) / 365 * 112, 1e-6, "Good Friday 2024 is 29 March");
  });
  it("has the dark hours from 18:00 to 07:00, and none with ?noclock", () => {
    const g = loadGame();
    for (const [h, d] of [[17.9, false], [18, true], [23.5, true], [0, true], [6.9, true], [7, false], [12, false]]) assert.equal(g.ev(`hour = ${h}; hdDark()`), d, "hour " + h);
    assert.equal(loadGame({ search: "?noclock" }).ev("hour = 22; hdDark()"), false);
  });
  it("starts exactly one Christmas a year at Dec 25 in the dark hours, for about 12 s", () => {
    const { g, out } = spans("?season=3&hour=22", 112, "xmas");
    assert.equal(out.length, 1, JSON.stringify(out));
    near(out[0][0], g.ev("XM.at * 4 * SEASON.len - 3 * SEASON.len"), 1 / 60, "start (about 1.9 s into winter)");
    near(out[0][0], 1.9, 0.1, "about 1.9 s into winter");
    near(out[0][1], 12, 0.1, "length");
    assert.equal(g.ev("xmasN"), 1);
    assert.equal(spans("?season=3&hour=22&daylen=112", 224, "xmas").out.length, 2, "two in two years (a day as long as the year: the same hour)");
  });
  it("has no Christmas by day, with ?noclock or with ?flair=0, and decides by the hour it passes Dec 25", () => {
    assert.equal(spans("?season=3&hour=12", 112, "xmas").out.length, 0);
    assert.equal(spans("?season=3&hour=22&noclock", 112, "xmas").out.length, 0);
    const a = spans("?season=3&hour=22&flair=0", 112, "xmas"); assert.equal(a.out.length, 0); assert.equal(a.g.ev("xmasN"), 0);
    assert.equal(spans("?season=3&hour=22&santa&flair=0", 5, "xmas").out.length, 0);
    const g = loadGame({ search: "?season=3&hour=17.9" });                   // the crossing itself decides: 17.9 no, 18 yes
    g.ev("seasonT = XM.at * 4 * SEASON.len - 0.01; hdPrev = seasonT / (4 * SEASON.len); stepSeason(0.02); stepHolidays(0.02, 0)");
    assert.equal(g.ev("xmasN"), 0);
    g.ev("hour = 18; seasonT = XM.at * 4 * SEASON.len - 0.01; hdPrev = seasonT / (4 * SEASON.len); stepSeason(0.02); stepHolidays(0.02, 0)");
    assert.equal(g.ev("xmasN"), 1);
  });
  it("is not fooled by the wrap, a big step or a change of pace (DISCO)", () => {
    const g = loadGame({ search: "?season=3&hour=22" });
    g.ev("seasonT = 4 * SEASON.len - 0.001; hdPrev = seasonT / (4 * SEASON.len); stepSeason(0.01); stepHolidays(0.01, 0)");   // through the wrap, past nothing
    assert.equal(g.ev("xmasN"), 0); assert.equal(g.ev("easterN"), 0);
    g.ev("seasonT = XM.at * 4 * SEASON.len - 0.5; hdPrev = seasonT / (4 * SEASON.len); stepSeason(2); stepHolidays(2, 0)");   // one step right over it
    assert.equal(g.ev("xmasN"), 1);
    g.ev("xmas = null; stepSeason(1); stepHolidays(1, 0)");
    assert.equal(g.ev("xmasN"), 1);
    g.ev("startDisco(); stepHolidays(0.01, 0)");                              // the same point in the year at another pace: nothing new
    assert.equal(g.ev("xmasN"), 1);
  });
  it("swells the star, runs Santa across in 8-10 s, and dims it again", () => {
    const g = loadGame({ search: "?santa&hour=22" }), k = [], u = [];
    g.run(14, i => { if (i % 6 === 0) { k.push(g.ev("xmasStarK()")); u.push(g.ev("santaU()")); g.ev("drawSanta(); drawBethlehem(); drawSparkles()"); } });
    assert.ok(k.every(v => v >= 0 && v <= 1));
    const peak = Math.max(...k);
    assert.equal(peak, 1); assert.equal(k[k.length - 1], 0, "back to normal");
    const first = k.findIndex(v => v > 0), full = k.findIndex(v => v >= 1);
    near((full - first) * 0.05, 1.5, 0.15, "swell");
    const last = k.length - 1 - [...k].reverse().findIndex(v => v >= 1), gone = k.length - 1 - [...k].reverse().findIndex(v => v > 0);
    near((gone - last) * 0.05, 2, 0.15, "dim");
    const on = u.map((v, i) => [v, i]).filter(([v]) => v >= 0 && v <= 1);
    near((on[on.length - 1][1] - on[0][1]) * 0.05, 9, 0.2, "the crossing");
    assert.equal(g.ev("xmas"), null, "over");
  });
  it("starts one Christmas with ?santa a second in, by day or night", () => {
    for (const h of [12, 22]) { const { out } = spans("?season=0&santa&hour=" + h, 20, "xmas"); assert.equal(out.length, 1); near(out[0][0], 1, 0.02, "start"); near(out[0][1], 12, 0.1, "length"); }
  });
  it("starts one Easter a year at Good Friday, lasting 20 s, through its phases in order (the blood moon at night)", () => {
    const seq = (search, secs) => {
      const g = loadGame({ search, seed: 3 }), s = []; let t0 = null, t1 = null;
      g.run(secs, i => { const p = g.ev("easterPhase()"); if (p && s[s.length - 1] !== p) s.push(p); if (p && t0 === null) t0 = i / 120; if (!p && t0 !== null && t1 === null) t1 = i / 120; });
      return { g, s, t0, t1 };
    };
    const n = seq("?season=0&hour=22&easteryear=2026", 112);
    assert.deepEqual(n.s, ["friday", "moon", "sunrise", "fade"]);
    near(n.t0, (93 - 79) / 365 * 112, 1 / 60, "start"); near(n.t1 - n.t0, 20, 0.5, "length");
    assert.equal(n.g.ev("easterN"), 1);
    const d = seq("?season=0&hour=12&easteryear=2026", 112);                   // by day there is no moon: the dark simply lifts into dawn
    assert.deepEqual(d.s, ["friday", "dawn", "sunrise", "fade"]); near(d.t1 - d.t0, 20, 0.5, "length");
    assert.equal(seq("?season=0&hour=22&easteryear=2026", 224).g.ev("easterN"), 2);
    assert.equal(seq("?season=0&hour=22&easteryear=2026&flair=0", 112).g.ev("easterN"), 0);
  });
  it("starts one Easter with ?easter a second in; the darkness, eclipse and gold follow the phases", () => {
    const g = loadGame({ search: "?season=0&hour=22&holidays=0&easter" }); const at = {};
    g.run(22, i => { const t = g.ev("easter ? easter.t : -1"); for (const T of [0.5, 1.4, 4, 6, 8, 10.5, 13, 16, 18.5]) if (t >= T && !(T in at)) at[T] = g.ev("[hdDk, hdEcl, hdGold, hdTrem]"); });
    assert.ok(at[0.5][0] < 0.3 && at[1.4][0] > 0.95, "darkens over 1.5 s");
    assert.ok(at[4][0] > 0.9 && at[6][0] < 0.01, "lifts at the end of the phase");
    assert.ok(at[8][1] > 0.95 && at[6][1] > 0 && at[10.5][1] < 0.3, "the eclipse comes and clears");
    assert.ok(at[13][2] > 0.9 && at[13][1] === 0 && at[18.5][2] < at[16][2], "golden, then fades");
    assert.ok(at[13][3] > 0 && at[16][3] === 0 && at[4][3] === 0, "the tremor is only in 12-14.5 s");
    const by = loadGame({ search: "?season=0&hour=12&holidays=0&easter" }); let ecl = 0;
    by.run(16, () => { ecl = Math.max(ecl, by.ev("hdEcl")); }); assert.equal(ecl, 0, "no eclipse without a moon");
  });
  it("shakes a little in the tremor, but is no quake: no startQuake, the pipes as they were, no Math.random", () => {
    const play = search => {
      const g = loadGame({ search, seed: 8 }); let q = 0, trem = 0; patchGradients(g); g.ev("startQuake = (f => (...a) => { globalThis.__q++; return f(...a); })(startQuake)"); globalThis.__q = 0;
      g.ev("Math.random = (f => () => { globalThis.__r++; return f(); })(Math.random)"); globalThis.__r = 0;
      g.run(24, i => { trem = Math.max(trem, g.ev("easterShake()")); if (i % 8 === 0) g.ev("draw()"); });
      return { q: globalThis.__q, r: globalThis.__r, trem, pipes: g.ev("JSON.stringify(pipes.map(p => [Math.round(p.x), Math.round(p.top), Math.round(p.bot)]))"), quake: g.ev("quake"), fallen: g.ev("fallen.length") };
    };
    const a = play("?season=0&hour=22&quake=0&holidays=0"), b = play("?season=0&hour=22&quake=0&holidays=0&easter");
    assert.equal(b.q, 0); assert.equal(b.quake, null); assert.equal(b.fallen, 0);
    assert.ok(b.trem > 0.5 && b.trem <= 2, `tremor ${b.trem} px`); assert.equal(a.trem, 0);
    assert.equal(b.pipes, a.pipes, "the pipes are the same");
    assert.equal(b.r, a.r, "the game's Math.random is not touched");
    delete globalThis.__q; delete globalThis.__r;
  });
  it("lays eggs at random gaps of 1.5-3 s, under the cap, that drop, bounce, roll and sit on the ground", () => {
    const g = loadGame({ search: "?season=0&hour=12&holidays=0&easter", seed: 4 }), times = [];
    g.ev("spawnEgg = (f => () => { globalThis.__e(); return f(); })(spawnEgg)");
    globalThis.__e = () => times.push(g.ev("easter.t"));
    let peak = 0, bounced = 0, sat = 0, first = null;
    g.run(23, i => {
      peak = Math.max(peak, g.ev("eggs.filter(e => e.on).length"));
      for (const e of g.ev("eggs.filter(e => e.on).map(e => [e.nb, e.rest, e.y, e.gy])")) { if (e[0] >= 1) bounced++; if (e[1]) { sat++; assert.ok(Math.abs(e[2] - e[3]) < 1e-6, "sits on the ground"); } }
    });
    delete globalThis.__e;
    assert.ok(times.length >= 6 && times.length <= 14, `${times.length} eggs in 20 s`);
    for (let i = 1; i < times.length; i++) { const d = times[i] - times[i - 1]; assert.ok(d >= 1.5 - 0.02 && d <= 3 + 0.02, `gap ${d}`); }
    assert.ok(times[0] >= 1.5 - 0.02 && times[0] <= 3 + 0.02, "the first gap");
    assert.ok(times[times.length - 1] <= 20, "none after the event");
    assert.ok(peak <= 30 && peak >= 1, `peak ${peak}`); assert.ok(bounced > 0 && sat > 0, "they bounce and then sit");
    const h = loadGame({ search: "?season=0&hour=12" });                      // the cap, hammered
    for (let i = 0; i < 100; i++) h.ev("spawnEgg()");
    assert.equal(h.ev("eggs.filter(e => e.on).length"), 30);
    h.run(0.1); assert.ok(h.ev("eggs.filter(e => e.on).length") <= 30);
  });
  it("draws every part of both events without error, in the dark, by day and with ?noclock", () => {
    for (const q of ["?santa&easter&hour=22", "?santa&easter&hour=12&season=3", "?santa&easter&noclock", "?santa&easter&hour=6.5&tvs"]) {
      const g = loadGame({ search: q, seed: 5, screen: q.includes("tvs") ? [1920, 1080] : [288, 512] }); patchGradients(g);
      g.run(24, i => { if (i % 6 === 0) g.ev("draw()"); });
      assert.equal(g.ev("xmasN"), 1); assert.equal(g.ev("easterN"), 1);
    }
  });
  it("never changes the game: the same seed plays the same with and without ?santa and ?easter", () => {
    const play = search => {
      const g = loadGame({ search, seed: 21 }), s = [];
      g.run(26, i => { if (i % 240 === 0) s.push(g.ev("[score, bird.y, stats.runs, dead, pipes.length]").join(",")); });
      return { s: s.join("|"), x: g.ev("xmasN"), e: g.ev("easterN") };
    };
    const a = play("?season=0&hour=22&holidays=0"), b = play("?season=0&hour=22&holidays=0&santa&easter");
    assert.equal(a.x + a.e, 0); assert.equal(b.x, 1); assert.equal(b.e, 1);
    assert.equal(a.s, b.s);
  });
  it("turns both off with ?flair=0", () => {
    const g = loadGame({ search: "?season=0&hour=22&santa&easter&flair=0" });
    g.run(25, i => { if (i % 12 === 0) g.ev("draw()"); });
    assert.equal(g.ev("xmasN"), 0); assert.equal(g.ev("easterN"), 0); assert.equal(g.ev("eggN"), 0);
  });
});

describe("TV sizing", () => {
  // the world's height is picked so a common screen is a whole number of px per game px: every game px
  // is then a whole block of screen px, and the scanline styles have nothing fractional to beat against
  it("scales by a whole number on 1080p, 1440p and 4K, and keeps 512 where nothing fits", () => {
    for (const [screen, w, h, k] of [[[3840, 2160], 960, 540, 4], [[1920, 1080], 960, 540, 2], [[2560, 1440], 852, 480, 3],
                                     [[3440, 1440], 1146, 480, 3], [[1920, 1200], 960, 600, 2], [[1280, 720], 910, 512, null]]) {
      const g = loadGame({ search: "?tvs", screen });
      assert.deepEqual([g.ev("W"), g.ev("H")], [w, h], screen.join("x"));
      if (k) assert.equal(g.ev("DS"), k, `${screen.join("x")}: ${g.ev("DS")} px a game px`);
    }
  });
  it("keeps the pipes' gaps in the usual band, centred in a taller sky", () => {
    const g = loadGame({ search: "?tvs", screen: [1920, 1080], seed: 3 });
    assert.equal(g.ev("PLAY_Y"), 14);
    let lo = 1e9, hi = -1e9;
    for (let i = 0; i < 400; i++) { g.ev("spawn(); 0"); const t = g.ev("pipes[pipes.length - 1].top"), b = g.ev("pipes[pipes.length - 1].bot"); lo = Math.min(lo, t); hi = Math.max(hi, b); }
    assert.ok(lo >= 14 + 30 - 1e-9 && hi <= 14 + 512 - 113 - 30 + 1e-9, `gaps from ${lo} to ${hi}`);
  });
});

describe("blimp disaster", () => {
  // lightning hits the blimp: it burns, falls, lands on the far hills' ground line and burns there for BLIMPFIRE.burn s
  const strikeBlimp = (search = "?season=0", seed = 4) => {
    const g = loadGame({ search, seed });
    g.ev("BLIMPFIRE.par = 0; flNext.blimp = 1e9; blimp = makeBlimp(); blimp.x = W / 2; blimp.y = 60; blimp.dir = 1; blimp.v = 0; ts.I = 1; igniteBlimp(blimp); 0");
    return g;
  };
  it("burns, falls, lands on the ground line, and the wreck burns for 20 s and is gone", () => {
    const g = strikeBlimp();
    assert.ok(g.ev("blimp.hit"), "the real blimp flies on, unseen");
    const seen = [], at = {}; let maxN = 0;
    g.run(60, i => {
      if (i % 6) return;
      const ph = g.ev("blimpFire ? blimpFire.phase : null");
      maxN = Math.max(maxN, g.ev("bfN"));
      if (ph !== seen[seen.length - 1]) { seen.push(ph); at[ph] = i / 120; if (ph === "wreck") at.y = g.ev("[blimpFire.y, blimpFire.s0, bfGround(), SKY - 26]"); }
    });
    assert.deepEqual(seen, ["burning", "falling", "wreck", null]);
    near(at.null - at.wreck, 20, 0.5, "the wreck's burn");
    assert.ok(at.falling > 2 && at.wreck > at.falling + 1, `falls from ${at.falling} to ${at.wreck}`);
    const [y, s0, gr, hills] = at.y;
    near(y + 9 + s0 * 22, gr, 0.5, "lowest point on the ground line");
    assert.ok(gr >= hills - 4 && gr <= hills + 4, "the far hills' ground line");
    assert.ok(maxN > 20 && maxN <= 500, `particles ${maxN}`);
  });
  it("tilts nose-up as the tail drops, and keeps its parallax: gone off screen early if the world scrolls it away", () => {
    const g = strikeBlimp();
    g.run(3.5);
    assert.ok(g.ev("blimpFire.slope") > 0.3);
    const g2 = loadGame({ search: "?season=0", seed: 4 });
    g2.ev("flNext.blimp = 1e9; blimp = makeBlimp(); blimp.x = W / 2; blimp.y = 60; ts.I = 1; igniteBlimp(blimp); 0");
    g2.run(60);
    assert.equal(g2.ev("blimpFire"), null);
  });
  it("is struck by a storm's lightning, sometimes (BLIMPFIRE.p), once per blimp", () => {
    const g = loadGame({ search: "?season=0", seed: 6 });
    g.ev("flNext.blimp = 1e9; blimp = makeBlimp(); blimp.x = W / 2; blimp.fate = true; ts.I = 1; blimpStrikeCheck(); 0");
    assert.equal(g.ev("blimpFire && blimpFire.phase"), "burning");
    const h = loadGame({ search: "?season=0", seed: 6 });
    h.ev("flNext.blimp = 1e9; blimp = makeBlimp(); blimp.x = W / 2; blimp.fate = false; ts.I = 1; blimpStrikeCheck(); 0");
    assert.equal(h.ev("blimpFire"), null);
    h.ev("ts.I = 0.2; blimp.fate = undefined; blimpStrikeCheck(); 0");   // not in a calm sky
    assert.equal(h.ev("blimpFire"), null);
  });
  it("starts one with ?blimpfire, and none with ?flair=0", () => {
    const g = loadGame({ search: "?season=0&blimpfire" });
    g.run(0.5); assert.equal(g.ev("blimpFire"), null);
    g.run(1); assert.equal(g.ev("blimpFire && blimpFire.phase"), "fly");
    g.run(2); assert.equal(g.ev("blimpFire && blimpFire.phase"), "burning");
    const k = loadGame({ search: "?season=0&blimpfire&flair=0" });
    k.run(8); assert.equal(k.ev("blimpFire"), null); assert.equal(k.ev("bfFires"), 0);
    assert.equal(loadGame({ search: "?season=0" }).ev("blimpFire"), null);
  });
  it("holds the particle cap", () => {
    const g = loadGame({ search: "?season=0" });
    g.ev("for (let i = 0; i < 3000; i++) bfPart(i % 4, 50, 50, 0, 0, 5, 2, 0, 0); 0");
    assert.equal(g.ev("bfN"), 500);
    g.run(2); assert.ok(g.ev("bfN") <= 500);
  });
  it("never changes the game: the same seed plays the same with and without a fire, and Math.random is untouched", () => {
    const play = search => {
      const g = loadGame({ search, seed: 21 }), s = [];
      g.ev("Math.random = (f => () => { globalThis.__rb = (globalThis.__rb || 0) + 1; return f(); })(Math.random)"); globalThis.__rb = 0;
      g.run(28, i => { if (i % 240 === 0) s.push(g.ev("[score, bird.y, stats.runs, dead, pipes.length]").join(",")); });
      const n = globalThis.__rb; delete globalThis.__rb;
      return { s: s.join("|"), fires: g.ev("bfFires"), n, phase: g.ev("blimpFire && blimpFire.phase") };
    };
    const a = play("?season=0"), b = play("?season=0&blimpfire");
    assert.equal(a.fires, 0); assert.equal(b.fires, 1);
    assert.equal(a.s, b.s);
    assert.equal(a.n, b.n);
  });
});

describe("BURNSAFE (OLED burn-in care)", () => {
  const TVSCREEN = [1920, 1080];
  it("is on with ?tv and ?tvs, off on the phone layout, and follows ?burnsafe", () => {
    assert.equal(loadGame({ search: "?tvs", screen: TVSCREEN }).ev("BURNSAFE"), true);
    assert.equal(loadGame({ search: "?tv", screen: TVSCREEN }).ev("BURNSAFE"), true);
    assert.equal(loadGame({}).ev("BURNSAFE"), false);
    assert.equal(loadGame({ search: "?tvs&burnsafe=0", screen: TVSCREEN }).ev("BURNSAFE"), false);
    assert.equal(loadGame({ search: "?burnsafe" }).ev("BURNSAFE"), true);
    assert.equal(loadGame({ search: "?burnsafe=1&noclock" }).ev("BURNSAFE"), true);
    assert.equal(loadGame({ search: "?burnsafe=0" }).ev("BURNSAFE"), false);
  });
  it("orbits within +-A, 1 px at a time, from 0,0, and visits every offset in the square", () => {
    const g = loadGame({ search: "?tvs", screen: TVSCREEN });
    const A = g.ev("orbitA()"), step = g.ev("ORBIT.step"), n = 2 * A + 1, P = 2 * (n * n - 1);
    assert.equal(A, 3);
    assert.deepEqual(g.ev("orbitXY()"), [0, 0]);
    const seen = new Set(); let prev = [0, 0];
    for (let i = 0; i <= P; i++) {   // (a full there-and-back: the bound on the time to see them all is P steps, 3840 s)
      g.ev(`orbitClock = ${i * step + step / 2}`);
      const [x, y] = g.ev("orbitXY()");
      assert.ok(Math.abs(x) <= A && Math.abs(y) <= A, `${x},${y} out of range`);
      assert.ok(Math.abs(x - prev[0]) <= 1 && Math.abs(y - prev[1]) <= 1, `jumped from ${prev} to ${x},${y}`);
      seen.add(x + "," + y); prev = [x, y];
    }
    assert.equal(seen.size, n * n);
    assert.ok(P * step <= 4000);
  });
  it("moves one step every ORBIT.step s of game time", () => {
    const g = loadGame({ search: "?tvs", screen: TVSCREEN });
    g.run(39); assert.deepEqual(g.ev("orbitXY()"), [0, 0]);
    g.run(2); assert.notDeepEqual(g.ev("orbitXY()"), [0, 0]);
  });
  it("keeps still with ?burnsafe=0", () => {
    const g = loadGame({ search: "?tvs&burnsafe=0", screen: TVSCREEN });
    for (const t of [0, 41, 500, 5000]) { g.ev(`orbitClock = hudClock = ${t}`); assert.deepEqual(g.ev("orbitXY()"), [0, 0]); assert.deepEqual(g.ev("hudXY()"), [0, 0]); }
  });
  it("drifts the HUD within +-3 game px, 1 px at a time", () => {
    const g = loadGame({ search: "?tvs", screen: TVSCREEN });
    let prev = [0, 0];
    for (let t = 0; t < 90 * 120; t += 45) {
      g.ev(`hudClock = ${t}`); const [x, y] = g.ev("hudXY()");
      assert.ok(Math.abs(x) <= 3 && Math.abs(y) <= 3);
      assert.ok(Math.abs(x - prev[0]) <= 1 && Math.abs(y - prev[1]) <= 1);
      prev = [x, y];
    }
  });
  it("never changes the game: the same seed plays the same with it on and off", () => {
    const play = search => {
      const g = loadGame({ search, seed: 21, screen: TVSCREEN }), s = [];
      g.run(150, i => { if (i % 1200 === 0) s.push(g.ev("[score, bird.y, pipes.length, stats.runs]").join(",")); });
      return s.join("|") + "#" + g.ev("[score, bird.y, stats.runs]").join(",");
    };
    assert.equal(play("?tvs&burnsafe=0"), play("?tvs&burnsafe=1"));
  });
});
