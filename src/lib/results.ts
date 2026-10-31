/**
 * Visningstexter för "Rapporterade bolag" (scripts/results.py, data/results/<vecka>.json).
 * Ren modul (testas med node --test).
 */

export interface ResultKpi {
  id: string;
  name: string;
  value: number;
  unit: string;
  previous_value: number | null;
  change_pct: number | null;
  yoy_pct: number | null;
  period_kind: "kvartal" | "delår" | "helår";
  quote: string;
}

export interface Comparison {
  actual: number;
  expected: number;
  analysts: number | null;
  currency: string;
  surprise_pct: number;
  verdict: "över" | "i linje" | "under" | "osäker konsensus" | "bolagshändelse" | "teckenbyte" | "nära noll" | "kontrollera";
  /** Resultat per aktie: justerat eller redovisat värde jämfört med förväntan (saknas = redovisat). */
  basis?: "justerat" | "redovisat";
}

/** Mot förväntan i kursreaktionen: procent (aldrig "i linje"), källa och antal analytiker. */
export interface ReactionExpected {
  /** surpriseReaction: "−1,5 %", eller etiketten vid kontrollera, osäker konsensus, teckenbyte m.m. */
  text: string;
  /** Källan och antalet analytiker: "Yahoo, 3 analytiker". */
  source: string;
  /** Hela texten från rapportutfallen, som tooltip. */
  title: string;
  verdict: Comparison["verdict"];
}

/** Kolumnerna i kursreaktionen, om kursen gick mot utfallet och rapportens svaga punkter. */
export interface ReactionOutcome {
  /** Vinst per aktie mot förväntan, eller null. */
  vsExpected: (ReactionExpected & { basis: "justerat" | "redovisat" }) | null;
  /** Nettoomsättning mot förväntan, med samma regler som vinst per aktie, eller null. */
  revenueVsExpected: ReactionExpected | null;
  /** Redovisat resultat per aktie (fastighetsbolag: förvaltningsresultat per aktie) mot samma kvartal i fjol:
   * "+12 %", eller båda värdena vid teckenbyte, nära noll eller över ±200 %, eller "–". */
  vsLastYear: string;
  /** Tooltip: perioderna och nyckeltalet, t.ex. "Q3 2026 mot Q3 2025 · Resultat per aktie", eller null. */
  vsLastYearTitle: string | null;
  /** Sektorns huvudnyckeltal mot samma kvartal i fjol (sectorKpi), eller null. */
  sectorKpi: { name: string; text: string; title: string } | null;
  /** "Ton i rapporten": vad rapporten själv lyfter fram (citaten visas inte), eller null. */
  highlight: string | null;
  /** Rapportens ton enligt raden och dess citat, eller null (äldre filer). */
  tone: Tone | null;
  /** Över förväntan men kursen föll, eller under förväntan men kursen steg. */
  divergent: boolean;
  /** Svaga punkter (weakPoints): mer än 5 % under förväntan, nyckeltalet sämre än fjol, negativ ton. */
  weak: string[];
}

export type Tone = "positiv" | "blandad" | "neutral" | "negativ";

/** Mer än så många procent under förväntan räknas som en svag punkt. */
export const WEAK_SURPRISE_PCT = -5;
/** Sektornyckeltal där ett högre värde är sämre (kreditförluster jämförs i belopp, oavsett tecken). */
const LOWER_IS_BETTER = new Set(["kreditforluster", "belaningsgrad"]);

/** Om nyckeltalet är sämre än samma kvartal i fjol, eller null om det inte går att avgöra. */
export function worseThanLastYear(k: Pick<ResultKpi, "id" | "value" | "previous_value" | "yoy_pct">): boolean | null {
  const prev = k.previous_value;
  if (LOWER_IS_BETTER.has(k.id)) return prev === null ? null : Math.abs(k.value) > Math.abs(prev);
  if (prev !== null) return k.value < prev;
  return k.yoy_pct === null ? null : k.yoy_pct < 0;
}

