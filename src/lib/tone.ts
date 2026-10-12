/**
 * Nyhetens ton jämfört med veckans kursrörelse. Ren modul (testas med node --test).
 * "Avviker" säger bara att de går åt olika håll – inget samband är fastställt.
 */

export type Tone = "positiv" | "negativ" | "neutral";

/** Positiv nyhet men sjunkande kurs, eller negativ nyhet men stigande kurs. Neutral avviker aldrig. */
export function divergesFromPrice(tone: Tone | undefined, quote: { change_pct: number } | null): boolean {
  if (!tone || !quote) return false;
  return (tone === "positiv" && quote.change_pct < 0) || (tone === "negativ" && quote.change_pct > 0);
}
