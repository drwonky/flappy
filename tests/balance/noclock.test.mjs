// Autopilot balance with ?noclock (no day and night, so no saucers).
import { it } from "node:test";
import { checkBalance } from "../lib/balance-check.mjs";

it("?noclock: the autopilot scores in its usual range, and nothing is abducted", t => {
  checkBalance(t, { search: "?noclock" }, { ufo: 0 });
});
