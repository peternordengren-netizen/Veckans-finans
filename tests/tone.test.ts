// Tester för "avviker" (nyhetens ton mot veckans kursrörelse). Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { divergesFromPrice } from "../src/lib/tone.ts";

test("positiv ton och sjunkande kurs avviker", () => {
  assert.equal(divergesFromPrice("positiv", { change_pct: -1.9 }), true);
});

test("negativ ton och stigande kurs avviker", () => {
  assert.equal(divergesFromPrice("negativ", { change_pct: 0.4 }), true);
});

test("samma håll avviker inte", () => {
  assert.equal(divergesFromPrice("positiv", { change_pct: 4.8 }), false);
  assert.equal(divergesFromPrice("negativ", { change_pct: -2.3 }), false);
});

test("neutral, oförändrad kurs, saknad kurs eller saknad ton avviker aldrig", () => {
  assert.equal(divergesFromPrice("neutral", { change_pct: -5 }), false);
  assert.equal(divergesFromPrice("positiv", { change_pct: 0 }), false);
  assert.equal(divergesFromPrice("positiv", null), false);
  assert.equal(divergesFromPrice(undefined, { change_pct: -5 }), false);
});
