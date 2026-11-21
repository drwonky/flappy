// The balance limits every mode is held to. Games per mode: BALANCE_GAMES (default 60).
import assert from "node:assert/strict";
import { playGames } from "./balance.mjs";

export const GAMES = +process.env.BALANCE_GAMES || 60;

export function checkBalance(t, opts, limits = {}) {
  const r = playGames({ games: GAMES, ...opts });
  const n = r.games, share = k => (r.causes[k] || 0) / n;
  t.diagnostic(`${n} games, ${r.simMinutes.toFixed(0)} sim min: mean ${r.mean.toFixed(1)} p10 ${r.p10} p50 ${r.p50} p90 ${r.p90} | deaths ${JSON.stringify(r.causes)}`);
  const L = { mean: [70, 135], p50: [60, 140], p10: 15, pipe: 0.6, ground: 0.1, zap: 0.2, ufo: 0.2, hawk: 0.1, trap: 0.1, ...limits };
  assert.ok(r.mean >= L.mean[0] && r.mean <= L.mean[1], `average score ${r.mean.toFixed(1)} outside ${L.mean}`);
  assert.ok(r.p50 >= L.p50[0] && r.p50 <= L.p50[1], `median score ${r.p50} outside ${L.p50}`);
  assert.ok(r.p10 >= L.p10, `bottom 10% score ${r.p10} < ${L.p10}: too many early crashes`);
  assert.ok(share("pipe") + share("cap") >= L.pipe, `pipes caused only ${(100 * share("pipe")).toFixed(0)}% of deaths`);
  assert.ok(share("ground") + share("ceiling") <= L.ground, `the autopilot flew into the ground/ceiling ${r.causes.ground || 0}/${r.causes.ceiling || 0} times`);
  for (const k of ["zap", "ufo", "hawk", "trap"]) assert.ok(share(k) <= L[k], `${k} caused ${(100 * share(k)).toFixed(0)}% of deaths (limit ${100 * L[k]}%)`);
  return r;
}
