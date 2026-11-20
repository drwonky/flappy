// Plays the autopilot through `games` seeded games and sums up how they went.
// One world per seed, several games in it (the seasons, ground cover and clock
// run on through the crashes, as they do on screen), seeds rotating the season.
import { loadGame } from "./sandbox.mjs";

export function playGames({ search = "", games = 60, perWorld = 8, screen, firstSeed = 100, cap = 3000 } = {}) {
  const scores = [], causes = {}, seasons = [0, 0, 0, 0];
  let simSecs = 0, seed = firstSeed;
  while (scores.length < games) {
    const g = loadGame({ search: search + (search ? "&" : "?") + "season=" + (seed % 4), seed: seed++, screen });
    const step = g.ev("step"), FIXED = g.FIXED, isDead = g.ev("() => dead"), sc = g.ev("() => score"), why = g.ev("() => lastKind"), season = g.ev("() => seasonI");
    let inWorld = 0, was = false;
    while (inWorld < perWorld && scores.length < games) {
      step(FIXED); simSecs += FIXED;
      const d = isDead();
      if (d && !was) { scores.push(sc()); causes[why()] = (causes[why()] || 0) + 1; seasons[season()]++; inWorld++; }
      else if (!d && sc() >= cap) { scores.push(sc()); causes.cap = (causes.cap || 0) + 1; inWorld++; g.ev("reset()"); }
      was = d;
    }
  }
  const sorted = scores.slice().sort((a, b) => a - b);
  const trimmed = sorted.slice(1, -1);
  const mean = trimmed.reduce((a, b) => a + b, 0) / trimmed.length;
  const q = p => sorted[Math.floor(p * (sorted.length - 1))];
  return { games: scores.length, mean, p10: q(0.1), p50: q(0.5), p90: q(0.9), causes, seasons, simMinutes: simSecs / 60 };
}
