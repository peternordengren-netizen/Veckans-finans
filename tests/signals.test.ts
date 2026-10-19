// Tester för signaltabellens visningstexter och sortering. Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { compareValues, ratio, sek, shortChange, signedPct } from "../src/lib/signals.ts";

const MINUS = "−";

test("procent med tecken och tomt värde", () => {
  assert.equal(signedPct(9.04), "+9,0 %");
  assert.equal(signedPct(-5.06), `${MINUS}5,1 %`);
  assert.equal(signedPct(0), "0,0 %");
  assert.equal(signedPct(null), "–");
});

test("omsättning och kronor", () => {
  assert.equal(ratio(3), "3,0×");
  assert.equal(ratio(null), "–");
  assert.equal(sek(229_514_008), "+229,5 mn kr");
  assert.equal(sek(252_815), "+252 815 kr");
  assert.equal(sek(-1_200_000), `${MINUS}1,2 mn kr`);
  assert.equal(sek(0), "0 kr");
});

test("blankning: positioner går före aggregatet", () => {
  assert.equal(shortChange({ short_positions_pp: 0.3, short_aggregate_pp: 0.6 }), 0.3);
  assert.equal(shortChange({ short_positions_pp: null, short_aggregate_pp: 0.6 }), 0.6);
  assert.equal(shortChange({ short_positions_pp: null, short_aggregate_pp: null }), null);
});

test("sortering: saknade värden sist i båda riktningarna, svensk textordning", () => {
  const nums = [3, null, -1, 10];
  assert.deepEqual([...nums].sort((a, b) => compareValues(a, b, true)), [-1, 3, 10, null]);
  assert.deepEqual([...nums].sort((a, b) => compareValues(a, b, false)), [10, 3, -1, null]);
  const names = ["Ödla", "Alfa", "Ärla", "Zeta"];
  assert.deepEqual([...names].sort((a, b) => compareValues(a, b, true)), ["Alfa", "Zeta", "Ärla", "Ödla"]);
});
