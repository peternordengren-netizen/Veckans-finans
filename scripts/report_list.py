"""Listar veckans rapporter (delårsrapporter, bokslutskommunikéer) för bolagen i instruments.csv,
i omgångar om BATCH_SIZE, för /rapportutfall.

En rapport per bolag och vecka: den första icke-rutinmässiga MFN/Cision-posten vars rubrik
är en rapport (inte en inbjudan till rapportpresentation). Avsändaren avgörs som i
rapportkalendern (scripts/report_calendar.match_company). Varje rad visar vilka nyckeltal
som ska tas fram: sektorns nyckeltal ur data/sectors.json plus omsättning och resultat per
aktie (som jämförs med Yahoos konsensus).

Användning:
    python scripts/report_list.py 2026-W42                # alla, med omgångsnummer
    python scripts/report_list.py 2026-W42 --omgang 2     # bara omgång 2
    python scripts/report_list.py 2026-W42 --antal-omgangar
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from datetime import date, datetime  # noqa: E402

from report_calendar import find_dates, match_company, name_patterns  # noqa: E402
from validate import RAW_DIR, Instrument, load_instruments, load_sector_kpis  # noqa: E402

BATCH_SIZE = 20
# Nyckeltal som tas fram för alla bolag, utöver sektorns: de jämförs med Yahoos konsensus.
COMMON_KPIS = [
    {"id": "nettoomsattning", "name": "Nettoomsättning", "kind": "belopp"},
    {"id": "resultat-per-aktie", "name": "Resultat per aktie", "kind": "per_aktie"},
]
REPORT_RE = re.compile(
    r"delårsrapport|interim report|kvartalsrapport|bokslutskommuniké|year[- ]end report|"
    r"rapport för (det )?(första|andra|tredje|fjärde) kvartalet|"
    r"(first|second|third|fourth) quarter (20\d\d )?(report|results)|\bq[1-4][ -]?(20\d\d )?(rapport|report|results)",
    re.IGNORECASE,
)
INVITE_RE = re.compile(
    r"inbjud|invitation|bjuder in|invites|telefonkonferens|conference call|webcast|presentation av|"
    r"kommer att publicera|publicerar datum|datum för|will publish",
    re.IGNORECASE,
)
# "Rapport för tredje kvartalet och inbjudan till telefonkonferens" är själva rapporten.
REPORT_AND_INVITE_RE = re.compile(r"\boch inbjudan|\band invitation", re.IGNORECASE)


def is_report_title(title: str, published: date) -> bool:
    """Sant om rubriken är själva rapporten. "… publicerar rapport för tredje kvartalet den 21
    oktober" (ett framtida datum i rubriken) är ett datumbesked, ingen rapport."""
    if not REPORT_RE.search(title):
        return False
    if any(d > published for _, d in find_dates(title, published)):
        return False
    return not INVITE_RE.search(title) or bool(REPORT_AND_INVITE_RE.search(title))


def kpis_for(inst: Instrument, sector_kpis: dict[str, list[dict]]) -> list[dict]:
    """Bolagets nyckeltal: sektorns först, sedan omsättning och resultat per aktie."""
    own = sector_kpis.get(inst.sektor or "", [])
    return [*own, *[k for k in COMMON_KPIS if k["id"] not in {o["id"] for o in own}]]


def list_reports(raw_dir: Path, week: str, instruments: dict[str, Instrument],
                 sector_kpis: dict[str, list[dict]]) -> list[dict]:
    """Veckans rapporter, en per bolag, i publiceringsordning."""
    index_path = raw_dir / week / "index.json"
    if not index_path.exists():
        return []
    patterns = name_patterns(instruments)
    items = json.loads(index_path.read_text(encoding="utf-8")).get("items", [])
    seen: set[str] = set()
    out = []
    for it in sorted(items, key=lambda i: i["published"]):
        published = datetime.fromisoformat(it["published"]).date()
        if it.get("source") not in ("mfn", "cision") or not is_report_title(it.get("title", ""), published):
            continue
        ticker = match_company(it, instruments, patterns)
        if ticker is None or ticker in seen:
            continue
        seen.add(ticker)
        inst = instruments[ticker]
        out.append({
            "ticker": ticker,
            "name": inst.namn,
            "sector": inst.sektor,
            "kpis": [k["id"] for k in kpis_for(inst, sector_kpis)],
            "published": it["published"],
            "raw_file": it["path"],
            "url": it["url"],
            "source_name": it.get("source_name") or it["source"],
            "text_kind": it.get("text_kind"),
            "title": it["title"],
        })
    for n, r in enumerate(out):
        r["batch"] = n // BATCH_SIZE + 1
    return out


def batches(reports: list[dict]) -> int:
    return max((r["batch"] for r in reports), default=0)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("week")
    p.add_argument("--omgang", type=int)
    p.add_argument("--antal-omgangar", action="store_true")
    args = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-W\d{2}", args.week):
        print(f"ogiltig vecka: {args.week!r}", file=sys.stderr)
        return 1
    reports = list_reports(RAW_DIR, args.week, load_instruments(), load_sector_kpis())
    if args.antal_omgangar:
        print(batches(reports))
        return 0
    chosen = [r for r in reports if args.omgang is None or r["batch"] == args.omgang]
    print(f"Vecka {args.week}: {len(reports)} rapporter i {batches(reports)} omgångar"
          + (f", omgång {args.omgang}: {len(chosen)}" if args.omgang else ""))
    print("nr | omgång | ticker | bolag | sektor | nyckeltal | publicerad | text | raw_file | rubrik")
    for n, r in enumerate(reports, start=1):
        if r in chosen:
            print(f"{n} | {r['batch']} | {r['ticker']} | {r['name']} | {r['sector']} | {', '.join(r['kpis'])} | "
                  f"{r['published'][:16]} | {r['text_kind']} | {r['raw_file']} | {r['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
