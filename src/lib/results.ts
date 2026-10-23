/**
 * Visningstexter för "Rapporterade bolag" (scripts/results.py, data/results/<vecka>.json).
 * Ren modul (testas med node --test).
 */

export interface ResultKpi {
  id: string;
  name: string;
  value: number;
  unit: string;
  previous_value: number | null;
  change_pct: number | null;
  yoy_pct: number | null;
  period_kind: "kvartal" | "delår" | "helår";
  quote: string;
}

export interface Comparison {
  actual: number;
  expected: number;
  analysts: number | null;
  currency: string;
  surprise_pct: number;
  verdict: "över" | "i linje" | "under" | "osäker konsensus" | "bolagshändelse" | "teckenbyte" | "nära noll" | "kontrollera";
  /** Resultat per aktie: justerat eller redovisat värde jämfört med förväntan (saknas = redovisat). */
  basis?: "justerat" | "redovisat";
}

/** Rubriken för jämförelsen av resultat per aktie: "Justerat resultat per aktie" eller "Resultat per aktie". */
export function epsLabel(c: Pick<Comparison, "basis">): string {
  return c.basis === "justerat" ? "Justerat resultat per aktie" : "Resultat per aktie";
}

export interface ReportResult {
  ticker: string;
  name: string;
  sector: string | null;
  published: string;
  url: string;
  source_name: string;
  period: string;
  note: string | null;
  kpis: ResultKpi[];
  vs_consensus: {
    consensus_date: string;
    /** Varningen "stor förändring, få analytiker": ingen bedömning över/under (saknas i äldre filer). */
    uncertain?: boolean;
    /** Känd bolagshändelse under året: ingen procent mot förväntan (saknas i äldre filer). */
    corporate_event?: boolean;
    eps: Comparison | null;
    revenue: Comparison | null;
  } | null;
}

const UNIT_LABELS: Record<string, string> = { SEK: "kr", TSEK: "tkr", MSEK: "mn kr", MDSEK: "mdr kr", procent: "%" };
const nf = new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 2 });
const signed = (v: number, digits: number) =>
  new Intl.NumberFormat("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: "exceptZero" }).format(v);

/** "1 683 mn kr", "2,23 kr", "11,2 %", "1 234 MEUR". */
export function kpiValue(value: number, unit: string): string {
  return `${nf.format(value)} ${UNIT_LABELS[unit] ?? unit}`;
}

/**
 * Förändring mot samma period i fjol: "+21 %", "+0,7 procentenheter" för procenttal,
 * "från vinst till förlust" när tecknet bytts (en procentsats säger då inget), annars "–".
 */
export function yoyText(k: Pick<ResultKpi, "value" | "previous_value" | "yoy_pct" | "unit">): string {
  const prev = k.previous_value;
  if (prev !== null && prev !== 0 && Math.sign(prev) !== Math.sign(k.value) && k.value !== 0) {
    return k.value < 0 ? "från vinst till förlust" : "från förlust till vinst";
  }
  if (k.unit === "procent") {
    return prev === null ? "–" : `${signed(k.value - prev, 1)} procentenheter`;
  }
  return k.yoy_pct === null ? "–" : `${signed(k.yoy_pct, 0)} %`;
}

/**
 * Utfall mot förväntan:
 * - "+4,2 % mot förväntan", eller "i linje med förväntan" inom ±2 %
 * - "osäker konsensus" (stor förändring, få analytiker) och "bolagshändelse påverkar jämförelsen":
 *   ingen procent
 * - teckenbyte och nära noll: båda värdena utan procent, som i "Kommande vecka"
 * - "kontrollera" (över ±50 % utan förklaring): båda värdena
 */
export function surpriseText(c: Comparison, perShare = true): string {
  const both = `utfall ${amountText(c.actual, c.currency, perShare)}, förväntan ${amountText(c.expected, c.currency, perShare)}`;
  switch (c.verdict) {
    case "osäker konsensus":
      return "osäker konsensus";
    case "bolagshändelse":
      return "bolagshändelse påverkar jämförelsen";
    case "teckenbyte":
    case "nära noll":
      return both;
    case "kontrollera":
      return `kontrollera: ${both}`;
    case "i linje":
      return "i linje med förväntan";
    default:
      return `${signed(c.surprise_pct, 1)} % mot förväntan`;
  }
}

/** Belopp i samma skala som utfallet: per aktie med två decimaler (tre under 1, så att t.ex.
 * 16,6 eurocent blir "0,166 EUR"), omsättning i mn/mdr. */
export function amountText(value: number, currency: string, perShare: boolean): string {
  const unit = currency === "SEK" ? "kr" : currency;
  if (perShare) {
    const digits = Math.abs(value) < 1 ? 3 : 2;
    return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: digits }).format(value)} ${unit}`;
  }
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 1 }).format(value / 1e9)} mdr ${unit}`;
  return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(value / 1e6)} mn ${unit}`;
}

/** Förväntat belopp i samma skala som utfallet. */
export function expectedText(c: Comparison, perShare: boolean): string {
  return amountText(c.expected, c.currency, perShare);
}
