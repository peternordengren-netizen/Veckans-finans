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
  verdict: "över" | "i linje" | "under" | "osäker konsensus";
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
 * Utfall mot förväntan: "+4,2 % mot förväntan", "i linje med förväntan" inom ±2 %, eller
 * "osäker konsensus" (stor förändring, få analytiker) – då utan avvikelse och över/under.
 */
export function surpriseText(c: Comparison): string {
  if (c.verdict === "osäker konsensus") return "osäker konsensus";
  return c.verdict === "i linje" ? "i linje med förväntan" : `${signed(c.surprise_pct, 1)} % mot förväntan`;
}

/** Förväntat belopp i samma skala som utfallet: per aktie i kr, omsättning i mn/mdr. */
export function expectedText(c: Comparison, perShare: boolean): string {
  const unit = c.currency === "SEK" ? "kr" : c.currency;
  if (perShare) return `${nf.format(Math.round(c.expected * 100) / 100)} ${unit}`;
  const abs = Math.abs(c.expected);
  if (abs >= 1e9) return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 1 }).format(c.expected / 1e9)} mdr ${unit}`;
  return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(c.expected / 1e6)} mn ${unit}`;
}
