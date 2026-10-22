"""Slår ihop omgångarna från /rapportutfall och jämför med föregående år och med förväntan.

Tre lägen (se scripts/report_list.py):
- dag (morgonkörningen): data/results/morning/<datum>/omgang-<N>.json -> data/results/morning/<datum>.json
- uppdatering (17:45 eller "Uppdatera nu"): data/results/updates/<datumThhmm>/omgang-<N>.json
  -> data/results/updates/<datumThhmm>.json
- vecka (måndagens uppsamling): data/results/<vecka>/omgang-<N>.json plus veckans godkända
  morgon- och uppdateringsfiler -> data/results/<vecka>.json. Varje rapport har "scope" = körningen
  den kom från.

- Omgångsfilerna valideras var för sig; en omgång som saknas eller underkänns tas inte med
  (listas i "missing_batches").
- Förändring mot föregående år (yoy_pct): rapportens egen procentsats, annars uträknad ur
  värdena (inte för procenttal, där jämförs värdena direkt).
- Utfall mot förväntan: resultat per aktie och nettoomsättning för kvartalet jämförs med Yahoos
  konsensus ur den senaste ögonblicksbilden daterad FÖRE rapportdagen (aldrig samma dag eller
  efter), och aldrig med en post markerad "after_report" (bolaget hade redan rapporterat när
  bilden togs). Ögonblicksbildens nästa rapportdatum måste ligga högst CONSENSUS_DATE_DAYS dagar
  från rapporten (så att prognosen gäller samma kvartal) och valutan måste vara densamma.

Användning:
    python scripts/results.py 2026-10-20 --backup   # morgonkörning, med säkerhetskopia
    python scripts/results.py 2026-W43        # måndagens uppsamling
Exit-kod: 0 = filen skriven, 1 = inga godkända rapportutfall eller valideringen underkände.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_list import (  # noqa: E402
    MORNING_RAW, WEEK_RE, is_run, kpis_for, list_scope, run_dir, run_output, week_run_files,
)
from validate import DATA_DIR, RAW_DIR, Instrument, iso_week_period, load_instruments, load_sector_kpis  # noqa: E402
from validate_results import (  # noqa: E402
    UNCERTAIN, scope_period, surprise_pct, uncertain_consensus, unit_factor, validate_batch, validate_results,
    verdict,
)

STOCKHOLM = ZoneInfo("Europe/Stockholm")
RESULTS_DIR = DATA_DIR / "results"
CONSENSUS_DIR = DATA_DIR / "consensus"
CONSENSUS_DATE_DAYS = 3


def output_path(scope: str, results_dir: Path = RESULTS_DIR) -> Path:
    return run_output(scope, results_dir) if is_run(scope) else results_dir / f"{scope}.json"


def batch_dir(scope: str, results_dir: Path = RESULTS_DIR) -> Path:
    return run_dir(scope, results_dir) if is_run(scope) else results_dir / scope


def consensus_before(day: date, consensus_dir: Path = CONSENSUS_DIR) -> dict | None:
    """Senaste konsensusfilen daterad före day (aldrig samma dag)."""
    files = sorted(p for p in consensus_dir.glob("*.json")
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem) and p.stem < day.isoformat())
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def compare(kpi: dict | None, estimate: dict | None, uncertain: bool = False) -> dict | None:
    """Utfall mot förväntan för ett kvartalsvärde, eller None om det inte går att jämföra.
    uncertain: konsensus har varningen "stor förändring, få analytiker" – ingen över/under."""
    if kpi is None or estimate is None or kpi["period_kind"] != "kvartal" or not estimate.get("avg"):
        return None
    factor = unit_factor(kpi["unit"])
    if factor is None or factor[1] != (estimate.get("currency") or ""):
        return None
    actual = float(Decimal(str(kpi["value"])) * factor[0])
    s = round(surprise_pct(actual, estimate["avg"]), 1)
    return {"actual": actual, "expected": estimate["avg"], "analysts": estimate.get("analysts"),
            "currency": factor[1], "surprise_pct": s, "verdict": UNCERTAIN if uncertain else verdict(s)}


def vs_consensus(report: dict, published: date, consensus_dir: Path) -> dict | None:
    snap = consensus_before(published, consensus_dir)
    if snap is None:
        return None
    c = next((c for c in snap["companies"] if c["ticker"] == report["ticker"]), None)
    if c is None or c.get("after_report") or not c.get("next_report_date"):
        return None
    if abs((date.fromisoformat(c["next_report_date"]) - published).days) > CONSENSUS_DATE_DAYS:
        return None
    by_id = {k["id"]: k for k in report["kpis"]}
    uncertain = uncertain_consensus(c)
    eps = compare(by_id.get("resultat-per-aktie"), c.get("eps"), uncertain)
    revenue = compare(by_id.get("nettoomsattning"), c.get("revenue"), uncertain)
    if eps is None and revenue is None:
        return None
    return {"consensus_date": snap["date"], "uncertain": uncertain, "eps": eps, "revenue": revenue}


def yoy_pct(k: dict, kind: str) -> float | None:
    """Förändring mot föregående år i procent: rapportens egen siffra, annars uträknad ur värdena
    (inte för procenttal, där jämförs värdena direkt)."""
    if k["change_pct"] is not None:
        return k["change_pct"]
    if kind == "procent" or k["previous_value"] in (None, 0):
        return None
    return round((k["value"] - k["previous_value"]) / abs(k["previous_value"]) * 100, 1)


def _merge_batches(scope: str, instruments: dict[str, Instrument], dirs: dict, results_dir: Path,
                   consensus_dir: Path) -> tuple[list[dict], list[int], list[str]]:
    """Godkända omgångar för ett läge, som rapporter i den sammanslagna filens format."""
    sector_kpis = load_sector_kpis()
    listed = list_scope(scope, instruments, sector_kpis, **dirs)
    by_ticker = {r["ticker"]: r for r in listed}
    n_batches = max((r["batch"] for r in listed), default=0)
    reports, missing, problems = [], [], []
    for n in range(1, n_batches + 1):
        path = batch_dir(scope, results_dir) / f"omgang-{n}.json"
        if not path.exists():
            missing.append(n)
            problems.append(f"omgång {n} saknas")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        res = validate_batch(data, scope, n, instruments, dirs["raw_dir"], dirs["morning_raw"], results_dir)
        if res.errors:
            missing.append(n)
            problems.append(f"omgång {n} underkänd: {res.errors[0]}"
                            + (f" (+{len(res.errors) - 1})" if len(res.errors) > 1 else ""))
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
            order = list(kinds)  # sektorns nyckeltal först, i sectors.json-ordning
            kpis.sort(key=lambda k: order.index(k["id"]))
            out = {"ticker": r["ticker"], "name": inst.namn, "scope": scope, "sector": inst.sektor,
                   "published": listed_r["published"], "url": listed_r["url"],
                   "source_name": listed_r["source_name"], "raw_file": r["raw_file"], "period": r["period"],
                   "note": r["note"], "kpis": kpis}
            out["vs_consensus"] = vs_consensus(out, datetime.fromisoformat(listed_r["published"]).date(),
                                               consensus_dir)
            reports.append(out)
    return reports, missing, problems


def build(scope: str, instruments: dict[str, Instrument], now: datetime, raw_dir: Path = RAW_DIR,
          results_dir: Path = RESULTS_DIR, consensus_dir: Path = CONSENSUS_DIR,
          morning_raw: Path | None = MORNING_RAW) -> tuple[dict, list[str]]:
    dirs = {"raw_dir": raw_dir, "morning_raw": morning_raw, "results_dir": results_dir}
    reports, missing, problems = _merge_batches(scope, instruments, dirs, results_dir, consensus_dir)
    if WEEK_RE.match(scope):
        # Veckans morgon- och uppdateringskörningar: redan godkända när de skrevs, valideras igen
        # i validate_results.
        for p in week_run_files(scope, results_dir):
            reports += json.loads(p.read_text(encoding="utf-8"))["reports"]
    reports.sort(key=lambda r: (r["published"], r["name"]))
    return ({"schema_version": 1, "week": scope, "period": scope_period(scope),
             "generated_at": now.isoformat(timespec="seconds"), "reports": reports, "missing_batches": missing},
            problems)


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("scope", help="vecka (2026-W43), dag (2026-10-20) eller uppdatering (2026-10-20T1745)")
    p.add_argument("--backup", action="store_true",
                   help="säkerhetskopiera filen till det privata repot (veckan sköts annars av backup_week.py)")
    args = p.parse_args(argv)
    if not (WEEK_RE.match(args.scope) or is_run(args.scope)):
        print(f"ogiltig vecka, dag eller uppdatering: {args.scope!r}", file=sys.stderr)
        return 1
    instruments = load_instruments()
    data, problems = build(args.scope, instruments, now or datetime.now(STOCKHOLM))
    for msg in problems:
        print(f"varning: {msg}")
    if not data["reports"]:
        print("Inga godkända rapportutfall – ingen fil skrivs.", file=sys.stderr)
        return 1
    res = validate_results(data, args.scope, instruments)
    if res.errors:
        print("Rapportutfallen klarar inte valideringen – skrivs inte:", *res.errors, sep="\n  ", file=sys.stderr)
        return 1
    out = output_path(args.scope)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with_cons = sum(r["vs_consensus"] is not None for r in data["reports"])
    print(f"Rapportutfall {args.scope}: {len(data['reports'])} rapporter, {with_cons} jämförda med förväntan, "
          f"saknade omgångar: {data['missing_batches'] or 'inga'} -> {out}")
    if args.backup:
        from backup_week import commit_files

        ok, msg = commit_files(RAW_DIR, [(out, out.relative_to(DATA_DIR).as_posix())], f"Rapportutfall {args.scope}")
        print(f"Säkerhetskopia: {msg}")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
