// Autopilot balance in the TV mode (?tvs: a 16:9 world, the bird held in the middle).
import { it } from "node:test";
import assert from "node:assert/strict";
import { checkBalance } from "../lib/balance-check.mjs";
import { loadGame } from "../lib/sandbox.mjs";

it("?tvs: the world is 16:9 wide", () => {
  assert.equal(loadGame({ search: "?tvs", screen: [1920, 1080] }).ev("W"), 910);
});
it("?tvs: the autopilot scores in its usual range and dies to the usual things", t => {
  checkBalance(t, { search: "?tvs", screen: [1920, 1080] });
});
