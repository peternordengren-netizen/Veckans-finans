"""Kompletterar veckans rådata i det privata repot med poster från morgonflödets lokala hämtning.

GitHub Actions hämtar råtexten varannan timme men hoppar över eller försenar körningar (5–14 timmars
luckor vecka 43). Morgon- och eftermiddagsflödet hämtar lokalt till data/morning/raw/<vecka>/ (MFN med
500 poster), och där fanns 46 av veckans 68 Large Cap-rapporter som saknades i data/raw/<vecka>/ –
bland annat Tele2, Telia, SEB, Swedbank, Volvo och ABB. Veckosammanfattningen läser bara
data/raw/<vecka>/, så de kom aldrig med.

Skriptet lägger till poster som finns i morgonrådatan men inte i veckans rådata (samma källa och id,
eller samma rubrik och publiceringsminut), kopierar textfilerna, skriver ett sammanslaget index.json
och committar till veckans-finans-raw (som säkerhetskopiorna, scripts/backup_week.commit_files).
Befintliga poster ändras aldrig. Indexet får en rad under "merged_from_morning".

Körs av run_weekly.ps1 före /sammanfatta-veckan.

Användning:
    python scripts/merge_morning_raw.py 2026-W43            # kompletterar och committar
    python scripts/merge_morning_raw.py 2026-W43 --torrkorning
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backup_week import commit_files, git  # noqa: E402
from validate import RAW_DIR  # noqa: E402

MORNING_RAW = ROOT / "data" / "morning" / "raw"
STOCKHOLM = ZoneInfo("Europe/Stockholm")
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def _key(it: dict) -> str:
    return f"{it.get('source')}:{it.get('id') or it.get('url')}"


def _title_key(it: dict) -> tuple[str, str]:
    return (" ".join((it.get("title") or "").lower().split()), (it.get("published") or "")[:16])


def merge(week_raw: Path, morning_week: Path, now: datetime) -> tuple[dict, list[dict]]:
    """Det sammanslagna indexet och de poster som lades till (bara från morgonrådatan)."""
    index = json.loads((week_raw / "index.json").read_text(encoding="utf-8"))
    morning = json.loads((morning_week / "index.json").read_text(encoding="utf-8"))
    items = index.get("items", [])
    keys = {_key(it) for it in items}
    titles = {_title_key(it) for it in items}
    also = {a.get("url") for it in items for a in it.get("also_in", [])}
    paths = {it.get("path") for it in items}
    added = []
    for it in morning.get("items", []):
        if _key(it) in keys or _title_key(it) in titles or it.get("url") in also or it.get("path") in paths:
            continue
        if not (morning_week / it["path"]).is_file():
            continue
        added.append(it)
        keys.add(_key(it))
        titles.add(_title_key(it))
        paths.add(it["path"])
    if added:
        index["items"] = sorted(items + added, key=lambda it: it.get("published") or "")
        index.setdefault("merged_from_morning", []).append(
            {"time": now.isoformat(timespec="seconds"), "items": len(added)})
    return index, added


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("week")
    p.add_argument("--torrkorning", action="store_true", help="visa bara vad som skulle läggas till")
    args = p.parse_args(argv)
    if not WEEK_RE.match(args.week):
        print(f"ogiltig vecka: {args.week!r}", file=sys.stderr)
        return 1
    week_raw, morning_week = RAW_DIR / args.week, MORNING_RAW / args.week
    if not (morning_week / "index.json").exists() or not (week_raw / "index.json").exists():
        print(f"Ingen komplettering: {morning_week} eller {week_raw} saknar index.json.")
        return 0
    if not args.torrkorning:
        # Räkna på senaste versionen (Actions kan ha pushat), så att inga av dess poster skrivs över.
        pull = git(RAW_DIR, "pull", "--rebase", "-q")
        if pull.returncode != 0:
            print(f"git pull misslyckades, ingen komplettering: {pull.stderr.strip()}", file=sys.stderr)
            return 1
    index, added = merge(week_raw, morning_week, datetime.now(STOCKHOLM))
    print(f"Komplettering {args.week}: {len(added)} poster från morgonens lokala hämtning saknades i "
          f"{week_raw.relative_to(ROOT).as_posix()}")
    if not added or args.torrkorning:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_index = Path(tmp) / "index.json"
        tmp_index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [(morning_week / it["path"], f"{args.week}/{it['path']}") for it in added]
        files.append((tmp_index, f"{args.week}/index.json"))
        ok, msg = commit_files(RAW_DIR, files, f"Komplettering {args.week}: {len(added)} poster från morgonens hämtning")
    # commit_files räknar upp varje fil; för hundratals filer räcker commit och antal.
    print(f"Säkerhetskopia: {msg.split(' (')[0]} ({len(added)} textfiler och index.json)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
