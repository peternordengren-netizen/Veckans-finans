"""Säkerhetskopierar veckans filer till det privata repot data/raw/ (veckans-finans-raw).

Gör deterministiskt det som tidigare var manuella git-steg i sammanfatta-veckan.md,
så att den schemalagda körningen bara behöver tillåtelse för det här skriptet och
inte för git i allmänhet:

1. Kontrollerar att data/raw/ inte har egna oincheckade ändringar – annars stopp,
   eftersom någon annans ändringar aldrig ska committas.
2. git pull --rebase (hämtar GitHub Actions senaste hämtningar).
3. Kopierar data/weeks/<vecka>.json och, om de finns, data/prices/<vecka>.json,
   data/analysis/<vecka>.json och data/signals/<vecka>.json till motsvarande mapp i data/raw/.
4. Lägger bara till just de filerna (aldrig git add -A), committar med
   "Säkerhetskopia <vecka> (validering OK|EJ GODKÄND)" om något ändrats.
   Valideringsstatusen räknas fram här med validate.py, den anges inte av anroparen.
5. git push; avvisas den görs pull --rebase och ett enda nytt försök.

Användning:
    python scripts/backup_week.py 2026-W42
Exit-kod: 0 = pushad eller oförändrad, 1 = fel (orsaken skrivs ut).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402

WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
KINDS = ("weeks", "prices", "analysis", "signals", "results", "valuation")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Kör git i repo och returnerar resultatet (kastar inte vid fel)."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def backup(week: str, data_dir: Path, raw_dir: Path, validation_ok: bool) -> tuple[bool, str]:
    """Kopierar och pushar veckans filer. Returnerar (lyckades, meddelande)."""
    if not WEEK_RE.match(week):
        return False, f"ogiltig vecka: {week!r}"
    if not (data_dir / "weeks" / f"{week}.json").exists():
        return False, f"data/weeks/{week}.json saknas"
    files = [(data_dir / kind / f"{week}.json", f"{kind}/{week}.json") for kind in KINDS
             if (data_dir / kind / f"{week}.json").exists()]
    label = "validering OK" if validation_ok else "validering EJ GODKÄND"
    return commit_files(raw_dir, files, f"Säkerhetskopia {week} ({label})", label)


def commit_files(raw_dir: Path, files: list[tuple[Path, str]], message: str, label: str = "") -> tuple[bool, str]:
    """Kopierar (källa, sökväg i data/raw/) till det privata repot, committar bara de filerna och pushar.

    Stannar om data/raw/ har egna oincheckade ändringar. Används av backup() och av andra
    skript som säkerhetskopierar egna filer (t.ex. scripts/consensus.py).
    """
    status = git(raw_dir, "status", "--porcelain")
    if status.returncode != 0:
        return False, f"git status misslyckades i {raw_dir}: {status.stderr.strip()}"
    if status.stdout.strip():
        return False, "data/raw/ har oincheckade ändringar, inget kopierades:\n" + status.stdout.rstrip()
    pull = git(raw_dir, "pull", "--rebase")
    if pull.returncode != 0:
        return False, f"git pull --rebase misslyckades: {pull.stderr.strip()}"

    added = []
    for src, rel in files:
        dst = raw_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        added.append(rel)
    add = git(raw_dir, "add", "--", *added)
    if add.returncode != 0:
        return False, f"git add misslyckades: {add.stderr.strip()}"
    if git(raw_dir, "diff", "--cached", "--quiet").returncode == 0:
        return True, f"oförändrad sedan förra kopian ({', '.join(added)})"

    commit = git(raw_dir, "commit", "-q", "-m", message)
    if commit.returncode != 0:
        return False, f"git commit misslyckades: {commit.stderr.strip()}"
    push = git(raw_dir, "push", "-q")
    if push.returncode != 0:
        # Actions kan ha hunnit pusha emellan: ett enda nytt försök efter rebase.
        retry_pull = git(raw_dir, "pull", "--rebase")
        push = git(raw_dir, "push", "-q") if retry_pull.returncode == 0 else retry_pull
        if push.returncode != 0:
            return False, (
                f"push misslyckades (commit finns lokalt i data/raw/): {push.stderr.strip()}"
            )
    head = git(raw_dir, "rev-parse", "--short", "HEAD").stdout.strip()
    detail = f"{label}; " if label else ""
    return True, f"pushad till veckans-finans-raw: {head} ({detail}{', '.join(added)})"


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if len(argv) != 1:
        print("användning: backup_week.py <vecka>", file=sys.stderr)
        return 1
    week = argv[0]
    week_file = validate.DATA_DIR / "weeks" / f"{week}.json"
    validation_ok = week_file.exists() and validate.main([str(week_file)]) == 0
    ok, message = backup(week, validate.DATA_DIR, validate.DATA_DIR / "raw", validation_ok)
    print(f"Säkerhetskopia: {message}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
