// Tester för "Rapporterade bolag". Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  epsLabel,
  expectedText,
  kpiValue,
  lastYearKpi,
  lastYearText,
  periodVsLastYear,
  reactionOutcome,
  surpriseShort,
  surpriseText,
  yoyText,
} from "../src/lib/results.ts";

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

test("kursreaktion: mot förväntan, mot fjol och kurs mot utfallet", () => {
  const eps = (verdict: string, surprise_pct: number) =>
    ({ actual: 2.5, expected: 2.4, analysts: 4, currency: "SEK", surprise_pct, verdict, basis: "justerat" }) as const;
  const report = (verdict: string, surprise_pct: number) => ({
    ticker: "ALFA", name: "Alfaverken", sector: null, published: "", url: "", source_name: "", period: "Q3 2026",
    note: null,
    kpis: [{ id: "resultat-per-aktie", name: "Resultat per aktie", value: 2.5, unit: "SEK", previous_value: 2.0,
      change_pct: 25, yoy_pct: 25, period_kind: "kvartal" as const, quote: "" }],
    vs_consensus: { consensus_date: "2026-10-22", eps: eps(verdict, surprise_pct) as never, revenue: null },
  });
  const over = reactionOutcome(-3.1, report("över", 4.2));
  assert.equal(over.vsExpected?.text, "+4,2 %");
  assert.equal(over.vsExpected?.basis, "justerat");
  assert.equal(over.vsLastYear, "+25 %");
  assert.equal(over.divergent, true); // över förväntan men kursen föll
  assert.equal(reactionOutcome(2.0, report("över", 4.2)).divergent, false);
  assert.equal(reactionOutcome(1.5, report("under", -6.0)).divergent, true); // under förväntan men kursen steg
  assert.equal(reactionOutcome(1.5, report("i linje", 1.0)).divergent, false);
  assert.equal(reactionOutcome(-9, report("kontrollera", 80)).divergent, false); // bara över/under markeras
  assert.equal(reactionOutcome(-9, report("bolagshändelse", 80)).vsExpected?.text, "bolagshändelse");
  assert.equal(reactionOutcome(null, report("över", 4.2)).divergent, false);
  assert.equal(over.vsLastYearTitle, "Q3 2026 mot Q3 2025 · Resultat per aktie");
  const none = reactionOutcome(2.0, undefined);
  assert.deepEqual(none, { vsExpected: null, vsLastYear: "–", vsLastYearTitle: null, divergent: false });
});

test("mot fjol: båda värdena vid teckenbyte, nära noll och över ±200 %", () => {
  const k = (value: number, previous_value: number | null, yoy_pct: number | null) =>
    ({ value, previous_value, yoy_pct, unit: "SEK" });
  assert.equal(lastYearText(k(2.42, 5.19, -53.4)), `${MINUS}53 %`);
  assert.equal(lastYearText(k(4.05, 3.0, 35)), "+35 %");
  assert.equal(lastYearText(k(9.38, 1.77, 429.9)), "9,38 kr (1,77)"); // över +200 %
  assert.equal(lastYearText(k(-0.46, 0.39, null)), `${MINUS}0,46 kr (0,39)`); // teckenbyte
  assert.equal(lastYearText(k(0.02, 0.85, -97.6)), "0,02 kr (0,85)"); // nära noll
  assert.equal(lastYearText(k(2.0, 2.0, 0)), "0 %");
  assert.equal(lastYearText(k(2.5, null, 30)), "+30 %"); // bara rapportens egen procentsats
  assert.equal(lastYearText(k(2.5, null, null)), "–");
  assert.equal(periodVsLastYear("Q3 2026"), "Q3 2026 mot Q3 2025");
  assert.equal(periodVsLastYear("januari–september"), "januari–september");
});

test("mot fjol för fastighetsbolag: förvaltningsresultat per aktie när det finns", () => {
  const kpi = (id: string, name: string, value: number, prev: number, period_kind = "kvartal" as const) =>
    ({ id, name, value, unit: "SEK", previous_value: prev, change_pct: null, yoy_pct: null, period_kind, quote: "" });
  const base = { ticker: "BETA", name: "Betabolaget", published: "", url: "", source_name: "", period: "Q3 2026",
    note: null, vs_consensus: null };
  const eps = kpi("resultat-per-aktie", "Resultat per aktie", 9.38, 1.77);
  const fr = kpi("forvaltningsresultat-per-aktie", "Förvaltningsresultat per aktie", 2.1, 1.9);
  const prop = reactionOutcome(1, { ...base, sector: "fastigheter", kpis: [eps, fr] });
  assert.equal(prop.vsLastYear, "+11 %");
  assert.equal(prop.vsLastYearTitle, "Q3 2026 mot Q3 2025 · Förvaltningsresultat per aktie");
  // Utan förvaltningsresultat per aktie för kvartalet: resultat per aktie.
  const noFr = reactionOutcome(1, { ...base, sector: "fastigheter", kpis: [eps, { ...fr, period_kind: "delår" as never }] });
  assert.equal(noFr.vsLastYear, "9,38 kr (1,77)");
  // Andra sektorer använder alltid resultat per aktie.
  assert.equal(lastYearKpi({ ...base, sector: "industri", kpis: [eps, fr] })?.id, "resultat-per-aktie");
});

test("kort form mot förväntan i kursreaktionen", () => {
  const c = { actual: 2.5, expected: 2.4, analysts: 4, currency: "SEK", surprise_pct: 4.2, verdict: "över" as const };
  assert.equal(surpriseShort(c), "+4,2 %");
  assert.equal(surpriseShort({ ...c, verdict: "i linje" }), "i linje");
  assert.equal(surpriseShort({ ...c, verdict: "bolagshändelse" }), "bolagshändelse");
  assert.equal(surpriseShort({ ...c, actual: -0.26, expected: 0.70712, surprise_pct: -136.8, verdict: "teckenbyte" }),
    `${MINUS}0,26 kr (förv. 0,707)`);
  assert.equal(surpriseShort({ ...c, actual: -1.63, expected: -0.14, verdict: "nära noll" }), `${MINUS}1,63 kr (förv. ${MINUS}0,14)`);
  assert.equal(
    surpriseShort({ ...c, actual: 0.166, expected: 0.07357, currency: "EUR", surprise_pct: 125.6, verdict: "kontrollera" }),
    "kontrollera: 0,166 EUR (förv. 0,074)",
  );
  assert.equal(surpriseShort({ ...c, actual: 1.5e9, expected: 4e9, verdict: "kontrollera" }, false), "kontrollera: 1,5 mdr kr (förv. 4 mdr)");
});
