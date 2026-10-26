"""Claudes användningsgräns: känner igen ett stopp i Claude Codes JSON-svar och sparar status.

När kvoten är slut svarar Claude Code med api_error "usage_limit_reached" (HTTP 429) och en text
som "You've hit your weekly limit · resets 8am (Europe/Stockholm)". Ett sådant stopp ska inte räknas
som ett försök (run_weekly.ps1, run_results.ps1 och run_morning.ps1 räknar annars högst två),
återställningstiden loggas, och sidan visar "Claudes användningsgräns nådd – försöker igen efter
<tid>" (data/status/claude-limit.json, läses vid bygget).

Användning (från PowerShell-skripten):
    python scripts/claude_status.py check <claude.json> --kalla "veckosammanfattning 2026-W43"
        exit 0 = inget stopp (statusfilen tas bort om Claude faktiskt körde), 3 = användningsgräns nådd:
        skriver "Claudes användningsgräns nådd – försöker igen efter 08:00" och "RESET_AT <iso>"
    python scripts/claude_status.py status       # för hälsokontrollen
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
STATUS_FILE = ROOT / "data" / "status" / "claude-limit.json"
STOCKHOLM = ZoneInfo("Europe/Stockholm")
LIMIT_ERRORS = {"usage_limit_reached", "rate_limit_reached"}
EXIT_LIMIT = 3

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
# "resets 8am (Europe/Stockholm)", "resets 8:30pm (…)", "resets Oct 27, 8am (…)", "resets Oct 27 at 8am"
_RESET_RE = re.compile(
    r"resets\s+(?:(?P<mon>[A-Za-z]{3})[a-z]*\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?(?:\s*\((?P<tz>[^)]+)\))?",
    re.IGNORECASE,
)


def is_limit(result: dict) -> bool:
    return result.get("api_error") in LIMIT_ERRORS or (
        result.get("api_error_status") == 429 and "limit" in str(result.get("result", "")).lower())


def reset_time(text: str, now: datetime) -> datetime | None:
    """Återställningstiden ur Claudes meddelande, som nästa sådan tidpunkt efter now (Europe/Stockholm
    om ingen annan tidszon anges); None om texten inte går att tolka."""
    m = _RESET_RE.search(text or "")
    if not m:
        return None
    h, mi = int(m["h"]), int(m["m"] or 0)
    if m["ampm"]:
        h = h % 12 + (12 if m["ampm"].lower() == "pm" else 0)
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    try:
        tz = ZoneInfo(m["tz"]) if m["tz"] else STOCKHOLM
    except Exception:  # noqa: BLE001 – okänd tidszon i texten: räkna i svensk tid
        tz = STOCKHOLM
    local_now = now.astimezone(tz)
    if m["mon"]:
        mon = _MONTHS.get(m["mon"][:3].lower())
        if mon is None:
            return None
        d = date(local_now.year, mon, int(m["day"]))
        if d < local_now.date() - timedelta(days=180):  # över årsskiftet
            d = date(local_now.year + 1, mon, int(m["day"]))
        return datetime.combine(d, time(h, mi), tz)
    at = datetime.combine(local_now.date(), time(h, mi), tz)
    return at if at > local_now else at + timedelta(days=1)


def limit_message(reset: datetime | None, now: datetime) -> str:
    """"Claudes användningsgräns nådd – försöker igen efter 08:00" (med datum om det inte är i dag)."""
    if reset is None:
        return "Claudes användningsgräns nådd – försöker igen efter återställningen"
    r = reset.astimezone(STOCKHOLM)
    when = r.strftime("%H:%M") if r.date() == now.astimezone(STOCKHOLM).date() else f"{r.day}/{r.month} {r:%H:%M}"
    return f"Claudes användningsgräns nådd – försöker igen efter {when}"


def check(json_path: Path, source: str, now: datetime, status_file: Path = STATUS_FILE) -> int:
    try:
        result = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return 0  # inget läsbart svar: inget kvotstopp att rapportera
    if not is_limit(result):
        # Claude körde (minst en tur med svar från modellen): ett tidigare stopp är över.
        if result.get("num_turns", 0) >= 1 and not result.get("api_error") and status_file.exists():
            status_file.unlink()
        return 0
    reset = reset_time(str(result.get("result", "")), now)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps({
        "hit_at": now.isoformat(timespec="seconds"),
        "reset_at": reset.isoformat(timespec="minutes") if reset else None,
        "message": str(result.get("result", "")),
        "source": source,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(limit_message(reset, now))
    if reset:
        print(f"RESET_AT {reset.isoformat(timespec='minutes')}")
    return EXIT_LIMIT


def status(now: datetime, status_file: Path = STATUS_FILE) -> str:
    if not status_file.exists():
        return "Ingen användningsgräns nådd (ingen statusfil)."
    s = json.loads(status_file.read_text(encoding="utf-8"))
    reset = datetime.fromisoformat(s["reset_at"]) if s.get("reset_at") else None
    state = "AKTIV" if reset is None or reset > now else "passerad, väntar på nästa körning"
    return f"Användningsgräns nådd {s['hit_at']} ({s['source']}), återställs {s.get('reset_at') or 'okänt'}: {state}"


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("json_path", type=Path)
    c.add_argument("--kalla", default="claude")
    sub.add_parser("status")
    args = p.parse_args(argv)
    now = now or datetime.now(STOCKHOLM)
    if args.cmd == "check":
        return check(args.json_path, args.kalla, now)
    print(status(now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
