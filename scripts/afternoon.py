"""Eftermiddagsuppdateringen: dagens kursreaktion för bolagen som rapporterat, utan Claude.

Skriver data/afternoon/<datum>.json (schema/afternoon.schema.json). Körs av
scripts/run_update.ps1 (vardagar 17:45 och skrivbordsgenvägen "Uppdatera nu") efter att
rapportutfallen för dagens uppdateringsfönster tagits fram.

- Bolagen: rapporterna i dagens körningsfönster (morgonen och dagens uppdateringar, se
  scripts/report_list.py) som publicerats från förra handelsdagens stängning (17:30) och framåt
  – deras första handelsdag efter rapporten är i dag. En rapport efter dagens stängning märks
  "after_close" och får ingen kursreaktion förrän nästa handelsdag.
- Kursen: ett batchanrop till Yahoo (scripts/signals.yahoo_bars) för bolagen och index. Dagens
  förändring är senaste kursen i dag mot förra handelsdagens stängning (justerad stängning, som
  i veckans kursfil); före stängning är det kursen vid körningen. Mot index i procentenheter,
  bara för aktier handlade i kronor (.ST), som i morgonrapporten.

Användning:
    python scripts/afternoon.py                  # i dag
    python scripts/afternoon.py --handelsdag     # bara kontrollen: exit 0 = handelsdag, 3 = inte
Exit-kod: 0 = filen skriven (eller ingen handelsdag), 1 = valideringen underkände, 3 = se ovan.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from morning import is_business_day, previous_business_day  # noqa: E402
from prices import INDEX_NAME, INDEX_TICKER  # noqa: E402
from report_list import RESULTS_DIR, list_scope, runs_on  # noqa: E402
from signals import BarFetcher, week_change, yahoo_bars  # noqa: E402
from validate import DATA_DIR, Instrument, load_instruments, load_sector_kpis, validate_afternoon  # noqa: E402

STOCKHOLM = ZoneInfo("Europe/Stockholm")
AFTERNOON_DIR = DATA_DIR / "afternoon"
MARKET_CLOSE = time(17, 30)
HISTORY_DAYS = 10  # räcker för förra handelsdagens stängning även efter en långhelg


def reporters(today: date, instruments: dict[str, Instrument], results_dir: Path = RESULTS_DIR,
              list_fn=list_scope) -> tuple[list[str], list[dict]]:
    """Dagens körningar och deras rapporter med reaktion i dag (eller efter dagens stängning)."""
    scopes = runs_on(today, results_dir)
    since = datetime.combine(previous_business_day(today), MARKET_CLOSE, STOCKHOLM)
    close = datetime.combine(today, MARKET_CLOSE, STOCKHOLM)
    sector_kpis = load_sector_kpis()
    out, seen = [], set()
    for scope in scopes:
        for r in list_fn(scope, instruments, sector_kpis, results_dir=results_dir):
            published = datetime.fromisoformat(r["published"])
            if published < since or r["ticker"] in seen:
                continue
            seen.add(r["ticker"])
            out.append({"ticker": r["ticker"], "name": r["name"], "scope": scope, "published": r["published"],
                        "title": r["title"], "url": r["url"], "after_close": published >= close})
    return scopes, out


def build(today: date, now: datetime, instruments: dict[str, Instrument], fetch: BarFetcher,
          results_dir: Path = RESULTS_DIR, list_fn=list_scope) -> dict:
    scopes, companies = reporters(today, instruments, results_dir, list_fn)
    errors: list[str] = []
    yahoo = {c["ticker"]: instruments[c["ticker"]].yahoo_ticker for c in companies}
    bars = {}
    if companies:
        try:
            bars = fetch([*yahoo.values(), INDEX_TICKER], today - timedelta(days=HISTORY_DAYS), today)
        except Exception as e:  # noqa: BLE001 – ett fel i kurshämtningen ska inte stoppa sidan
            errors.append(f"kursdata: {e}")
    has_today = any(b.day == today for bs in bars.values() for b in bs)
    index_change = week_change(bars.get(INDEX_TICKER, []), today, today) if has_today else None
    for c in companies:
        b = [x for x in bars.get(yahoo[c["ticker"]], []) if x.day <= today]
        change = week_change(b, today, today) if has_today and not c["after_close"] else None
        c["close"] = round(b[-1].close, 4) if change is not None else None
        c["change_pct"] = change
        c["relative_pp"] = (round(change - index_change, 2) if change is not None and index_change is not None
                            and yahoo[c["ticker"]].endswith(".ST") else None)
    companies.sort(key=lambda c: (c["after_close"], c["published"], c["name"]))
    return {
        "date": today.isoformat(),
        "generated_at": now.isoformat(timespec="seconds"),
        "scopes": scopes,
        "price_day": today.isoformat() if has_today else None,
        "index": {"ticker": INDEX_TICKER, "name": INDEX_NAME, "change_pct": index_change},
        "companies": companies,
        "errors": errors,
    }


def main(argv: list[str] | None = None, fetch: BarFetcher = yahoo_bars, now: datetime | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--handelsdag", action="store_true", help="kontrollera bara om i dag är en handelsdag")
    args = p.parse_args(argv)
    now = now or datetime.now(STOCKHOLM)
    today = now.date()
    if args.handelsdag:
        return 0 if is_business_day(today) else 3
    if not is_business_day(today):
        print(f"{today} är ingen handelsdag – ingen eftermiddagsuppdatering.")
        return 0
    instruments = load_instruments()
    data = build(today, now, instruments, fetch)
    res = validate_afternoon(data, today.isoformat(), instruments)
    if res.errors:
        print("Eftermiddagsuppdateringen klarar inte valideringen – skrivs inte:", *res.errors, sep="\n  ",
              file=sys.stderr)
        return 1
    out = AFTERNOON_DIR / f"{today}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    with_price = sum(c["change_pct"] is not None for c in data["companies"])
    print(f"Eftermiddag {today}: {len(data['companies'])} rapporterande bolag, {with_price} med kursreaktion, "
          f"körningar {', '.join(data['scopes']) or 'inga'}, {len(data['errors'])} fel -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
