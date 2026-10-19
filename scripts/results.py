"""Slår ihop veckans omgångar från /rapportutfall till data/results/<vecka>.json och jämför
med föregående år och med förväntan.

- Omgångsfilerna data/results/<vecka>/omgang-<N>.json valideras var för sig; en omgång som
  saknas eller underkänns tas inte med (listas i "missing_batches").
- Förändring mot föregående år: den angivna procentsatsen, annars räknad ur värdena (inte
  för procenttal, där jämförs värdena direkt).
- Utfall mot förväntan: resultat per aktie och nettoomsättning för kvartalet jämförs med Yahoos
  konsensus ur den senaste ögonblicksbilden *före* rapportdagen (data/consensus/<datum>.json),
  och bara om ögonblicksbildens nästa rapportdatum ligger högst CONSENSUS_DATE_DAYS dagar från
  rapporten (så att prognosen gäller samma kvartal) och valutan är densamma.

Användning:
    python scripts/results.py 2026-W43
Exit-kod: 0 = filen skriven, 1 = inga godkända omgångar eller valideringen underkände.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_list import kpis_for, list_reports  # noqa: E402
from validate import DATA_DIR, RAW_DIR, Instrument, iso_week_period, load_instruments, load_sector_kpis  # noqa: E402
from validate_results import surprise_pct, unit_factor, validate_batch, validate_results, verdict  # noqa: E402

STOCKHOLM = ZoneInfo("Europe/Stockholm")
RESULTS_DIR = DATA_DIR / "results"
CONSENSUS_DIR = DATA_DIR / "consensus"
CONSENSUS_DATE_DAYS = 3


def consensus_before(day: date, consensus_dir: Path = CONSENSUS_DIR) -> dict | None:
    """Senaste konsensusfilen daterad före day."""
    files = sorted(p for p in consensus_dir.glob("*.json")
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem) and p.stem < day.isoformat())
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def compare(kpi: dict | None, estimate: dict | None) -> dict | None:
    """Utfall mot förväntan för ett kvartalsvärde, eller None om det inte går att jämföra."""
    if kpi is None or estimate is None or kpi["period_kind"] != "kvartal" or not estimate.get("avg"):
        return None
    factor = unit_factor(kpi["unit"])
    if factor is None or factor[1] != (estimate.get("currency") or ""):
        return None
    actual = float(Decimal(str(kpi["value"])) * factor[0])
    s = round(surprise_pct(actual, estimate["avg"]), 1)
    return {"actual": actual, "expected": estimate["avg"], "analysts": estimate.get("analysts"),
            "currency": factor[1], "surprise_pct": s, "verdict": verdict(s)}


def vs_consensus(report: dict, published: date, consensus_dir: Path) -> dict | None:
    snap = consensus_before(published, consensus_dir)
    if snap is None:
        return None
    c = next((c for c in snap["companies"] if c["ticker"] == report["ticker"]), None)
    if c is None or not c.get("next_report_date"):
        return None
    if abs((date.fromisoformat(c["next_report_date"]) - published).days) > CONSENSUS_DATE_DAYS:
        return None
    by_id = {k["id"]: k for k in report["kpis"]}
    eps = compare(by_id.get("resultat-per-aktie"), c.get("eps"))
    revenue = compare(by_id.get("nettoomsattning"), c.get("revenue"))
    if eps is None and revenue is None:
        return None
    return {"consensus_date": snap["date"], "eps": eps, "revenue": revenue}


def yoy_pct(k: dict, kind: str) -> float | None:
    """Förändring mot föregående år i procent: rapportens egen siffra, annars uträknad ur värdena
    (inte för procenttal, där jämförs värdena direkt)."""
    if k["change_pct"] is not None:
        return k["change_pct"]
    if kind == "procent" or k["previous_value"] in (None, 0):
        return None
    return round((k["value"] - k["previous_value"]) / abs(k["previous_value"]) * 100, 1)


def build(week: str, instruments: dict[str, Instrument], now: datetime, raw_dir: Path = RAW_DIR,
          results_dir: Path = RESULTS_DIR, consensus_dir: Path = CONSENSUS_DIR) -> tuple[dict, list[str]]:
    sector_kpis = load_sector_kpis()
    listed = list_reports(raw_dir, week, instruments, sector_kpis)
    by_ticker = {r["ticker"]: r for r in listed}
    n_batches = max((r["batch"] for r in listed), default=0)
    reports, missing, problems = [], [], []
    for n in range(1, n_batches + 1):
        path = results_dir / week / f"omgang-{n}.json"
        if not path.exists():
            missing.append(n)
            problems.append(f"omgång {n} saknas")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        res = validate_batch(data, week, n, instruments, raw_dir)
        if res.errors:
            missing.append(n)
            problems.append(f"omgång {n} underkänd: {res.errors[0]}" + (f" (+{len(res.errors) - 1})" if len(res.errors) > 1 else ""))
            continue
        for r in data["reports"]:
            inst = instruments[r["ticker"]]
            kinds = {k["id"]: k for k in kpis_for(inst, sector_kpis)}
            listed_r = by_ticker[r["ticker"]]
            kpis = [{"id": k["id"], "name": kinds[k["id"]]["name"], "value": k["value"], "unit": k["unit"],
                     "previous_value": k["previous_value"], "change_pct": k["change_pct"],
                     "yoy_pct": yoy_pct(k, kinds[k["id"]]["kind"]),
                     "period_kind": k["period_kind"], "quote": k["quote"]}
                    for k in r["kpis"]]
            # Sektorns nyckeltal först, i sectors.json-ordning.
            order = list(kinds)
            kpis.sort(key=lambda k: order.index(k["id"]))
            out = {"ticker": r["ticker"], "name": inst.namn, "sector": inst.sektor,
                   "published": listed_r["published"], "url": listed_r["url"],
                   "source_name": listed_r["source_name"], "raw_file": r["raw_file"], "period": r["period"],
                   "note": r["note"], "kpis": kpis}
            out["vs_consensus"] = vs_consensus(out, datetime.fromisoformat(listed_r["published"]).date(),
                                               consensus_dir)
            reports.append(out)
    reports.sort(key=lambda r: (r["published"], r["name"]))
    start, end = iso_week_period(week)
    return ({"schema_version": 1, "week": week, "period": {"start": start.isoformat(), "end": end.isoformat()},
             "generated_at": now.isoformat(timespec="seconds"), "reports": reports, "missing_batches": missing},
            problems)


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("week")
    args = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-W\d{2}", args.week):
        print(f"ogiltig vecka: {args.week!r}", file=sys.stderr)
        return 1
    instruments = load_instruments()
    data, problems = build(args.week, instruments, now or datetime.now(STOCKHOLM))
    for msg in problems:
        print(f"varning: {msg}")
    if not data["reports"]:
        print("Inga godkända rapportutfall – ingen fil skrivs.", file=sys.stderr)
        return 1
    res = validate_results(data, args.week, instruments)
    if res.errors:
        print("Rapportutfallen klarar inte valideringen – skrivs inte:", *res.errors, sep="\n  ", file=sys.stderr)
        return 1
    out = RESULTS_DIR / f"{args.week}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with_cons = sum(r["vs_consensus"] is not None for r in data["reports"])
    print(f"Rapportutfall {args.week}: {len(data['reports'])} rapporter, {with_cons} jämförda med förväntan, "
          f"saknade omgångar: {data['missing_batches'] or 'inga'} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
