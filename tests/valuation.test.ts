// Tester för fliken "Kurs mot vinst". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { epsChange, epsPair, interpretation, pePair } from "../src/lib/valuation.ts";

const MINUS = "−";

test("vinst rullande 12 månader och förändring", () => {
  assert.equal(epsPair({ eps_ttm_start: 4, eps_ttm_now: 4.5, financial_currency: "SEK" }), "4,00 → 4,50 kr");
  assert.equal(epsPair({ eps_ttm_start: 1.2, eps_ttm_now: 1.5, financial_currency: "USD" }), "1,20 → 1,50 USD");
  assert.equal(epsPair({ eps_ttm_start: null, eps_ttm_now: 4.5, financial_currency: "SEK" }), "–");
  assert.equal(epsChange({ eps_change_pct: 12.5 }), "+13 %");
  assert.equal(epsChange({ eps_change_pct: -11.6 }), `${MINUS}12 %`);
  assert.equal(epsChange({ eps_change_pct: null }), "–");
});

test("P/E vid årets början och nu", () => {
  assert.equal(pePair({ pe_start: 25, pe_now: 28.9, pe_over_max: false }), "25,0 → 28,9");
  assert.equal(pePair({ pe_start: 19.3, pe_now: 1676, pe_over_max: true }), "19,3 → över 100");
  assert.equal(pePair({ pe_start: null, pe_now: null, pe_over_max: false }), "–");
});

test("tolkning eller status", () => {
  assert.equal(interpretation({ status: "ok", verdict: "kursen före vinsten", pe_over_max: false }), "kursen före vinsten");
  assert.equal(interpretation({ status: "ok", verdict: null, pe_over_max: true }), "P/E över 100 – ingen tolkning");
  assert.equal(interpretation({ status: "kontrollera bolagshändelse", verdict: null, pe_over_max: false }),
    "kontrollera bolagshändelse");
  assert.equal(interpretation({ status: "fastighetsbolag", verdict: null, pe_over_max: false }),
    "fastighetsbolag – se förvaltningsresultatet");
});

test("känd bolagshändelse visar etiketten", () => {
  assert.equal(
    interpretation({ status: "känd bolagshändelse", verdict: null, pe_over_max: false, event_label: "noterad i Stockholm 9 jan" }),
    "noterad i Stockholm 9 jan",
  );
  assert.equal(interpretation({ status: "känd bolagshändelse", verdict: null, pe_over_max: false }), "känd bolagshändelse");
});

test("noterad under året visar dagen", () => {
  assert.equal(
    interpretation({ status: "noterad under året", verdict: null, pe_over_max: false, event_label: "noterad under året (12 juni)" }),
    "noterad under året (12 juni)",
  );
  assert.equal(interpretation({ status: "kurs saknas", verdict: null, pe_over_max: false }), "kurs saknas");
});
