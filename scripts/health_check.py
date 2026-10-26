"""Hälsokontroll av de automatiska körningarna, utan att ändra något.

Visar en tabell (fungerar / fungerar inte / oklart) för:
- de schemalagda uppgifterna: senaste körning, resultatkod och nästa körning
- dagens filer: morgonrapport, konsensus, rapportutfall och eftermiddag, och förra veckans veckofil
- servern (http://localhost:4321/veckans-finans/)
- Claudes kvot: om användningsgränsen är nådd (data/status/claude-limit.json), kvotstopp i veckans
  loggar, och veckans förbrukning (körningar, minuter, utskrivna tokens, API-pris som jämförelse)

Användning:
    python scripts/health_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from claude_status import STATUS_FILE, is_limit, status as limit_status  # noqa: E402
from morning import is_business_day  # noqa: E402

STOCKHOLM = ZoneInfo("Europe/Stockholm")
DATA = ROOT / "data"
LOGS = ROOT / "logs"
OK, FAIL, UNKNOWN = "fungerar", "fungerar inte", "oklart"
SITE = "http://localhost:4321/veckans-finans/"


def claude_usage(logs: Path, since: datetime) -> dict:
    """Claude-körningar i logs/**/*.json sedan since: antal, minuter, tokens, API-pris och kvotstopp."""
    out = {"runs": 0, "minutes": 0.0, "output_tokens": 0, "cost_usd": 0.0, "limit_stops": []}
    for p in sorted(logs.glob("*/*.json")):
        mtime = datetime.fromtimestamp(p.stat().st_mtime, STOCKHOLM)
        if mtime < since:
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or "num_turns" not in r:
            continue
        if is_limit(r):
            out["limit_stops"].append(f"{mtime:%a %H:%M} {p.parent.name}/{p.name}")
            continue
        out["runs"] += 1
        out["minutes"] += (r.get("duration_ms") or 0) / 60000
        out["output_tokens"] += (r.get("usage") or {}).get("output_tokens", 0)
        out["cost_usd"] += r.get("total_cost_usd") or 0
    return out


def quota_row(now: datetime, logs: Path = LOGS, status_file: Path = STATUS_FILE) -> tuple[str, str, str]:
    week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time(), STOCKHOLM)
    u = claude_usage(logs, week_start)
    tokens = f"{u['output_tokens']:,}".replace(",", " ")
    usage = (f"veckan: {u['runs']} körningar, {u['minutes']:.0f} min, {tokens} utskrivna tokens "
             f"(≈ {u['cost_usd']:.2f} USD i API-pris)")
    stops = f"; kvotstopp: {', '.join(u['limit_stops'])}" if u["limit_stops"] else ""
    if status_file.exists():
        return ("Claudes kvot", FAIL, f"{limit_status(now, status_file)}; {usage}{stops}")
    return ("Claudes kvot", UNKNOWN if u["limit_stops"] else OK, f"ingen aktiv användningsgräns; {usage}{stops}")


def task_rows() -> list[tuple[str, str, str]]:
    ps = ("Get-ScheduledTask -TaskName 'VeckansFinans*' | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{ n = $_.TaskName; s = [string]$_.State; last = $i.LastRunTime.ToString('yyyy-MM-dd HH:mm'); "
          "res = $i.LastTaskResult; next = $(if ($i.NextRunTime) { $i.NextRunTime.ToString('yyyy-MM-dd HH:mm') } else { '' }) } } "
          "| ConvertTo-Json")
    try:
        raw = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                             text=True, encoding="utf-8", errors="replace").stdout
        tasks = json.loads(raw) if raw.strip() else []
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return [("Schemalagda uppgifter", UNKNOWN, f"kunde inte läsas: {e}")]
    tasks = tasks if isinstance(tasks, list) else [tasks]
    rows = []
    for t in sorted(tasks, key=lambda t: t["n"]):
        # 267009 = körs just nu, 267011 = har aldrig körts (engångsuppgift som väntar)
        state = OK if t["res"] in (0, 267009, 267011) else FAIL
        rows.append((t["n"], state, f"senast {t['last']} (kod {t['res']}), nästa {t['next'] or '–'}, {t['s']}"))
    return rows


def file_rows(today: date) -> list[tuple[str, str, str]]:
    rows = []
    trading = is_business_day(today)
    y, w, _ = (today - timedelta(days=7)).isocalendar()
    week = f"{y}-W{w:02d}"
    checks = [("Veckosammanfattning " + week, DATA / "weeks" / f"{week}.json", True)]
    if trading:
        checks += [("Morgonrapport", DATA / "morning" / f"{today}.json", True),
                   ("Konsensus", DATA / "consensus" / f"{today}.json", True),
                   ("Rapportutfall i morgonrapporten", DATA / "results" / "morning" / f"{today}.json", False),
                   ("Eftermiddag", DATA / "afternoon" / f"{today}.json", False)]
    for name, path, required in checks:
        if path.exists():
            mt = datetime.fromtimestamp(path.stat().st_mtime, STOCKHOLM)
            rows.append((name, OK, f"{path.relative_to(ROOT).as_posix()} ({mt:%Y-%m-%d %H:%M})"))
        else:
            rows.append((name, FAIL if required else UNKNOWN,
                         f"{path.relative_to(ROOT).as_posix()} saknas" + ("" if required else " (kan vara utan rapporter eller före 17:45)")))
    return rows


def server_row() -> tuple[str, str, str]:
    try:
        with urllib.request.urlopen(SITE, timeout=5) as r:
            return ("Servern", OK if r.status == 200 else FAIL, f"HTTP {r.status}")
    except OSError as e:
        return ("Servern", FAIL, f"svarar inte: {e}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    now = datetime.now(STOCKHOLM)
    rows = task_rows() + file_rows(now.date()) + [server_row(), quota_row(now)]
    print(f"Hälsokontroll {now:%Y-%m-%d %H:%M}\n")
    print("| Kontroll | Status | Detalj |\n|---|---|---|")
    for name, state, detail in rows:
        print(f"| {name} | {state} | {detail} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
