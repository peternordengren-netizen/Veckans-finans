"""Skriver en kompakt översikt av data/raw/<vecka>/index.json, en rad per post.

index.json blir flera hundra poster stor och för lång att läsa i ett svep. Översikten
har bara det som behövs för urvalet i sammanfatta-veckan.md:

    nr | källa | publicerad | company | R(utin)/- | F(ulltext)/U(tdrag) | path | rubrik

Nyckeltal (Riksbanken) listas med sitt värde. Översikten visas i sidor om PAGE_SIZE
poster (--sida 1, 2, ...) så att varje utskrift ryms i ett verktygsanrop. Sist på
varje sida står källkörningarnas status (runs) sammanräknad per källa.

Användning:
    python scripts/index_overview.py 2026-W42            # sida 1
    python scripts/index_overview.py 2026-W42 --sida 2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
PAGE_SIZE = 120  # ~25 000 tecken per sida


def item_line(n: int, it: dict) -> str:
    """En rad för en indexpost."""
    routine = "R" if it.get("routine") else "-"
    kind = "U" if it.get("text_kind") == "utdrag" else "F"
    extra = ""
    rate = (it.get("data") or {}).get("policy_rate")
    if rate:
        extra = f" [styrränta {rate.get('value')} per {rate.get('date')}, ändrad {rate.get('changed_on')}]"
    return (
        f"{n} | {it.get('source')} | {(it.get('published') or '')[:16]} | {it.get('company')} | "
        f"{routine} | {kind} | {it.get('path')} | {it.get('title')}{extra}"
    )


def runs_summary(runs: list[dict]) -> str:
    """Antal körningar och antal fel per källa, t.ex. 'mfn 0 fel, cision 2 fel'."""
    errors: Counter = Counter()
    seen: set[str] = set()
    for run in runs:
        for source, info in (run.get("sources") or {}).items():
            seen.add(source)
            if info.get("status") != "ok":
                errors[source] += 1
    parts = ", ".join(f"{s} {errors[s]} fel" for s in sorted(seen))
    return f"Körningar: {len(runs)} ({parts})" if runs else "Körningar: inga"


def overview(index: dict, page: int) -> list[str]:
    """Bygger en sida av översikten ur ett inläst index."""
    items = index.get("items", [])
    pages = max(1, -(-len(items) // PAGE_SIZE))
    first = (page - 1) * PAGE_SIZE
    lines = [
        f"Vecka {index.get('week')}, uppdaterad {index.get('updated_at')}, {len(items)} poster, "
        f"sida {page} av {pages}"
    ]
    lines += [item_line(n, it) for n, it in enumerate(items[first:first + PAGE_SIZE], start=first + 1)]
    lines.append(runs_summary(index.get("runs", [])))
    return lines


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("week")
    parser.add_argument("--sida", type=int, default=1)
    args = parser.parse_args(argv)
    if not WEEK_RE.match(args.week) or args.sida < 1:
        print("användning: index_overview.py <vecka, t.ex. 2026-W42> [--sida N]", file=sys.stderr)
        return 1
    path = RAW_DIR / args.week / "index.json"
    if not path.exists():
        print(f"{path} saknas", file=sys.stderr)
        return 1
    print("\n".join(overview(json.loads(path.read_text(encoding="utf-8")), args.sida)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
