"""Listar rapporter (delårsrapporter, bokslutskommunikéer) för bolagen i instruments.csv,
i omgångar om BATCH_SIZE, för /rapportutfall.

Tre lägen ("scope"):
- vecka ("2026-W43"): veckans rapporter ur data/raw/<vecka>/ (måndagens uppsamling). Bolag
  som redan fått sitt utfall i en godkänd morgon- eller uppdateringskörning samma vecka hoppas över.
- dag ("2026-10-20"): morgonkörningen, rapporter publicerade i dess tidsfönster, ur både
  data/raw/ och data/morning/raw/. Fönstret sparas i data/results/morning/<datum>/window.json.
- uppdatering ("2026-10-20T1745"): eftermiddagsuppdateringen 17:45 eller "Uppdatera nu", med
  fönstret i data/results/updates/<läge>/window.json. Flera uppdateringar per dag går bra.
Ett fönster sparas när det skapas (--skapa-fonster) och ändras aldrig, så att listan och
valideringen alltid räknar på samma fönster. Det börjar där det senast slutande fönstret
(morgon eller uppdatering, från förra handelsdagen till och med dagen) slutade, annars förra
handelsdagen 08:10, och slutar när körningen startar. Därmed räknas ingen rapport två gånger,
oavsett i vilken ordning körningarna sker. Bolag som redan fått ett godkänt utfall i en annan
körning från förra handelsdagen till och med dagen hoppas över (en rapport som publiceras om).

En rapport per bolag: den första icke-rutinmässiga MFN/Cision-posten vars rubrik är en rapport
(inte en inbjudan eller ett datumbesked). Avsändaren avgörs som i rapportkalendern
(scripts/report_calendar.match_company). Varje rad visar vilka nyckeltal som ska tas fram:
sektorns nyckeltal ur data/sectors.json plus omsättning och resultat per aktie, och sökvägen
till rapporttexten.

Användning:
    python scripts/report_list.py 2026-W42                 # alla, med omgångsnummer
    python scripts/report_list.py 2026-W42 --omgang 2      # bara omgång 2
    python scripts/report_list.py 2026-10-20 --skapa-fonster --antal-omgangar
    python scripts/report_list.py 2026-10-20T1745 --skapa-fonster --antal-omgangar
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
UPDATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{4}$")


def is_run(scope: str) -> bool:
    """Sant för en körning med eget tidsfönster: morgon (datum) eller uppdatering (datumThhmm)."""
    return bool(DAY_RE.match(scope) or UPDATE_RE.match(scope))


def run_dir(scope: str, results_dir: Path = RESULTS_DIR) -> Path:
    """Katalogen med en körnings fönster och omgångar."""
    return results_dir / ("updates" if UPDATE_RE.match(scope) else "morning") / scope


def run_output(scope: str, results_dir: Path = RESULTS_DIR) -> Path:
    """Den sammanslagna filen för en körning (data/results/morning|updates/<läge>.json)."""
    d = run_dir(scope, results_dir)
    return d.parent / f"{scope}.json"


def runs_on(day: date, results_dir: Path = RESULTS_DIR) -> list[str]:
    """Dagens körningar med fönster eller sammanslagen fil: morgonen först, sedan uppdateringarna."""
    out = [day.isoformat()] if (results_dir / "morning" / day.isoformat()).exists() or \
        (results_dir / "morning" / f"{day.isoformat()}.json").exists() else []
    updates = results_dir / "updates"
    if updates.exists():
        out += sorted({p.name.removesuffix(".json") for p in updates.glob(f"{day.isoformat()}T*")
                       if UPDATE_RE.match(p.name.removesuffix(".json"))})
    return out

# Nyckeltal som tas fram för alla bolag, utöver sektorns: de jämförs med Yahoos konsensus.
COMMON_KPIS = [
    {"id": "nettoomsattning", "name": "Nettoomsättning", "kind": "belopp"},
    {"id": "resultat-per-aktie", "name": "Resultat per aktie", "kind": "per_aktie"},
]
REPORT_RE = re.compile(
    r"delårsrapport|interim report|kvartalsrapport|bokslutskommuniké|year[- ]end report|"
    r"rapport för (det )?(första|andra|tredje|fjärde) kvartalet|"
    # "Resultat tredje kvartalet 2026", "Tele2 rapporterar resultat för …", "Bolaget: Resultat för …",
    # "SEB:s resultat för …" – men inte "bedömer att omsättning och resultat för tredje kvartalet
    # överstiger …" (resultatvarning).
    r"(^|\brapporterar |:s? ?)resultat (för )?(det )?(första|andra|tredje|fjärde) kvartalet|"
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


def window_path(scope: str, results_dir: Path = RESULTS_DIR) -> Path:
    return run_dir(scope, results_dir) / "window.json"


def load_window(scope: str, results_dir: Path = RESULTS_DIR) -> tuple[datetime, datetime] | None:
    p = window_path(scope, results_dir)
    if not p.exists():
        return None
    w = json.loads(p.read_text(encoding="utf-8"))
    return datetime.fromisoformat(w["since"]), datetime.fromisoformat(w["until"])


def latest_window_end(day: date, results_dir: Path = RESULTS_DIR, exclude: str | None = None) -> datetime | None:
    """Senaste slut bland alla fönster (morgon och uppdateringar) från förra handelsdagen till och
    med day, utom exclude."""
    ends = []
    d = previous_business_day(day)
    while d <= day:
        for scope in runs_on(d, results_dir):
            w = load_window(scope, results_dir) if scope != exclude else None
            if w:
                ends.append(w[1])
        d += timedelta(days=1)
    return max(ends, default=None)


def create_window(scope: str, now: datetime, results_dir: Path = RESULTS_DIR) -> tuple[datetime, datetime]:
    """Skapar körningens fönster om det inte finns (ett befintligt fönster ändras aldrig). Det
    börjar där det senast slutande fönstret slutade (se modulens beskrivning)."""
    existing = load_window(scope, results_dir)
    if existing:
        return existing
    day = date.fromisoformat(scope[:10])
    since = latest_window_end(day, results_dir, exclude=scope) or \
        datetime.combine(previous_business_day(day), MORNING_START, STOCKHOLM)
    p = window_path(scope, results_dir)
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


def week_run_files(week: str, results_dir: Path = RESULTS_DIR) -> list[Path]:
    """Veckans sammanslagna filer från morgon- och uppdateringskörningar, i tidsordning."""
    start, _ = iso_week_period(week)
    out = []
    for i in range(7):
        for scope in runs_on(start + timedelta(days=i), results_dir):
            p = run_output(scope, results_dir)
            if p.exists():
                out.append(p)
    return out


def _recent_run_tickers(scope: str, results_dir: Path) -> set[str]:
    """Bolag med godkänt utfall i en annan körning från förra handelsdagen till och med dagen.
    En rapport som publiceras om (t.ex. Castellum 2026-10-22 08:00 och 08:25 med ny adress) ska
    inte få ett andra utfall i nästa körning."""
    day = date.fromisoformat(scope[:10])
    out: set[str] = set()
    d = previous_business_day(day)
    while d <= day:
        for other in runs_on(d, results_dir):
            p = run_output(other, results_dir)
            if other != scope and p.exists():
                out |= {r["ticker"] for r in json.loads(p.read_text(encoding="utf-8")).get("reports", [])}
        d += timedelta(days=1)
    return out


def _morning_tickers(week: str, results_dir: Path) -> set[str]:
    """Bolag med godkänt utfall i veckans morgon- och uppdateringskörningar (sammanslagna filer)."""
    out: set[str] = set()
    for p in week_run_files(week, results_dir):
        out |= {r["ticker"] for r in json.loads(p.read_text(encoding="utf-8")).get("reports", [])}
    return out


def list_scope(scope: str, instruments: dict[str, Instrument], sector_kpis: dict[str, list[dict]],
               raw_dir: Path = RAW_DIR, morning_raw: Path | None = MORNING_RAW,
               results_dir: Path | None = RESULTS_DIR) -> list[dict]:
    """Rapporterna för en vecka eller en körning (se modulens beskrivning), en per bolag."""
    if WEEK_RE.match(scope):
        bases = [raw_dir / scope]
        window = None
        skip = _morning_tickers(scope, results_dir) if results_dir else set()
    elif is_run(scope):
        window = load_window(scope, results_dir) if results_dir else None
        if window is None:
            return []
        weeks = sorted({_iso_week(window[0].date()), _iso_week(window[1].date())})
        bases = [b / w for w in weeks for b in (raw_dir, morning_raw) if b is not None]
        skip = _recent_run_tickers(scope, results_dir)
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
    p.add_argument("scope", help="vecka (2026-W43), dag (2026-10-20) eller uppdatering (2026-10-20T1745)")
    p.add_argument("--omgang", type=int)
    p.add_argument("--antal-omgangar", action="store_true")
    p.add_argument("--skapa-fonster", action="store_true", help="dag/uppdatering: skapa tidsfönstret om det saknas")
    args = p.parse_args(argv)
    if not (WEEK_RE.match(args.scope) or is_run(args.scope)):
        print(f"ogiltig vecka, dag eller uppdatering: {args.scope!r}", file=sys.stderr)
        return 1
    if args.skapa_fonster and is_run(args.scope):
        create_window(args.scope, now or datetime.now(STOCKHOLM))
    reports = list_scope(args.scope, load_instruments(), load_sector_kpis())
    if args.antal_omgangar:
        print(batches(reports))
        return 0
    chosen = [r for r in reports if args.omgang is None or r["batch"] == args.omgang]
    label = "Vecka" if WEEK_RE.match(args.scope) else "Uppdatering" if UPDATE_RE.match(args.scope) else "Dag"
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
