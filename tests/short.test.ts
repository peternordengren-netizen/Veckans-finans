// Tester för blankningsvisningen (src/lib/short.ts). Körs med `npm run test:js`. Påhittade innehavare och bolag.
import assert from "node:assert/strict";
import { test } from "node:test";

import { groupByCompany, holderName, sortBySize } from "../src/lib/short.ts";

test("innehavarnamn med normal versalisering", () => {
  assert.equal(holderName("NORDKAPP ADVISORS LLC"), "Nordkapp Advisors LLC");
  assert.equal(holderName("FJORD WACE LLP"), "Fjord Wace LLP");
  assert.equal(holderName("ALBION CAPITAL MANAGEMENT, LLC"), "Albion Capital Management, LLC");
  assert.equal(holderName("KUSTEN FONDER AB (PUBL)"), "Kusten Fonder AB (publ)");
  assert.equal(holderName("VÄSTERÅS KAPITAL GMBH"), "Västerås Kapital GmbH");
  assert.equal(holderName("O'NEIL-HARBOUR CO. LTD"), "O'Neil-Harbour Co. Ltd");
  assert.equal(holderName("NORTH BANK OF ALBION AND CO"), "North Bank of Albion and Co");
  assert.equal(holderName("THE FJORD FUND"), "The Fjord Fund");  // först i namnet: stor bokstav
  // Namn som redan har gemener lämnas orörda.
  assert.equal(holderName("Nordkapp Advisors LLC"), "Nordkapp Advisors LLC");
  assert.equal(holderName("AQR"), "Aqr");
});

const pos = (ticker: string, name: string, holder: string, start_pct: number, end_pct: number) =>
  ({ ticker, name, holder, start_pct, end_pct, change_pp: Math.round((end_pct - start_pct) * 100) / 100 });

test("innehavare sorterade efter positionens storlek", () => {
  const sorted = sortBySize([pos("A", "A", "liten", 0.5, 0.6), pos("A", "A", "stor", 1.2, 0.9), pos("A", "A", "mellan", 0, 0.7)]);
  assert.deepEqual(sorted.map((h) => h.holder), ["stor", "mellan", "liten"]);
  // Avvecklad position (0 nu) sorteras efter storleken före.
  const closed = sortBySize([pos("A", "A", "kvar", 0.5, 0.55), pos("A", "A", "såld", 1.0, 0), pos("A", "A", "såld liten", 0.6, 0)]);
  assert.deepEqual(closed.map((h) => h.holder), ["kvar", "såld", "såld liten"]);
});

test("gruppering per bolag med total förändring, största först", () => {
  const groups = groupByCompany([
    pos("ALFA", "Alfaverken", "x", 0.5, 0.6),
    pos("BETA", "Betabolaget", "y", 1.0, 0.5),
    pos("ALFA", "Alfaverken", "z", 0.6, 0.8),
    pos("BETA", "Betabolaget", "w", 0, 0.6),
    pos("GAMMA", "Gammagruppen", "v", 0.7, 0.75),
  ]);
  assert.deepEqual(groups.map((g) => [g.ticker, g.change_pp]), [["ALFA", 0.3], ["BETA", 0.1], ["GAMMA", 0.05]]);
  assert.deepEqual(groups[0].holders.map((h) => h.holder), ["z", "x"]);
  assert.deepEqual(groups[1].holders.map((h) => h.holder), ["w", "y"]); // 0,6 nu före 0,5 nu
  // Minskning räknas på absolut belopp.
  const down = groupByCompany([pos("ALFA", "Alfaverken", "x", 0.9, 0.5), pos("BETA", "Betabolaget", "y", 0.5, 0.7)]);
  assert.deepEqual(down.map((g) => [g.ticker, g.change_pp]), [["ALFA", -0.4], ["BETA", 0.2]]);
});
