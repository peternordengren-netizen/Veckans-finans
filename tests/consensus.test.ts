// Tester för konsensustexterna i "Kommande vecka". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { amount, estimateText, expectedChange, perShare, warnings, type Consensus } from "../src/lib/consensus.ts";

const MINUS = "\u2212";

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

test("prognostext med förväntad förändring mot fjol och antal analytiker", () => {
  assert.equal(estimateText(base.eps!, perShare), `5,43 kr (${MINUS}2 % mot fjol, 4 analytiker)`);
  assert.equal(estimateText({ ...base.eps!, avg: 2.37, year_ago: 1.9 }, perShare), "2,37 kr (+25 % mot fjol, 4 analytiker)");
  assert.equal(estimateText(base.revenue!, amount), "18,6 mdr kr (+8 % mot fjol, 11 analytiker)");
  // Över ±200 %: fjolårets värde i stället för procentsatsen; exakt 200 % visas fortfarande som procent.
  assert.equal(estimateText({ ...base.eps!, avg: -0.27, year_ago: -0.02, analysts: 2 }, perShare),
    `${MINUS}0,27 kr (i fjol ${MINUS}0,02 kr, 2 analytiker)`);
  assert.equal(estimateText({ ...base.eps!, avg: 0.76, year_ago: 0.2 }, perShare), "0,76 kr (i fjol 0,20 kr, 4 analytiker)");
  assert.equal(estimateText({ ...base.eps!, avg: 0.6, year_ago: 0.2 }, perShare), "0,60 kr (+200 % mot fjol, 4 analytiker)");
  assert.equal(estimateText({ ...base.revenue!, avg: 3.5e9, year_ago: 1e9 }, amount), "3,5 mdr kr (i fjol 1,0 mdr kr, 11 analytiker)");
  // Från förlust till vinst: ingen procentsats, fjolårets värde i stället.
  assert.equal(estimateText({ ...base.eps!, avg: 0.4, year_ago: -0.2, analysts: 2 }, perShare),
    `0,40 kr (i fjol ${MINUS}0,20 kr, 2 analytiker)`);
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

test("förväntad förändring", () => {
  assert.equal(Math.round(expectedChange({ ...base.eps!, avg: 2.37, year_ago: 1.9 })! * 10) / 10, 24.7);
  assert.equal(expectedChange({ ...base.eps!, year_ago: null }), null);
  assert.equal(expectedChange({ ...base.eps!, year_ago: 0 }), null);
  assert.equal(expectedChange({ ...base.eps!, avg: -0.5, year_ago: 0.4 }), null);
  // Två förluster: mindre förlust än i fjol är en positiv förändring.
  assert.equal(expectedChange({ ...base.eps!, avg: -0.5, year_ago: -1 }), 50);
});

test("stor förändring, få analytiker: över ±50 % och färre än 3 analytiker", () => {
  const big = { ...base.eps!, avg: 3.2, year_ago: 2.0 }; // +60 %
  assert.deepEqual(warnings({ ...base, eps: { ...big, analysts: 2 } }, "industri"), [
    "bara 2 analytiker för vinst per aktie",
    "stor förändring, få analytiker",
  ]);
  assert.deepEqual(warnings({ ...base, eps: { ...big, analysts: 3 } }, "industri"), []); // tillräckligt många
  assert.deepEqual(warnings({ ...base, eps: { ...big, avg: 3.0, analysts: 1 } }, "industri"), [
    "bara 1 analytiker för vinst per aktie",
  ]); // exakt +50 %: ingen varning
  // Varningen gäller även när procentsatsen inte visas (över ±200 %).
  assert.deepEqual(warnings({ ...base, eps: { ...base.eps!, avg: -0.27, year_ago: -0.02, analysts: 2 } }, "industri"), [
    "bara 2 analytiker för vinst per aktie",
    "stor förändring, få analytiker",
  ]);
  // Omsättningen räknas också.
  const rev = { ...base.revenue!, avg: 2e9, year_ago: 1e9, analysts: 2 }; // +100 %
  assert.deepEqual(warnings({ ...base, revenue: rev }, "industri"), ["stor förändring, få analytiker"]);
});