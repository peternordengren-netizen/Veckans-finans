"""Tester för scripts/index_overview.py."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import index_overview  # noqa: E402
from index_overview import overview, runs_summary  # noqa: E402


def item(n, **extra):
    base = {
        "source": "mfn", "published": "2026-10-12T06:00:00+02:00", "company": "acme", "routine": False,
        "text_kind": "fulltext", "path": f"mfn/{n}.txt", "title": f"Rubrik {n}",
    }
    return {**base, **extra}


def test_rad_per_post_med_rutin_och_utdrag():
    index = {"week": "2026-W42", "items": [item(1), item(2, routine=True, text_kind="utdrag", source="cision")]}
    lines = overview(index, 1)
    assert lines[1] == "1 | mfn | 2026-10-12T06:00 | acme | - | F | mfn/1.txt | Rubrik 1"
    assert lines[2] == "2 | cision | 2026-10-12T06:00 | acme | R | U | mfn/2.txt | Rubrik 2"


def test_styrrantan_visas_med_varde():
    rate = {"value": 1.75, "date": "2026-10-12", "changed_on": "2025-10-01"}
    lines = overview({"items": [item(1, source="riksbanken", data={"policy_rate": rate})]}, 1)
    assert lines[1].endswith("[styrränta 1.75 per 2026-10-12, ändrad 2025-10-01]")


def test_sidindelning(monkeypatch):
    monkeypatch.setattr(index_overview, "PAGE_SIZE", 2)
    index = {"week": "2026-W42", "items": [item(n) for n in range(1, 6)]}
    page2 = overview(index, 2)
    assert "sida 2 av 3" in page2[0]
    assert [line.split(" | ")[0] for line in page2[1:-1]] == ["3", "4"]
    assert len(overview(index, 3)) == 3  # rubrik, post 5, körningar


def test_korningar_raknar_fel_per_kalla():
    runs = [
        {"sources": {"mfn": {"status": "ok"}, "cision": {"status": "fel"}}},
        {"sources": {"mfn": {"status": "ok"}, "cision": {"status": "fel"}}},
    ]
    assert runs_summary(runs) == "Körningar: 2 (cision 2 fel, mfn 0 fel)"
    assert runs_summary([]) == "Körningar: inga"
