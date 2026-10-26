/**
 * Blankningspositioner för visning: gruppering per bolag, innehavare sorterade efter positionens
 * storlek och innehavarnamn med normal versalisering. Används av morgonrapporten och veckans flik
 * "Blankning & insyn". Ren modul (testas med node --test).
 */

export interface HolderChange {
  holder: string;
  start_pct: number;
  end_pct: number;
  change_pp: number;
}

export interface PositionChange extends HolderChange {
  ticker: string;
  name: string;
}

export interface CompanyShort<H extends HolderChange = HolderChange> {
  ticker: string;
  name: string;
  /** Summan av innehavarnas förändring i procentenheter. */
  change_pp: number;
  holders: H[];
}

// Förkortningar och bolagsformer som skrivs som de brukar, inte med bara stor begynnelsebokstav
// (versal form i FI:s register -> visning).
const KEEP = new Map<string, string>([
  ...["LLC", "LLP", "LP", "L.P.", "AB", "ASA", "AS", "A/S", "AG", "SA", "S.A.", "NV", "N.V.", "BV", "PLC", "SE", "UK",
    "US", "USA", "II", "III", "IV", "SICAV", "AIF", "ICAV", "UCITS", "KG", "SAS"].map((w): [string, string] => [w, w]),
  ["GMBH", "GmbH"], ["LTD", "Ltd"], ["LTD.", "Ltd."], ["INC", "Inc"], ["INC.", "Inc."], ["CORP", "Corp"],
  ["CORP.", "Corp."], ["CO", "Co"], ["CO.", "Co."], ["SARL", "Sàrl"], ["SPA", "SpA"], ["S.P.A.", "S.p.A."],
  ["OY", "Oy"], ["OYJ", "Oyj"], ["(PUBL)", "(publ)"],
]);

const capitalize = (part: string) => part.charAt(0).toLocaleUpperCase("sv-SE") + part.slice(1);
// Småord som skrivs med gemen inne i ett namn ("Bank of America", "Fonds de Placement").
const SMALL = new Set(["of", "and", "the", "for", "de", "du", "des", "la", "le", "van", "von", "der", "och", "för"]);

/**
 * Innehavarens namn med normal versalisering när FI anger det med enbart versaler:
 * "CITADEL ADVISORS LLC" -> "Citadel Advisors LLC", "MARSHALL WACE LLP" -> "Marshall Wace LLP",
 * "AQR CAPITAL MANAGEMENT, LLC" -> "Aqr Capital Management, LLC". Namn med gemener lämnas orörda.
 */
export function holderName(raw: string): string {
  if (!/[A-ZÅÄÖÉÜ]/.test(raw) || /[a-zåäöéü]/.test(raw)) return raw;
  return raw
    .split(/(\s+)/)
    .map((word, i) => {
      if (/^\s+$/.test(word)) return word;
      const bare = word.replace(/[,;]$/, "");
      const tail = word.slice(bare.length);
      const kept = KEEP.get(bare);
      if (kept) return kept + tail;
      const lower = bare.toLocaleLowerCase("sv-SE");
      if (i > 0 && SMALL.has(lower)) return lower + tail;
      // "BLACKROCK-INVESTMENT" -> "Blackrock-Investment", "O'NEIL" -> "O'Neil"
      return bare.toLocaleLowerCase("sv-SE").split(/([-'’/&.(])/).map(capitalize).join("") + tail;
    })
    .join("");
}

/** Innehavare sorterade efter positionens storlek: störst nu först, därefter störst före förändringen. */
export function sortBySize<H extends HolderChange>(holders: H[]): H[] {
  return [...holders].sort((a, b) => b.end_pct - a.end_pct || b.start_pct - a.start_pct || a.holder.localeCompare(b.holder, "sv"));
}

/**
 * Positioner grupperade per bolag: innehavarna sorterade efter positionens storlek, bolagen efter
 * största totala förändring (absolut belopp), därefter namn.
 */
export function groupByCompany(positions: PositionChange[]): CompanyShort<PositionChange>[] {
  const byTicker = new Map<string, CompanyShort<PositionChange>>();
  for (const p of positions) {
    const c = byTicker.get(p.ticker) ?? { ticker: p.ticker, name: p.name, change_pp: 0, holders: [] };
    c.holders.push(p);
    c.change_pp += p.change_pp;
    byTicker.set(p.ticker, c);
  }
  return [...byTicker.values()]
    .map((c) => ({ ...c, change_pp: Math.round(c.change_pp * 100) / 100, holders: sortBySize(c.holders) }))
    .sort((a, b) => Math.abs(b.change_pp) - Math.abs(a.change_pp) || a.name.localeCompare(b.name, "sv"));
}
