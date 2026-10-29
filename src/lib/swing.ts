/**
 * Visningstexter för fliken Swing (scripts/swing.py, scripts/swing_history.py). Ren modul (testas med node --test).
 * Etiketterna är beskrivande; inga ord som uppmanar till köp eller försäljning.
 */

/** Under så många fall visas historiken som "för få fall". */
export const MIN_CASES = 30;

/** Etikettens färgklass: utbrott, RSI, trend eller rapport. */
export function labelClass(label: string): string {
  if (label.startsWith("utbrott")) return "breakout";
  if (label.startsWith("rsi2")) return "rsi";
  if (label.startsWith("trend")) return "trend";
  return "report";
}

/** Antal bolag per etikett, i etiketternas ordning. */
export function labelCounts(rows: { labels: string[] }[], order: string[]): { label: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const r of rows) for (const l of r.labels) counts.set(l, (counts.get(l) ?? 0) + 1);
  return order.map((label) => ({ label, count: counts.get(label) ?? 0 }));
}

const pctFmt = new Intl.NumberFormat("sv-SE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/**
 * Andel fall bättre än index: "49,3 % (±3,6)", med "för få fall" under MIN_CASES och "–" utan fall.
 */
export function shareText(s: { n: number; better: number | null; ci: number | null } | undefined): string {
  if (!s || s.n === 0 || s.better === null) return "–";
  const share = `${pctFmt.format(s.better * 100)} %`;
  if (s.n < MIN_CASES) return `${share} (för få fall)`;
  return s.ci === null ? share : `${share} (±${pctFmt.format(s.ci * 100)})`;
}

/** Skillnad mot alla dagar i procentenheter: "+2,0 pe", "−0,1 pe"; "–" utan underlag eller vid för få fall. */
export function vsBaseText(s: { n: number; better: number | null } | undefined, base: { better: number | null } | undefined): string {
  if (!s || !base || s.better === null || base.better === null || s.n < MIN_CASES) return "–";
  const d = (s.better - base.better) * 100;
  return `${new Intl.NumberFormat("sv-SE", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" }).format(d)} pe`;
}

/** "3 dagar sedan (över förväntan)", "i dag", "–". */
export function reportText(days: number | null, verdict: string | null): string {
  if (days === null) return "–";
  const when = days === 0 ? "reaktionsdag" : days === 1 ? "1 dag sedan" : `${days} dagar sedan`;
  return verdict === "över" || verdict === "under" ? `${when} (${verdict} förväntan)` : when;
}