/** Svaga punkter för markeringen ▼ i kursreaktionen. En bolagshändelse ger ingen jämförbar avvikelse. */
export function weakPoints(report: ReportResult | undefined, main: ResultKpi | undefined): string[] {
  if (!report) return [];
  const out: string[] = [];
  const below = (c: Comparison | null) => c !== null && c.verdict !== "bolagshändelse" && c.surprise_pct < WEAK_SURPRISE_PCT;
  const eps = report.vs_consensus?.eps ?? null;
  const revenue = report.vs_consensus?.revenue ?? null;
  if (eps && below(eps)) out.push(`${epsLabel(eps).toLowerCase()} ${pctText(eps.surprise_pct)} mot förväntan`);
  if (revenue && below(revenue)) out.push(`omsättningen ${pctText(revenue.surprise_pct)} mot förväntan`);
  if (main && worseThanLastYear(main)) out.push(`${main.name.toLowerCase()} sämre än fjol`);
  if (report.highlight?.tone === "negativ") out.push("negativ ton i rapporten");
  return out;
}

const pctText = (v: number) => `${signed(v, 1)} %`;

/** Mot förväntan i kursreaktionen: alltid procent i stället för "i linje"/"över"/"under"; övriga etiketter som i
 * surpriseShort. Källan är Yahoos konsensus sparad före rapporten. */
export function surpriseReaction(c: Comparison, perShare = true): ReactionExpected {
  const text = ["i linje", "över", "under"].includes(c.verdict) ? pctText(c.surprise_pct) : surpriseShort(c, perShare);
  const n = c.analysts;
  return {
    text,
    source: `Yahoo${n ? `, ${n} analytiker` : ""}`,
    title: `${surpriseText(c, perShare)} (Yahoos konsensus${n ? `, ${n} analytiker` : ""})`,
    verdict: c.verdict,
  };
}

/** Över så stor förändring (±procent) visas båda värdena, som i "Kommande vecka" (consensus.ts MAX_SHOWN_PCT). */
export const MAX_YOY_PCT = 200;
/** Är det ena värdet mindre än så stor andel av det andra räknas det som nära noll (samma som i jämförelsen med förväntan). */
export const NEAR_ZERO_RATIO = 0.1;

/**
 * Nyckeltalet för "Mot fjol": för fastighetsbolag förvaltningsresultat per aktie när rapporten anger det,
 * annars redovisat resultat per aktie. Bara kvartalsvärden (valideringen kräver en kvartalsangivelse).
 */
export function lastYearKpi(report: ReportResult): ResultKpi | undefined {
  const q = (id: string) => report.kpis.find((k) => k.id === id && k.period_kind === "kvartal");
  return (report.sector === "fastigheter" ? q("forvaltningsresultat-per-aktie") : undefined) ?? q("resultat-per-aktie");
}

/** "+12 %", eller båda värdena kort ("9,38 kr (1,77)") vid teckenbyte, nära noll eller över ±200 %. */
export function lastYearText(k: Pick<ResultKpi, "value" | "previous_value" | "yoy_pct" | "unit">): string {
  const prev = k.previous_value;
  if (prev === null) return k.yoy_pct === null ? "–" : `${signed(k.yoy_pct, 0)} %`;
  const both = `${kpiValue(k.value, k.unit)} (${nf.format(prev)})`;
  const [small, big] = [Math.abs(k.value), Math.abs(prev)].sort((a, b) => a - b);
  const signChange = k.value !== 0 && prev !== 0 && Math.sign(k.value) !== Math.sign(prev);
  if (signChange || (big > 0 && small < NEAR_ZERO_RATIO * big)) return both;
  const pct = k.yoy_pct ?? ((k.value - prev) / Math.abs(prev)) * 100;
  return Math.abs(pct) > MAX_YOY_PCT ? both : `${signed(pct, 0)} %`;
}

/** "Q3 2026" -> "Q3 2026 mot Q3 2025"; annars perioden som den är. */
export function periodVsLastYear(period: string): string {
  const m = /^(Q[1-4]|H[12]|FY)\s+(\d{4})$/.exec(period.trim());
  return m ? `${m[1]} ${m[2]} mot ${m[1]} ${Number(m[2]) - 1}` : period;
}

