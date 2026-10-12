/**
 * Visningstexter för procentjämförelser – utan "pe"/"procentenheter" på sidan.
 * Ren modul (testas med node --test). Bara visning; datan är oförändrad.
 */

const nf = (min: number, max: number, sign = false) =>
  new Intl.NumberFormat("sv-SE", {
    minimumFractionDigits: min,
    maximumFractionDigits: max,
    ...(sign ? { signDisplay: "exceptZero" as const } : {}),
  });

/** 2.2 -> "2,2", 0.68 -> "0,68", 2 -> "2,0" */
export function pct(value: number): string {
  return nf(1, 2).format(value);
}

/**
 * Skillnad mot index (data: procentenheter, en decimal):
 * -5.3 -> "5,3 % sämre än index", 2.1 -> "2,1 % bättre än index", 0.0 -> "i linje med index".
 */
export function relativeToIndex(relativePp: number): string {
  const rounded = Math.round(relativePp * 10) / 10;
  if (rounded === 0) return "i linje med index";
  const abs = nf(1, 1).format(Math.abs(rounded));
  return rounded > 0 ? `${abs} % bättre än index` : `${abs} % sämre än index`;
}

/**
 * Blankningsandel från och till, med förändringen inom parentes:
 *   1.1 -> 3.3            "1,1 % → 3,3 % av aktierna (+2,2)"
 * Under rapportgränsen (värdet 0 i datan) skrivs som "under <gräns> %":
 *   0 -> 1.2 (bolag)      "under 0,5 % → 1,2 % av aktierna (+1,2)"
 *   1.05 -> 0             "1,05 % → under 0,5 % av aktierna (−1,05)"
 * Ny innehavare (newHolder och start 0):  "ny position 0,6 % av aktierna"
 */
export function shortRange(
  start: number,
  end: number,
  change: number,
  opts: { threshold: number; newHolder?: boolean },
): string {
  const t = `under ${pct(opts.threshold)} %`;
  if (opts.newHolder && start === 0) return `ny position ${pct(end)} % av aktierna`;
  const from = start === 0 ? t : `${pct(start)} %`;
  const to = end === 0 ? t : `${pct(end)} %`;
  return `${from} → ${to} av aktierna (${nf(1, 2, true).format(change)})`;
}
