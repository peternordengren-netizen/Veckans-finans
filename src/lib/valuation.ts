/**
 * Visningstexter för fliken "Kurs mot vinst" (scripts/valuation.py).
 * Ren modul (testas med node --test).
 */

export type ValuationStatus =
  | "ok"
  | "kontrollera bolagshändelse"
  | "känd bolagshändelse"
  | "fastighetsbolag"
  | "investmentbolag"
  | "annan valuta"
  | "otillräcklig vinsthistorik"
  | "förlust"
  | "kurs saknas";

export interface ValuationRow {
  ticker: string;
  name: string;
  sector: string | null;
  financial_currency: string | null;
  ytd_pct: number | null;
  rel_index_pp: number | null;
  eps_ttm_start: number | null;
  eps_ttm_now: number | null;
  eps_change_pct: number | null;
  pe_start: number | null;
  pe_now: number | null;
  pe_change_pct: number | null;
  pe_over_max: boolean;
  verdict: "kursen före vinsten" | "vinsten före kursen" | "i takt" | null;
  big_moves: { date: string; pct: number }[];
  status: ValuationStatus;
  /** Känd bolagshändelse som inte går att justera, t.ex. "noterad i Stockholm 9 jan" (saknas i äldre filer). */
  event_label?: string | null;
}

const nf = (digits: number) =>
  new Intl.NumberFormat("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const signed = (v: number, digits: number) =>
  new Intl.NumberFormat("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: "exceptZero" }).format(v);

/** "4,00 → 4,50 kr" (vinst per aktie rullande 12 mån), "–" om något saknas. */
export function epsPair(r: Pick<ValuationRow, "eps_ttm_start" | "eps_ttm_now" | "financial_currency">): string {
  if (r.eps_ttm_start === null || r.eps_ttm_now === null) return "–";
  const unit = !r.financial_currency || r.financial_currency === "SEK" ? "kr" : r.financial_currency;
  return `${nf(2).format(r.eps_ttm_start)} → ${nf(2).format(r.eps_ttm_now)} ${unit}`;
}

/** Vinstförändring: "+12 %", eller "–" om den inte visas (förlust, över ±200 %). */
export function epsChange(r: Pick<ValuationRow, "eps_change_pct">): string {
  return r.eps_change_pct === null ? "–" : `${signed(r.eps_change_pct, 0)} %`;
}

/** "25,0 → 28,9", "över 100" om något av talen överstiger gränsen, annars "–". */
export function pePair(r: Pick<ValuationRow, "pe_start" | "pe_now" | "pe_over_max">, peMax = 100): string {
  if (r.pe_start === null || r.pe_now === null) return "–";
  const show = (v: number) => (v > peMax ? `över ${peMax}` : nf(1).format(v));
  return `${show(r.pe_start)} → ${show(r.pe_now)}`;
}

/** Statusens förklaring när P/E inte visas. */
export const STATUS_TEXT: Record<ValuationStatus, string> = {
  ok: "",
  "kontrollera bolagshändelse": "kontrollera bolagshändelse",
  "känd bolagshändelse": "känd bolagshändelse",
  fastighetsbolag: "fastighetsbolag – se förvaltningsresultatet",
  investmentbolag: "investmentbolag – substansvärdet är måttet",
  "annan valuta": "redovisar i annan valuta",
  "otillräcklig vinsthistorik": "för kort eller ofullständig vinsthistorik",
  förlust: "förlust – ingen P/E",
  "kurs saknas": "kurs saknas",
};

/** Tolkning eller status: det som visas i sista kolumnen. */
export function interpretation(r: Pick<ValuationRow, "status" | "verdict" | "pe_over_max" | "event_label">): string {
  if (r.status === "känd bolagshändelse" && r.event_label) return r.event_label;
  if (r.status !== "ok") return STATUS_TEXT[r.status];
  if (r.pe_over_max) return "P/E över 100 – ingen tolkning";
  return r.verdict ?? "";
}
