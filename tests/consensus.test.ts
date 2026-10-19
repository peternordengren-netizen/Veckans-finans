// Tester för konsensustexterna i "Kommande vecka". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { amount, estimateText, perShare, warnings, type Consensus } from "../src/lib/consensus.ts";

const base: Consensus = {
  ticker: "ALFA",
  eps: { avg: 5.426, low: 5.3, high: 5.68, analysts: 4, year_ago: 5.53, currency: "SEK" },
  revenue: { avg: 18_620_796_000, low: null, high: null, analysts: 11, year_ago: 17_244_000_000, currency: "SEK" },
  next_report_date: "2026-10-27",
  financial_currency: "SEK",
  analyst_opinions: 16,
};

test("belopp och vinst per aktie", () => {
  assert.equal(perShare(5.426, "SEK"), "5,43 kr");
  assert.equal(perShare(2.63, "USD"), "2,63 USD");
  assert.equal(amount(18_620_796_000, "SEK"), "18,6 mdr kr");
  assert.equal(amount(950_400_000, "SEK"), "950 mn kr");
  assert.equal(amount(1_234_000_000, "EUR"), "1,2 mdr EUR");
});

test("prognostext med antal analytiker och föregående år", () => {
  assert.equal(estimateText(base.eps!, perShare), "5,43 kr (4 analytiker, i fjol 5,53 kr)");
  assert.equal(
    estimateText({ ...base.revenue!, analysts: null, year_ago: null }, amount),
    "18,6 mdr kr",
  );
});

test("varningar: få analytiker, annan valuta, fastigheter", () => {
  assert.deepEqual(warnings(base, "industri"), []);
  assert.deepEqual(warnings({ ...base, eps: { ...base.eps!, analysts: 2 } }, "industri"), [
    "bara 2 analytiker för vinst per aktie",
  ]);
  assert.deepEqual(warnings({ ...base, eps: null }, "industri"), ["ingen prognos för vinst per aktie"]);
  assert.deepEqual(warnings({ ...base, financial_currency: "EUR" }, "teknik"), ["redovisar i EUR"]);
  assert.deepEqual(warnings(base, "fastigheter"), [
    "vinst per aktie styrs av värdeförändringar – se förvaltningsresultatet",
  ]);
});

test("konsensus efter rapport visas inte", () => {
  assert.deepEqual(warnings({ ...base, after_report: true }, "fastigheter"), ["konsensus efter rapport – visas inte"]);
  assert.deepEqual(warnings({ ...base, after_report: false }, "industri"), []);
});
