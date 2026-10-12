/**
 * Nyhetens ton jämfört med veckans kursrörelse **mot index**. Ren modul (testas med node --test).
 * "Avviker" säger bara att de går åt olika håll – inget samband är fastställt.
 */

export type Tone = "positiv" | "negativ" | "neutral";

/**
 * Positiv nyhet men sämre än index, eller negativ nyhet men bättre än index.
 * Utan jämförelse mot index (relative_pp saknas, t.ex. aktie i annan valuta) markeras inget.
 * Neutral avviker aldrig.
 */
export function divergesFromPrice(tone: Tone | undefined, quote: { relative_pp?: number | null } | null): boolean {
  const rel = quote?.relative_pp;
  if (!tone || rel === null || rel === undefined) return false;
  return (tone === "positiv" && rel < 0) || (tone === "negativ" && rel > 0);
}
