// Tester för "Rapporterade bolag". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { epsLabel, expectedText, kpiValue, surpriseText, yoyText } from "../src/lib/results.ts";

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
  // Stor förändring, få analytiker: ingen avvikelse och inget över/under.
  assert.equal(surpriseText({ ...c, surprise_pct: -43.9, verdict: "osäker konsensus" }), "osäker konsensus");
  assert.equal(epsLabel({ basis: "justerat" }), "Justerat resultat per aktie");
  assert.equal(epsLabel({ basis: "redovisat" }), "Resultat per aktie");
  assert.equal(epsLabel({}), "Resultat per aktie");  // äldre filer
  // Bolagshändelse, teckenbyte, nära noll och kontrollera (utredningen W43).
  assert.equal(surpriseText({ ...c, verdict: "bolagshändelse" }), "bolagshändelse påverkar jämförelsen");
  assert.equal(surpriseText({ ...c, actual: -0.46, expected: 0.53, surprise_pct: -187.6, verdict: "teckenbyte" }),
    `utfall ${MINUS}0,46 kr, förväntan 0,53 kr`);
  assert.equal(surpriseText({ ...c, actual: -1.63, expected: -0.14, surprise_pct: -1064.3, verdict: "nära noll" }),
    `utfall ${MINUS}1,63 kr, förväntan ${MINUS}0,14 kr`);
  assert.equal(
    surpriseText({ ...c, actual: 0.166, expected: 0.07357, currency: "EUR", surprise_pct: 125.6, verdict: "kontrollera" }),
    "kontrollera: utfall 0,166 EUR, förväntan 0,074 EUR",
  );
  assert.equal(surpriseText({ ...c, actual: 1.5e9, expected: 4e9, verdict: "kontrollera" }, false),
    "kontrollera: utfall 1,5 mdr kr, förväntan 4 mdr kr");
  assert.equal(expectedText(c, true), "2,4 kr");
  assert.equal(expectedText({ ...c, expected: 1.6e9 }, false), "1,6 mdr kr");
  assert.equal(expectedText({ ...c, expected: 950e6 }, false), "950 mn kr");
});