/** Nyckeltal som alla bolag har; sektorns egna står före dem i rapportutfallen (sectors.json-ordning). */
const COMMON_KPIS = new Set(["nettoomsattning", "resultat-per-aktie", "justerat-resultat-per-aktie"]);

/**
 * Sektorns huvudnyckeltal för kursreaktionen: det första av sektorns egna nyckeltal (t.ex. orderingång för
 * industri) som rapporten anger för kvartalet, utom det som redan visas under "Mot fjol". Rapportutfallens
 * nyckeltal är sorterade med sektorns först, i sectors.json-ordning.
 */
export function sectorMainKpi(report: ReportResult): ResultKpi | undefined {
  const used = lastYearKpi(report)?.id;
  return report.kpis.find((k) => !COMMON_KPIS.has(k.id) && k.id !== used && k.period_kind === "kvartal");
}

/** "−9 %" för belopp m.m., och för procenttal båda värdena: "19,9 % (16,9)". */
export function sectorKpiText(k: ResultKpi): string {
  if (k.unit === "procent") return k.previous_value === null ? `${nf.format(k.value)} %` : `${nf.format(k.value)} % (${nf.format(k.previous_value)})`;
  return lastYearText(k);
}

export function reactionOutcome(changePct: number | null, report: ReportResult | undefined): ReactionOutcome {
  const eps = report?.vs_consensus?.eps ?? null;
  const revenue = report?.vs_consensus?.revenue ?? null;
  const yoy = report ? lastYearKpi(report) : undefined;
  const main = report ? sectorMainKpi(report) : undefined;
  const divergent =
    eps !== null && changePct !== null &&
    ((eps.verdict === "över" && changePct < 0) || (eps.verdict === "under" && changePct > 0));
  return {
    vsExpected: eps ? { ...surpriseReaction(eps, true), basis: eps.basis ?? "redovisat" } : null,
    revenueVsExpected: revenue ? surpriseReaction(revenue, false) : null,
    vsLastYear: yoy ? lastYearText(yoy) : "–",
    vsLastYearTitle: yoy && report ? `${periodVsLastYear(report.period)} · ${yoy.name}` : null,
    sectorKpi:
      main && report
        ? { name: main.name, text: sectorKpiText(main), title: `${periodVsLastYear(report.period)} · ${main.name}` }
        : null,
    highlight: report?.highlight?.text ?? null,
    tone: report?.highlight?.tone ?? null,
    divergent,
    weak: weakPoints(report, main),
  };
}

/** Rubriken för jämförelsen av resultat per aktie: "Justerat resultat per aktie" eller "Resultat per aktie". */
export function epsLabel(c: Pick<Comparison, "basis">): string {
  return c.basis === "justerat" ? "Justerat resultat per aktie" : "Resultat per aktie";
}

export interface ReportResult {
  ticker: string;
  name: string;
  sector: string | null;
  published: string;
  url: string;
  source_name: string;
  period: string;
  note: string | null;
  /** "I rapporten" (saknas i äldre filer); citaten är validerade mot rapporten men visas inte. */
  highlight?: { text: string; quotes: string[]; tone?: Tone } | null;
  kpis: ResultKpi[];
  vs_consensus: {
    consensus_date: string;
    /** Varningen "stor förändring, få analytiker": ingen bedömning över/under (saknas i äldre filer). */
    uncertain?: boolean;
    /** Känd bolagshändelse under året: ingen procent mot förväntan (saknas i äldre filer). */
    corporate_event?: boolean;
    eps: Comparison | null;
    revenue: Comparison | null;
  } | null;
}

/** En rapport som underkändes av valideringen; omgångens övriga rapporter är med ändå. */
export interface RejectedReport {
  ticker: string;
  name: string;
  scope: string;
  published: string;
  url: string;
  /** Första valideringsfelet, t.ex. "nettoomsattning: värdet 2500 finns inte i citatet". */
  reason: string;
}

/** En sammanslagen rapportutfallsfil (scripts/results.py) som sidan visar. */
export interface ResultsView {
  reports: ReportResult[];
  missingBatches: number[];
  rejected: RejectedReport[];
}

