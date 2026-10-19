/**
 * Visningstexter för rapportkalendern (scripts/report_calendar.py).
 * Ren modul (testas med node --test).
 */
import { shortDate } from "./format.ts";

export type CalendarStatus = "bekräftat" | "avvikelse" | "yahoo" | "mfn";

export interface CalendarEvent {
  date: string;
  kind: "rapport" | "stämma";
  ticker: string;
  name: string;
  /** Bolagets sektor (saknas i äldre kalenderfiler). */
  sector?: string | null;
  status: CalendarStatus;
  yahoo_date: string | null;
  mfn_date: string | null;
  mfn_url: string | null;
}

const WEEKDAYS = ["söndag", "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag"];

/** "2026-10-22" -> "Torsdag 22 okt". */
export function weekdayDate(iso: string): string {
  const day = WEEKDAYS[new Date(`${iso}T12:00:00Z`).getUTCDay()];
  return `${day[0].toUpperCase()}${day.slice(1)} ${shortDate(iso)}`;
}

/** Statusens text: "bekräftat av MFN", "olika datum: Yahoo 21 okt, MFN 23 okt", "enligt Yahoo", "enligt MFN". */
export function statusText(e: Pick<CalendarEvent, "status" | "yahoo_date" | "mfn_date">): string {
  switch (e.status) {
    case "bekräftat":
      return "bekräftat av MFN";
    case "avvikelse":
      return `olika datum: Yahoo ${shortDate(e.yahoo_date!)}, MFN ${shortDate(e.mfn_date!)}`;
    case "yahoo":
      return "enligt Yahoo";
    case "mfn":
      return "enligt MFN";
  }
}

/** Händelserna grupperade per dag, i datumordning. */
export function byDay<T extends { date: string }>(events: T[]): { date: string; events: T[] }[] {
  const days = new Map<string, T[]>();
  for (const e of [...events].sort((a, b) => a.date.localeCompare(b.date))) {
    days.set(e.date, [...(days.get(e.date) ?? []), e]);
  }
  return [...days].map(([date, evs]) => ({ date, events: evs }));
}
