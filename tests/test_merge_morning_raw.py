"""Tester för kompletteringen av veckans rådata med morgonens lokala hämtning (påhittade poster)."""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from merge_morning_raw import merge  # noqa: E402

NOW = datetime(2026, 10, 26, 8, 20, tzinfo=ZoneInfo("Europe/Stockholm"))


def item(id_, source, title, published, path, url=None, also_in=None):
    it = {"id": id_, "source": source, "title": title, "published": published, "path": path,
          "url": url or f"https://example.test/{id_}"}
    if also_in:
        it["also_in"] = also_in
    return it


def write(base: Path, items: list[dict]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for it in items:
        (base / it["path"]).parent.mkdir(parents=True, exist_ok=True)
        (base / it["path"]).write_text("Rubrik: x\n---\ntext\n", encoding="utf-8")
    (base / "index.json").write_text(json.dumps({"week": "2026-W43", "items": items}), encoding="utf-8")


def test_lagger_till_bara_det_som_saknas(tmp_path):
    actions = [item("a1", "mfn", "Alfaverken delårsrapport", "2026-10-21T08:00:00+02:00", "mfn/a1.txt",
                    also_in=[{"source": "cision", "url": "https://example.test/c9"}])]
    morning = [
        item("a1", "mfn", "Alfaverken delårsrapport", "2026-10-21T08:00:00+02:00", "mfn/a1.txt"),  # samma post
        item("c9", "cision", "Alfaverken delårsrapport", "2026-10-21T08:01:00+02:00", "cision/c9.txt"),  # also_in
        item("b2", "mfn", "Betabolaget: Q3 2026", "2026-10-22T07:00:00+02:00", "mfn/b2.txt"),  # saknas
        item("b3", "cision", "BETABOLAGET: Q3 2026", "2026-10-22T07:00:30+02:00", "cision/b3.txt"),  # samma rubrik och minut
    ]
    write(tmp_path / "raw", actions)
    write(tmp_path / "morning", morning)
    index, added = merge(tmp_path / "raw", tmp_path / "morning", NOW)
    assert [it["id"] for it in added] == ["b2"]
    assert [it["id"] for it in index["items"]] == ["a1", "b2"]  # i publiceringsordning
    assert index["merged_from_morning"] == [{"time": "2026-10-26T08:20:00+01:00", "items": 1}]
    assert index["items"][0] == actions[0]  # befintliga poster oförändrade


def test_inget_att_lagga_till(tmp_path):
    same = [item("a1", "mfn", "Alfaverken delårsrapport", "2026-10-21T08:00:00+02:00", "mfn/a1.txt")]
    write(tmp_path / "raw", same)
    write(tmp_path / "morning", same)
    index, added = merge(tmp_path / "raw", tmp_path / "morning", NOW)
    assert added == [] and "merged_from_morning" not in index
