"""Listar rapporter (delårsrapporter, bokslutskommunikéer) för bolagen i instruments.csv,
i omgångar om BATCH_SIZE, för /rapportutfall.

Två lägen ("scope"):
- vecka ("2026-W43"): veckans rapporter ur data/raw/<vecka>/ (måndagens uppsamling). Bolag
  som redan fått sitt utfall i en godkänd morgonkörning samma vecka hoppas över.
- dag ("2026-10-20"): rapporter publicerade i morgonens tidsfönster, ur både data/raw/ och
  data/morning/raw/. Fönstret sparas i data/results/morning/<datum>/window.json när det skapas
  (--skapa-fonster), så att listan och valideringen alltid räknar på samma fönster. Det börjar
  där förra handelsdagens fönster slutade (annars förra handelsdagen 08:10) och slutar när
  morgonkörningen startar.

En rapport per bolag: den första icke-rutinmässiga MFN/Cision-posten vars rubrik är en rapport
(inte en inbjudan eller ett datumbesked). Avsändaren avgörs som i rapportkalendern
(scripts/report_calendar.match_company). Varje rad visar vilka nyckeltal som ska tas fram:
sektorns nyckeltal ur data/sectors.json plus omsättning och resultat per aktie, och sökvägen
till rapporttexten.

Användning:
    python scripts/report_list.py 2026-W42                 # alla, med omgångsnummer
    python scripts/report_list.py 2026-W42 --omgang 2      # bara omgång 2
    python scripts/report_list.py 2026-10-20 --skapa-fonster --antal-omgangar
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_calendar import find_dates, match_company, name_patterns  # noqa: E402
from validate import DATA_DIR, RAW_DIR, Instrument, iso_week_period, load_instruments, load_sector_kpis  # noqa: E402
from workdays import non_business_days  # noqa: E402

STOCKHOLM = ZoneInfo("Europe/Stockholm")
MORNING_RAW = DATA_DIR / "morning" / "raw"
RESULTS_DIR = DATA_DIR / "results"
BATCH_SIZE = 20
MORNING_START = time(8, 10)  # fönstrets början om förra handelsdagen saknar fönster
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Nyckeltal som tas fram för alla bolag, utöver sektorns: de jämförs med Yahoos konsensus.
COMMON_KPIS = [
    {"id": "nettoomsattning", "name": "Nettoomsättning", "kind": "belopp"},
    {"id": "resultat-per-aktie", "name": "Resultat per aktie", "kind": "per_aktie"},
]
REPORT_RE = re.compile(
    r"delårsrapport|interim report|kvartalsrapport|bokslutskommuniké|year[- ]end report|"
    r"rapport för (det )?(första|andra|tredje|fjärde) kvartalet|"
    r"\bresultat (för )?(det )?(första|andra|tredje|fjärde) kvartalet|"
    r"(first|second|third|fourth) quarter (20\d\d )?(report|results)|\bq[1-4][ -]?(20\d\d )?(rapport|report|results)",
    re.IGNORECASE,
)
INVITE_RE = re.compile(
    r"inbjud|invitation|bjuder in|invites|telefonkonferens|conference call|webcast|presentation av|"
    r"kommer att publicera|publicerar datum|datum för|will publish",
    re.IGNORECASE,
)
# Preliminära siffror före rapporten: räknas som att bolaget redan rapporterat när en
# konsensusbild tas (scripts/consensus.py), men är ingen rapport att ta fram nyckeltal ur.
PRELIM_RE = re.compile(
    r"preliminära (siffror|resultat)|preliminärt (resultat|utfall)|preliminary (figures|results|financial)",
    re.IGNORECASE,
)
# "Rapport för tredje kvartalet och inbjudan till telefonkonferens" är själva rapporten.
REPORT_AND_INVITE_RE = re.compile(r"\boch inbjudan|\band invitation", re.IGNORECASE)


def is_report_title(title: str, published: date) -> bool:
    """Sant om rubriken är själva rapporten. "… publicerar rapport för tredje kvartalet den 21
    oktober" (ett framtida datum i rubriken) är ett datumbesked, ingen rapport. "Preliminärt
    resultat för tredje kvartalet" är preliminära siffror, ingen rapport."""
    if not REPORT_RE.search(title) or PRELIM_RE.search(title):
        return False
    if any(d > published for _, d in find_dates(title, published)):
        return False
    return not INVITE_RE.search(title) or bool(REPORT_AND_INVITE_RE.search(title))