const UNIT_LABELS: Record<string, string> = { SEK: "kr", TSEK: "tkr", MSEK: "mn kr", MDSEK: "mdr kr", procent: "%" };
const nf = new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 2 });
const signed = (v: number, digits: number) =>
  new Intl.NumberFormat("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: "exceptZero" }).format(v);

/** "1 683 mn kr", "2,23 kr", "11,2 %", "1 234 MEUR". */
export function kpiValue(value: number, unit: string): string {
  return `${nf.format(value)} ${UNIT_LABELS[unit] ?? unit}`;
}

/**
 * Förändring mot samma period i fjol: "+21 %", "+0,7 procentenheter" för procenttal,
 * "från vinst till förlust" när tecknet bytts (en procentsats säger då inget), annars "–".
 */
export function yoyText(k: Pick<ResultKpi, "value" | "previous_value" | "yoy_pct" | "unit">): string {
  const prev = k.previous_value;
  if (prev !== null && prev !== 0 && Math.sign(prev) !== Math.sign(k.value) && k.value !== 0) {
    return k.value < 0 ? "från vinst till förlust" : "från förlust till vinst";
  }
  if (k.unit === "procent") {
    return prev === null ? "–" : `${signed(k.value - prev, 1)} procentenheter`;
  }
  return k.yoy_pct === null ? "–" : `${signed(k.yoy_pct, 0)} %`;
}

/**
 * Utfall mot förväntan:
 * - "+4,2 % mot förväntan", eller "i linje med förväntan" inom ±2 %
 * - "osäker konsensus" (stor förändring, få analytiker) och "bolagshändelse påverkar jämförelsen":
 *   ingen procent
 * - teckenbyte och nära noll: båda värdena utan procent, som i "Kommande vecka"
 * - "kontrollera" (över ±50 % utan förklaring): båda värdena
 */
export function surpriseText(c: Comparison, perShare = true): string {
  const both = `utfall ${amountText(c.actual, c.currency, perShare)}, förväntan ${amountText(c.expected, c.currency, perShare)}`;
  switch (c.verdict) {
    case "osäker konsensus":
      return "osäker konsensus";
    case "bolagshändelse":
      return "bolagshändelse påverkar jämförelsen";
    case "teckenbyte":
    case "nära noll":
      return both;
    case "kontrollera":
      return `kontrollera: ${both}`;
    case "i linje":
      return "i linje med förväntan";
    default:
      return `${signed(c.surprise_pct, 1)} % mot förväntan`;
  }
}

/**
 * Kort form av utfall mot förväntan för kursreaktionstabellen, med samma regler som surpriseText:
 * "+4,2 %", "i linje", "osäker konsensus", "bolagshändelse", och båda värdena som
 * "−0,26 kr (förv. 0,707)" vid teckenbyte och nära noll, med "kontrollera: " före vid över ±50 %.
 */
export function surpriseShort(c: Comparison, perShare = true): string {
  const both = `${amountText(c.actual, c.currency, perShare)} (förv. ${amountText(c.expected, c.currency, perShare).replace(/ \S+$/, "")})`;
  switch (c.verdict) {
    case "osäker konsensus":
    case "bolagshändelse":
      return c.verdict;
    case "teckenbyte":
    case "nära noll":
      return both;
    case "kontrollera":
      return `kontrollera: ${both}`;
    case "i linje":
      return "i linje";
    default:
      return `${signed(c.surprise_pct, 1)} %`;
  }
}

/** Belopp i samma skala som utfallet: per aktie med två decimaler (tre under 1, så att t.ex.
 * 16,6 eurocent blir "0,166 EUR"), omsättning i mn/mdr. */
export function amountText(value: number, currency: string, perShare: boolean): string {
  const unit = currency === "SEK" ? "kr" : currency;
  if (perShare) {
    const digits = Math.abs(value) < 1 ? 3 : 2;
    return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: digits }).format(value)} ${unit}`;
  }
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 1 }).format(value / 1e9)} mdr ${unit}`;
  return `${new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(value / 1e6)} mn ${unit}`;
}

/** Förväntat belopp i samma skala som utfallet. */
export function expectedText(c: Comparison, perShare: boolean): string {
  return amountText(c.expected, c.currency, perShare);
}
