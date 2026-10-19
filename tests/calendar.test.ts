// Tester för rapportkalenderns visningstexter. Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { byDay, statusText, weekdayDate } from "../src/lib/calendar.ts";

test("veckodag och kort datum", () => {
  assert.equal(weekdayDate("2026-10-22"), "Torsdag 22 okt");
  assert.equal(weekdayDate("2026-10-19"), "Måndag 19 okt");
  assert.equal(weekdayDate("2026-11-01"), "Söndag 1 nov");
});

test("statustexter visar båda datumen vid avvikelse", () => {
  assert.equal(statusText({ status: "bekräftat", yahoo_date: "2026-10-22", mfn_date: "2026-10-22" }), "bekräftat av MFN");
  assert.equal(
    statusText({ status: "avvikelse", yahoo_date: "2026-10-21", mfn_date: "2026-10-23" }),
    "olika datum: Yahoo 21 okt, MFN 23 okt",
  );
  assert.equal(statusText({ status: "yahoo", yahoo_date: "2026-10-21", mfn_date: null }), "enligt Yahoo");
  assert.equal(statusText({ status: "mfn", yahoo_date: null, mfn_date: "2026-10-21" }), "enligt MFN");
});

test("gruppering per dag i datumordning", () => {
  const days = byDay([{ date: "2026-10-23", n: 1 }, { date: "2026-10-21", n: 2 }, { date: "2026-10-23", n: 3 }]);
  assert.deepEqual(days.map((d) => [d.date, d.events.map((e) => e.n)]), [
    ["2026-10-21", [2]],
    ["2026-10-23", [1, 3]],
  ]);
});