def kpis_for(inst: Instrument, sector_kpis: dict[str, list[dict]]) -> list[dict]:
    """Bolagets nyckeltal: sektorns först, sedan omsättning och resultat per aktie."""
    own = sector_kpis.get(inst.sektor or "", [])
    return [*own, *[k for k in COMMON_KPIS if k["id"] not in {o["id"] for o in own}]]


# --- Tidsfönster för dagsläget -------------------------------------------------


def _iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def previous_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in non_business_days(d.year):
        d -= timedelta(days=1)
    return d


def window_path(day: str, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "morning" / day / "window.json"


def load_window(day: str, results_dir: Path = RESULTS_DIR) -> tuple[datetime, datetime] | None:
    p = window_path(day, results_dir)
    if not p.exists():
        return None
    w = json.loads(p.read_text(encoding="utf-8"))
    return datetime.fromisoformat(w["since"]), datetime.fromisoformat(w["until"])


def create_window(day: str, now: datetime, results_dir: Path = RESULTS_DIR) -> tuple[datetime, datetime]:
    """Skapar dagens fönster om det inte finns (ett befintligt fönster ändras aldrig)."""
    existing = load_window(day, results_dir)
    if existing:
        return existing
    prev = previous_business_day(date.fromisoformat(day)).isoformat()
    prev_window = load_window(prev, results_dir)
    since = prev_window[1] if prev_window else datetime.combine(date.fromisoformat(prev), MORNING_START, STOCKHOLM)
    p = window_path(day, results_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"since": since.isoformat(timespec="seconds"),
                             "until": now.isoformat(timespec="seconds")}) + "\n", encoding="utf-8")
    return since, now


# --- Listan ---------------------------------------------------------------------


