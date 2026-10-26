// Tester för varningen om saknad vecka. Körs med `npm run test:js`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { claudeLimitWarning, isoWeek, missingWeekWarning, previousWeek } from "../src/lib/weekCheck.ts";

test("varning när Claudes användningsgräns nåtts", () => {
  const monday = new Date("2026-10-26T06:31:00Z"); // 07:31 svensk tid (vintertid)
  assert.equal(claudeLimitWarning("2026-10-26T08:00+01:00", monday), "Claudes användningsgräns nådd – försöker igen efter 08:00");
  assert.equal(claudeLimitWarning("2026-10-27T08:00+01:00", monday), "Claudes användningsgräns nådd – försöker igen efter 27 okt. 08:00");
  assert.equal(claudeLimitWarning(null, monday), "Claudes användningsgräns nådd – försöker igen efter återställningen");
});

test("isoWeek hanterar årsskiften", () => {
  assert.equal(isoWeek(2026, 10, 12), "2026-W42");
  assert.equal(isoWeek(2026, 10, 18), "2026-W42");
  assert.equal(isoWeek(2027, 1, 1), "2026-W53"); // fredag 1 jan 2027 hör till 2026 års sista vecka
  assert.equal(isoWeek(2024, 12, 30), "2025-W01");
});

test("förra veckan räknas i svensk tid", () => {
  // Måndag 19 okt 07:30 svensk tid (05:30 UTC) → förra veckan är W42.
  assert.equal(previousWeek(new Date("2026-10-19T05:30:00Z")), "2026-W42");
  // Söndag 18 okt 23:30 svensk tid (21:30 UTC) är fortfarande W42 → förra veckan är W41.
  assert.equal(previousWeek(new Date("2026-10-18T21:30:00Z")), "2026-W41");
  // Måndag 00:30 svensk tid, trots att det är söndag i UTC.
  assert.equal(previousWeek(new Date("2026-10-18T22:30:00Z")), "2026-W42");
});

test("varning när senaste veckan är äldre än förra veckan", () => {
  const monday = new Date("2026-10-19T08:00:00Z");
  assert.equal(missingWeekWarning("2026-W41", monday), "Vecka 42 saknas – se logs/weekly/");
  assert.equal(missingWeekWarning("2026-W42", monday), null);
  assert.equal(missingWeekWarning("2026-W43", monday), null);
  assert.equal(missingWeekWarning(null, monday), "Vecka 42 saknas – se logs/weekly/");
  // Under veckan efter (onsdag) gäller samma förväntan.
  assert.equal(missingWeekWarning("2026-W42", new Date("2026-10-21T12:00:00Z")), null);
});
