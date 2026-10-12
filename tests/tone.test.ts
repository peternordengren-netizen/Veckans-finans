// Tester för "avviker" (nyhetens ton mot kursrörelsen relativt index). Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { divergesFromPrice } from "../src/lib/tone.ts";

test("positiv ton och sämre än index avviker – även om kursen steg", () => {
  assert.equal(divergesFromPrice("positiv", { relative_pp: -0.6 }), true);
});

test("negativ ton och bättre än index avviker – även om kursen föll", () => {
  assert.equal(divergesFromPrice("negativ", { relative_pp: 0.4 }), true);
});

test("samma håll som index-skillnaden avviker inte – även om kursen föll", () => {
  assert.equal(divergesFromPrice("positiv", { relative_pp: 3.8 }), false);
  assert.equal(divergesFromPrice("negativ", { relative_pp: -2.3 }), false);
});

test("neutral, lika med index, saknad jämförelse, saknad kurs eller saknad ton avviker aldrig", () => {
  assert.equal(divergesFromPrice("neutral", { relative_pp: -5 }), false);
  assert.equal(divergesFromPrice("positiv", { relative_pp: 0 }), false);
  assert.equal(divergesFromPrice("positiv", { relative_pp: null }), false);
  assert.equal(divergesFromPrice("positiv", {}), false);
  assert.equal(divergesFromPrice("positiv", null), false);
  assert.equal(divergesFromPrice(undefined, { relative_pp: -5 }), false);
});