def _rel(path: Path) -> str:
    """Sökväg relativt projektroten om möjligt (det Claude läser), annars absolut."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _morning_tickers(week: str, results_dir: Path) -> set[str]:
    """Bolag med godkänt utfall i veckans morgonkörningar (sammanslagna morgonfiler)."""
    start, _ = iso_week_period(week)
    out: set[str] = set()
    for i in range(7):
        p = results_dir / "morning" / f"{start + timedelta(days=i)}.json"
        if p.exists():
            out |= {r["ticker"] for r in json.loads(p.read_text(encoding="utf-8")).get("reports", [])}
    return out


def list_scope(scope: str, instruments: dict[str, Instrument], sector_kpis: dict[str, list[dict]],
               raw_dir: Path = RAW_DIR, morning_raw: Path | None = MORNING_RAW,
               results_dir: Path | None = RESULTS_DIR) -> list[dict]:
    """Rapporterna för en vecka eller en dag (se modulens beskrivning), en per bolag."""
    if WEEK_RE.match(scope):
        bases = [raw_dir / scope]
        window = None
        skip = _morning_tickers(scope, results_dir) if results_dir else set()
    elif DAY_RE.match(scope):
        window = load_window(scope, results_dir) if results_dir else None
        if window is None:
            return []
        weeks = sorted({_iso_week(window[0].date()), _iso_week(window[1].date())})
        bases = [b / w for w in weeks for b in (raw_dir, morning_raw) if b is not None]
        skip = set()
    else:
        raise ValueError(f"ogiltig vecka eller dag: {scope!r}")
    return _list(bases, window, skip, instruments, sector_kpis)


def list_window(since: datetime, until: datetime, instruments: dict[str, Instrument],
                sector_kpis: dict[str, list[dict]], raw_dir: Path = RAW_DIR,
                morning_raw: Path | None = MORNING_RAW, prelim: bool = False) -> list[dict]:
    """Rapporter publicerade i (since, until] ur båda rådatamapparna, utan sparat fönster
    (används t.ex. för att se vilka bolag som rapporterat före en konsensusbild).
    prelim=True: preliminära siffror i stället för rapporter."""
    weeks, d = set(), since.date()
    while d <= until.date():
        weeks.add(_iso_week(d))
        d += timedelta(days=1)
    bases = [b / w for w in sorted(weeks) for b in (raw_dir, morning_raw) if b is not None]
    title_ok = (lambda title, _day: bool(PRELIM_RE.search(title))) if prelim else is_report_title
    return _list(bases, (since, until), set(), instruments, sector_kpis, title_ok)


def _list(bases: list[Path], window: tuple[datetime, datetime] | None, skip: set[str],
          instruments: dict[str, Instrument], sector_kpis: dict[str, list[dict]],
          title_ok=is_report_title) -> list[dict]:
    patterns = name_patterns(instruments)
    candidates: list[tuple[Path, dict]] = []
    seen_ids: set[str] = set()
    for base in bases:
        index_path = base / "index.json"
        if not index_path.exists():
            continue
        for it in json.loads(index_path.read_text(encoding="utf-8")).get("items", []):
            key = f"{it.get('source')}:{it.get('id') or it.get('url')}"
            if key in seen_ids:
                continue  # samma post i både Actions- och morgonrådatan
            seen_ids.add(key)
            candidates.append((base, it))

    seen: set[str] = set()
    out = []
    for base, it in sorted(candidates, key=lambda c: c[1]["published"]):
        published = datetime.fromisoformat(it["published"])
        if window and not window[0] < published <= window[1]:
            continue
        if it.get("source") not in ("mfn", "cision") or not title_ok(it.get("title", ""), published.date()):
            continue
        ticker = match_company(it, instruments, patterns)
        if ticker is None or ticker in seen or ticker in skip:
            continue
        seen.add(ticker)
        inst = instruments[ticker]
        out.append({
            "ticker": ticker,
            "name": inst.namn,
            "sector": inst.sektor,
            "kpis": [k["id"] for k in kpis_for(inst, sector_kpis)],
            "published": it["published"],
            "base": _rel(base),
            "raw_file": it["path"],
            "path": f"{_rel(base)}/{it['path']}",
            "url": it["url"],
            "source_name": it.get("source_name") or it["source"],
            "text_kind": it.get("text_kind"),
            "title": it["title"],
        })
    for n, r in enumerate(out):
        r["batch"] = n // BATCH_SIZE + 1
    return out


def list_reports(raw_dir: Path, week: str, instruments: dict[str, Instrument],
                 sector_kpis: dict[str, list[dict]], results_dir: Path | None = None) -> list[dict]:
    """Veckans rapporter ur raw_dir (utan morgonrådata; results_dir=None: inga hoppas över)."""
    return list_scope(week, instruments, sector_kpis, raw_dir, None, results_dir)


def report_path(entry: dict) -> Path:
    """Rapporttextens sökväg för en rad ur listan."""
    base = Path(entry["base"])
    return (base if base.is_absolute() else ROOT / base) / entry["raw_file"]


def batches(reports: list[dict]) -> int:
    return max((r["batch"] for r in reports), default=0)


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("scope", help="vecka (2026-W43) eller dag (2026-10-20)")
    p.add_argument("--omgang", type=int)
    p.add_argument("--antal-omgangar", action="store_true")
    p.add_argument("--skapa-fonster", action="store_true", help="dagsläge: skapa dagens tidsfönster om det saknas")
    args = p.parse_args(argv)
    if not (WEEK_RE.match(args.scope) or DAY_RE.match(args.scope)):
        print(f"ogiltig vecka eller dag: {args.scope!r}", file=sys.stderr)
        return 1
    if args.skapa_fonster and DAY_RE.match(args.scope):
        create_window(args.scope, now or datetime.now(STOCKHOLM))
    reports = list_scope(args.scope, load_instruments(), load_sector_kpis())
    if args.antal_omgangar:
        print(batches(reports))
        return 0
    chosen = [r for r in reports if args.omgang is None or r["batch"] == args.omgang]
    label = "Vecka" if WEEK_RE.match(args.scope) else "Dag"
    print(f"{label} {args.scope}: {len(reports)} rapporter i {batches(reports)} omgångar"
          + (f", omgång {args.omgang}: {len(chosen)}" if args.omgang else ""))
    print("nr | omgång | ticker | bolag | sektor | nyckeltal | publicerad | text | raw_file | sökväg | rubrik")
    for n, r in enumerate(reports, start=1):
        if r in chosen:
            print(f"{n} | {r['batch']} | {r['ticker']} | {r['name']} | {r['sector']} | {', '.join(r['kpis'])} | "
                  f"{r['published'][:16]} | {r['text_kind']} | {r['raw_file']} | {r['path']} | {r['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
