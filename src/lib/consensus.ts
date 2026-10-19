/**
 * Visningstexter för Yahoos konsensus i "Kommande vecka" (scripts/consensus.py).
 * Ren modul (testas med node --test).
 */

export interface Estimate {
  avg: number;
  low: number | null;
  high: number | null;
  analysts: number | null;
  year_ago: number | null;
  currency: string | null;
}

export interface Consensus {
  ticker: string;
  eps: Estimate | null;
  revenue: Estimate | null;
  next_report_date: string | null;
  financial_currency: string | null;
  analyst_opinions: number | null;
}

/** Under så många analytiker för vinst per aktie är konsensus tunn. */
export const MIN_ANALYSTS = 3;

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("sv-SE", { minimumFractionDigits: min, maximumFractionDigits: max });

const unit = (currency: string | null) => (currency === null || currency === "SEK" ? "kr" : currency);

/** Vinst per aktie: "5,43 kr", "2,63 USD". */
export function perShare(value: number, currency: string | null): string {
  return `${nf(2, 2).format(value)} ${unit(currency)}`;
}

/** Belopp: "18,6 mdr kr", "950 mn kr", "1,2 mdr EUR". */
export function amount(value: number, currency: string | null): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${nf(1, 1).format(value / 1e9)} mdr ${unit(currency)}`;
  if (abs >= 1e6) return `${nf(0, 0).format(value / 1e6)} mn ${unit(currency)}`;
  return `${nf(0, 0).format(value)} ${unit(currency)}`;
}

/** "5,43 kr (4 analytiker, i fjol 5,53 kr)". */
export function estimateText(e: Estimate, format: (v: number, c: string | null) => string): string {
  const parts = [];
  if (e.analysts !== null) parts.push(`${e.analysts} analytiker`);
  if (e.year_ago !== null) parts.push(`i fjol ${format(e.year_ago, e.currency)}`);
  return parts.length ? `${format(e.avg, e.currency)} (${parts.join(", ")})` : format(e.avg, e.currency);
}

/**
 * Varningar som visas vid konsensus:
 * - färre än MIN_ANALYSTS analytiker för vinst per aktie (eller ingen prognos alls)
 * - bolaget redovisar i annan valuta än kronor
 * - fastighetsbolag: vinst per aktie styrs av värdeförändringar
 */
export function warnings(c: Consensus, sector: string | null | undefined): string[] {
  const out: string[] = [];
  const n = c.eps?.analysts ?? 0;
  if (c.eps === null) out.push("ingen prognos för vinst per aktie");
  else if (n < MIN_ANALYSTS) out.push(`bara ${n} analytiker för vinst per aktie`);
  const ccy = c.financial_currency ?? c.eps?.currency ?? c.revenue?.currency ?? null;
  if (ccy && ccy !== "SEK") out.push(`redovisar i ${ccy}`);
  if (sector === "fastigheter") out.push("vinst per aktie styrs av värdeförändringar – se förvaltningsresultatet");
  return out;
}
