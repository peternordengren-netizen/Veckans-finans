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
  /** Bolaget hade redan rapporterat när bilden togs – siffrorna visas inte (saknas i äldre filer). */
  after_report?: boolean;
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

/** Över så stor förväntad förändring (±procent) och med färre än MIN_ANALYSTS analytiker varnas det. */
export const BIG_CHANGE_PCT = 50;

/**
 * Förväntad förändring mot samma kvartal i fjol i procent, eller null om den saknar mening:
 * fjolåret saknas, är noll eller har annat tecken än förväntan (t.ex. från förlust till vinst).
 */
export function expectedChange(e: Estimate): number | null {
  const ya = e.year_ago;
  if (ya === null || ya === 0 || Math.sign(ya) !== Math.sign(e.avg)) return null;
  return ((e.avg - ya) / Math.abs(ya)) * 100;
}

const signedPct = (v: number) =>
  `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0, signDisplay: "exceptZero" }).format(v)} %`;

/** Över så stor förändring (±procent) visas fjolårets värde i stället för en svårläst procentsats. */
export const MAX_SHOWN_PCT = 200;

/**
 * "2,37 kr (+25 % mot fjol, 4 analytiker)". Går förändringen inte att uttrycka i procent
 * (tecknet byts, fjolåret är noll) eller är den större än ±MAX_SHOWN_PCT % visas fjolårets
 * värde: "0,40 kr (i fjol −0,20 kr, 2 analytiker)".
 */
export function estimateText(e: Estimate, format: (v: number, c: string | null) => string): string {
  const parts = [];
  const change = expectedChange(e);
  if (change !== null && Math.abs(change) <= MAX_SHOWN_PCT) parts.push(`${signedPct(change)} mot fjol`);
  else if (e.year_ago !== null) parts.push(`i fjol ${format(e.year_ago, e.currency)}`);
  if (e.analysts !== null) parts.push(`${e.analysts} analytiker`);
  return parts.length ? `${format(e.avg, e.currency)} (${parts.join(", ")})` : format(e.avg, e.currency);
}

/** Stor förväntad förändring (över ±BIG_CHANGE_PCT %) från färre än MIN_ANALYSTS analytiker. */
export function bigChangeFewAnalysts(e: Estimate | null): boolean {
  if (e === null) return false;
  const change = expectedChange(e);
  return change !== null && Math.abs(change) > BIG_CHANGE_PCT && (e.analysts ?? 0) < MIN_ANALYSTS;
}

/**
 * Varningar som visas vid konsensus:
 * - färre än MIN_ANALYSTS analytiker för vinst per aktie (eller ingen prognos alls)
 * - bolaget redovisar i annan valuta än kronor
 * - fastighetsbolag: vinst per aktie styrs av värdeförändringar
 * - förväntad förändring över ±50 % mot fjol från färre än 3 analytiker (vinst eller omsättning)
 */
export function warnings(c: Consensus, sector: string | null | undefined): string[] {
  if (c.after_report) return ["konsensus efter rapport – visas inte"];
  const out: string[] = [];
  const n = c.eps?.analysts ?? 0;
  if (c.eps === null) out.push("ingen prognos för vinst per aktie");
  else if (n < MIN_ANALYSTS) out.push(`bara ${n} analytiker för vinst per aktie`);
  if (bigChangeFewAnalysts(c.eps) || bigChangeFewAnalysts(c.revenue)) out.push("stor förändring, få analytiker");
  const ccy = c.financial_currency ?? c.eps?.currency ?? c.revenue?.currency ?? null;
  if (ccy && ccy !== "SEK") out.push(`redovisar i ${ccy}`);
  if (sector === "fastigheter") out.push("vinst per aktie styrs av värdeförändringar – se förvaltningsresultatet");
  return out;
}
