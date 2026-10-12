/**
 * Läser veckofiler, kursfiler och sektorlistan vid byggtid.
 *
 * Läge "mock" (astro dev/build --mode mock) läser data/mock/, annars data/weeks/
 * och data/prices/. Rådata och evidence-fältet läses aldrig in i sidan:
 * toWeekView plockar bara ut de fält som visas.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const DATA = join(process.cwd(), "data");
const IS_MOCK = import.meta.env.MODE === "mock";
const WEEKS_DIR = IS_MOCK ? join(DATA, "mock", "weeks") : join(DATA, "weeks");
const PRICES_DIR = IS_MOCK ? join(DATA, "mock", "prices") : join(DATA, "prices");
const ANALYSIS_DIR = IS_MOCK ? join(DATA, "mock", "analysis") : join(DATA, "analysis");
const WEEK_RE = /^\d{4}-W\d{2}$/;

export type Impact = "direkt" | "indirekt";
export type Direction = "positiv" | "negativ" | "blandad" | "oklar";

export interface Sector {
  id: string;
  name: string;
}

export interface Quote {
  change_pct: number;
  close: number;
  currency: string;
  /** Skillnad mot index i procentenheter; null/saknas om ingen jämförelse finns. */
  relative_pp?: number | null;
}

export interface IndexQuote {
  ticker: string;
  name: string;
  change_pct: number;
}

export interface ListedCompany {
  name: string;
  ticker: string;
  exchange: string;
  impact: Impact;
  rationale: string;
  quote: Quote | null;
}

export interface NotInListCompany {
  name: string;
  impact: Impact;
  rationale: string;
}

export interface SectorImpact {
  sector: Sector;
  direction: Direction;
  rationale: string;
}

import type { Tone } from "./tone";
export type { Tone } from "./tone";

export interface Sentiment {
  label: Tone;
  rationale: string;
}

export interface ItemView {
  id: string;
  sentiment: Sentiment | null;
  headline: string;
  summary: string;
  published: string;
  sourceName: string;
  sourceUrl: string;
  listed: ListedCompany[];
  notInList: NotInListCompany[];
  impacts: SectorImpact[];
}

export interface SectorView {
  sector: Sector;
  summary: string;
  items: ItemView[];
}

export interface PolicyRate {
  value: number;
  date: string;
  previousValue: number | null;
  changedOn: string | null;
  sourceUrl: string;
}

export interface WeekView {
  week: string;
  start: string;
  end: string;
  mock: boolean;
  hasPrices: boolean;
  /** Jämförelseindex för veckan (ur kursfilen), om det kunde hämtas. */
  index: IndexQuote | null;
  policyRate: PolicyRate | null;
  analysis: Analysis | null;
  sectors: SectorView[];
}

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

export function loadSectors(): Sector[] {
  return readJson<Sector[]>(join(DATA, "sectors.json"));
}

/** Tillgängliga veckor, nyast först. */
export function listWeeks(): string[] {
  if (!existsSync(WEEKS_DIR)) return [];
  return readdirSync(WEEKS_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.slice(0, -5))
    .filter((w) => WEEK_RE.test(w))
    .sort()
    .reverse();
}

// Blanknings- och insynsanalys (scripts/registers.py, schema/analysis.schema.json).
export interface ShortChange {
  ticker: string;
  name: string;
  start_pct: number;
  end_pct: number;
  change_pp: number;
  holders?: { holder: string; start_pct: number; end_pct: number; change_pp: number }[];
}
export interface ShortBlock {
  available: boolean;
  note: string | null;
  start_as_of: string | null;
  end_as_of: string | null;
  changes: ShortChange[];
}
export interface InsiderTransaction {
  person: string;
  position: string;
  closely_associated: string;
  side: "köp" | "försäljning";
  transaction_date: string;
  published_date: string;
  volume: number;
  price: number;
  value_sek: number;
  /** Utanför handelsplats enligt FI – ingår i summorna men markeras (saknas i äldre filer). */
  off_exchange?: boolean;
}
export interface InsiderCompany {
  ticker: string;
  name: string;
  buy_value_sek: number;
  sell_value_sek: number;
  net_value_sek: number;
  buyers: string[];
  sellers: string[];
  cluster_buy: boolean;
  cluster_sell: boolean;
  /** Målbolag för uppköpsbud/avnotering enligt veckans nyheter (saknas i äldre filer). */
  under_offer?: boolean;
  transactions: InsiderTransaction[];
}
export interface Analysis {
  week: string;
  top_n: number;
  short_positions: ShortBlock;
  short_aggregate: ShortBlock;
  insider: {
    threshold_sek: number;
    cluster_min_persons: number;
    days_covered: string[];
    days_missing: string[];
    companies: InsiderCompany[];
  };
}

