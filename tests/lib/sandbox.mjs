// Runs the game's <script> from flappy-seasons.html in Node, with no browser:
// a canvas that ignores every draw call, a seeded Math.random, an in-memory
// localStorage and a chosen URL query. The returned `ev(code)` evaluates code
// INSIDE the game's scope, so a test can read any variable, call any function
// or swap one out (`ev("startQuake = wrap(startQuake)")` - internal calls see
// the swap, because they go through the same binding).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const GAME = path.join(ROOT, "flappy-seasons.html");

let cached = null;
export function gameScript() {
  if (!cached) {
    const m = fs.readFileSync(GAME, "utf8").match(/<script>\n"use strict";([\s\S]*?)<\/script>/);
    if (!m) throw new Error("no <script> block with \"use strict\" in " + GAME);
    cached = m[1];
  }
  return cached;
}

// mulberry32: small, fast, and the same sequence everywhere
export function seeded(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

export function memoryStorage(init = {}) {
  const m = new Map(Object.entries(init));
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => { m.set(k, String(v)); },
    removeItem: k => { m.delete(k); },
    clear: () => m.clear(),
    get size() { return m.size; },
  };
}

/**
 * @param {object} o
 * @param {string} [o.search]   the URL query, e.g. "?noclock&env=1"
 * @param {number} [o.seed]     Math.random seed
 * @param {object} [o.storage]  a memoryStorage() to share between loads (persistence tests)
 * @param {number[]} [o.screen] [w, h] of the stage (TV modes size the world from it)
 */
export function loadGame({ search = "", seed = 1, storage = memoryStorage(), screen = [288, 512] } = {}) {
  const noop = () => {};
  const ctx = new Proxy({}, {
    get: (t, k) => (k in t ? t[k] : k === "measureText" ? () => ({ width: 40 }) : k === "getImageData" ? () => ({ data: new Uint8ClampedArray(4) }) : noop),
    set: (t, k, v) => ((t[k] = v), true),
  });
  const el = () => ({
    getContext: () => ctx, style: {}, width: 0, height: 0,
    getBoundingClientRect: () => ({ width: screen[0], height: screen[1] }),
    textContent: "", value: "", className: "",
    addEventListener: noop, setAttribute: noop, getAttribute: () => null,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  });
  const els = {};
  const document = {
    getElementById: id => (els[id] ||= el()), createElement: () => el(),
    body: el(), documentElement: el(), fonts: null, addEventListener: noop,
  };
  let clock = 0;
  const env = {
    Math: Object.assign(Object.create(Math), { random: seeded(seed) }),
    document, window: {}, localStorage: storage,
    location: { search, hash: "" }, URLSearchParams,
    devicePixelRatio: 1, innerWidth: screen[0], innerHeight: screen[1], screen: { width: screen[0], height: screen[1] },
    addEventListener: noop, requestAnimationFrame: () => 0, ResizeObserver: undefined,
    performance: { now: () => clock }, history: { replaceState: noop },
  };
  const body = gameScript() + "\nreturn (__code) => eval(__code);";
  const ev = new Function(...Object.keys(env), body)(...Object.values(env));
  const FIXED = ev("FIXED");
  const step = ev("step");
  return {
    ev,
    storage,
    /** advance the game by `secs` of 1/120 s steps */
    run(secs, each) {
      const n = Math.round(secs / FIXED);
      for (let i = 0; i < n; i++) { step(FIXED); clock += FIXED * 1000; if (each) each(i); }
    },
    FIXED,
  };
}
