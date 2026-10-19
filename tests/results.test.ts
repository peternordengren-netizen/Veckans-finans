// Tester för "Rapporterade bolag". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { expectedText, kpiValue, surpriseText, yoyText } from "../src/lib/results.ts";

const MINUS = "−";
const NBSP = " ";

test("värden med enhet", () => {
  assert.equal(kpiValue(1683, "MSEK"), `1${NBSP}683 mn kr`);
  assert.equal(kpiValue(2.23, "SEK"), "2,23 kr");
  assert.equal(kpiValue(11.2, "procent"), "11,2 %");
  assert.equal(kpiValue(1234, "MEUR"), `1${NBSP}234 MEUR`);
});

test("förändring mot i fjol", () => {
  assert.equal(yoyText({ value: 2566, previous_value: 2114, yoy_pct: 21, unit: "MSEK" }), "+21 %");
  assert.equal(yoyText({ value: 11.2, previous_value: 10.5, yoy_pct: null, unit: "procent" }), "+0,7 procentenheter");
  assert.equal(yoyText({ value: -1.13, previous_value: 1.7, yoy_pct: -166.5, unit: "SEK" }), "från vinst till förlust");
  assert.equal(yoyText({ value: 0.4, previous_value: -0.2, yoy_pct: 300, unit: "SEK" }), "från förlust till vinst");
  assert.equal(yoyText({ value: 3.51, previous_value: null, yoy_pct: 30, unit: "SEK" }), "+30 %");
  assert.equal(yoyText({ value: 3.51, previous_value: null, yoy_pct: null, unit: "SEK" }), "–");
});

test("utfall mot förväntan", () => {
  const c = { actual: 2.5, expected: 2.4, analysts: 4, currency: "SEK", surprise_pct: 4.2, verdict: "över" as const };
  assert.equal(surpriseText(c), "+4,2 % mot förväntan");
  assert.equal(surpriseText({ ...c, surprise_pct: -6.2, verdict: "under" }), `${MINUS}6,2 % mot förväntan`);
  assert.equal(surpriseText({ ...c, surprise_pct: 1.1, verdict: "i linje" }), "i linje med förväntan");
  assert.equal(expectedText(c, true), "2,4 kr");
  assert.equal(expectedText({ ...c, expected: 1.6e9 }, false), "1,6 mdr kr");
  assert.equal(expectedText({ ...c, expected: 950e6 }, false), "950 mn kr");
});