/** Analysfilen är valfri – saknas den, eller är den trasig, visas ingen flik för den. */
export function loadAnalysis(week: string): Analysis | null {
  const path = join(ANALYSIS_DIR, `${week}.json`);
  if (!existsSync(path)) return null;
  try {
    return readJson<Analysis>(path);
  } catch (err) {
    console.warn(`[veckans-finans] kunde inte läsa ${path}, visar sidan utan blankning/insyn:`, err);
    return null;
  }
}

/** Kursfilen är valfri – saknas den, eller är den trasig, visas sidan utan kurser. */
function loadPrices(week: string): { quotes: Record<string, Quote>; index: IndexQuote | null } | null {
  const path = join(PRICES_DIR, `${week}.json`);
  if (!existsSync(path)) return null;
  try {
    const data = readJson<{ quotes: Record<string, Quote>; index?: IndexQuote }>(path);
    return data.quotes ? { quotes: data.quotes, index: data.index ?? null } : null;
  } catch (err) {
    console.warn(`[veckans-finans] kunde inte läsa ${path}, visar sidan utan kurser:`, err);
    return null;
  }
}

// Rå struktur enligt schema/week.schema.json – bara de fält sidan använder.
interface RawCompany {
  name: string;
  match: "matchad" | "ej i listan";
  ticker: string | null;
  yahoo_ticker: string | null;
  exchange: string | null;
  impact: Impact;
  rationale: string;
}
interface RawItem {
  id: string;
  headline: string;
  summary: string;
  published: string;
  source: { name: string; url: string };
  companies: RawCompany[];
  sector_impacts: { sector: string; direction: Direction; rationale: string }[];
  sentiment?: { label: Tone; rationale: string; basis: number[] };
}
interface RawWeek {
  week: string;
  period: { start: string; end: string };
  mock?: boolean;
  key_figures?: {
    policy_rate?: {
      value: number;
      date: string;
      previous_value: number | null;
      changed_on: string | null;
      source_url: string;
    };
  };
  sectors: { id: string; summary: string; items: RawItem[] }[];
}

export function loadWeek(week: string): WeekView {
  const raw = readJson<RawWeek>(join(WEEKS_DIR, `${week}.json`));
  if (!IS_MOCK && raw.mock) {
    // Extra spärr utöver validate.py: exempeldata får aldrig publiceras.
    throw new Error(`${week}.json är markerad som mock men ligger i data/weeks/`);
  }

  const sectors = loadSectors();
  const byId = new Map(sectors.map((s) => [s.id, s]));
  const sectorOf = (id: string): Sector => byId.get(id) ?? { id, name: id };
  const prices = loadPrices(week);
  const quotes = prices?.quotes ?? null;

  const toItem = (it: RawItem): ItemView => ({
    id: it.id,
    // basis (citatindex) används bara av valideringen; evidence läses aldrig in i sidan.
    sentiment: it.sentiment ? { label: it.sentiment.label, rationale: it.sentiment.rationale } : null,
    headline: it.headline,
    summary: it.summary,
    published: it.published,
    sourceName: it.source.name,
    sourceUrl: it.source.url,
    listed: it.companies
      .filter((c) => c.match === "matchad" && c.ticker)
      .map((c) => ({
        name: c.name,
        ticker: c.ticker!,
        exchange: c.exchange ?? "",
        impact: c.impact,
        rationale: c.rationale,
        quote: (c.yahoo_ticker && quotes?.[c.yahoo_ticker]) || null,
      })),
    notInList: it.companies
      .filter((c) => c.match === "ej i listan")
      .map((c) => ({ name: c.name, impact: c.impact, rationale: c.rationale })),
    impacts: it.sector_impacts.map((s) => ({
      sector: sectorOf(s.sector),
      direction: s.direction,
      rationale: s.rationale,
    })),
  });

  // Flikordningen följer sectors.json, inte filens ordning.
  const order = new Map(sectors.map((s, i) => [s.id, i]));
  const sectorViews = raw.sectors
    .map((s) => ({ sector: sectorOf(s.id), summary: s.summary, items: s.items.map(toItem) }))
    .sort((a, b) => (order.get(a.sector.id) ?? 99) - (order.get(b.sector.id) ?? 99));

  const pr = raw.key_figures?.policy_rate;
  return {
    week: raw.week,
    start: raw.period.start,
    end: raw.period.end,
    mock: Boolean(raw.mock),
    hasPrices: quotes !== null,
    index: prices?.index ?? null,
    policyRate: pr
      ? {
          value: pr.value,
          date: pr.date,
          previousValue: pr.previous_value,
          changedOn: pr.changed_on,
          sourceUrl: pr.source_url,
        }
      : null,
    analysis: loadAnalysis(week),
    sectors: sectorViews,
  };
}

export function weekLabel(week: string): string {
  const [year, w] = week.split("-W");
  return `Vecka ${Number(w)}, ${year}`;
}

export function formatDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("sv-SE", { day: "numeric", month: "long" });
}
