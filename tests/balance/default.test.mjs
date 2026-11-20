// Autopilot balance with the default settings: day and night, ENV x1.
import { it } from "node:test";
import { checkBalance } from "../lib/balance-check.mjs";

it("default settings: the autopilot scores in its usual range and dies to the usual things", t => {
  checkBalance(t, { search: "" });
});
