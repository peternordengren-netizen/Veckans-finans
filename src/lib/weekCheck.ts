/**
 * Kontroll av om senaste veckan saknas, så att en misslyckad eller utebliven automatisk
 * körning syns direkt på sidan.
 *
 * Körs i webbläsaren när sidan öppnas, inte vid bygget: om måndagens körning aldrig blev av
 * byggs sidan inte heller om, och då måste kontrollen ändå slå till.
 */

/** ISO-vecka ("2026-W42") för ett kalenderdatum. */
export function isoWeek(year: number, month: number, day: number): string {
  const d = new Date(Date.UTC(year, month - 1, day));
  const weekday = d.getUTCDay() || 7; // måndag = 1 … söndag = 7
  d.setUTCDate(d.getUTCDate() + 4 - weekday); // torsdagen i samma vecka avgör året
  const isoYear = d.getUTCFullYear();
  const week = Math.ceil(((d.getTime() - Date.UTC(isoYear, 0, 1)) / 86_400_000 + 1) / 7);
  return `${isoYear}-W${String(week).padStart(2, "0")}`;
}

/** Förra ISO-veckan räknat från nu i Europe/Stockholm. */
export function previousWeek(now: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Stockholm",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => Number(parts.find((p) => p.type === type)!.value);
  const weekAgo = new Date(Date.UTC(get("year"), get("month") - 1, get("day") - 7));
  return isoWeek(weekAgo.getUTCFullYear(), weekAgo.getUTCMonth() + 1, weekAgo.getUTCDate());
}

/**
 * Varningstext om senaste veckan är äldre än förra veckan, annars null.
 * Veckosträngarna har fast format och kan jämföras som text.
 */
export function missingWeekWarning(latest: string | null, now: Date): string | null {
  const expected = previousWeek(now);
  if (latest !== null && latest >= expected) return null;
  return `Vecka ${Number(expected.split("-W")[1])} saknas – se logs/weekly/`;
}
