"""Tester för fliken Swing: scripts/swing.py, scripts/swing_history.py och valideringen (påhittade kurser)."""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import swing  # noqa: E402
import swing_history  # noqa: E402
from signals import Bar  # noqa: E402
from validate import Instrument, validate_swing  # noqa: E402

TZ = ZoneInfo("Europe/Stockholm")
INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", (), "ALFA", "ALFA.ST", "Stockholm", sektor="industri"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm", sektor="fastigheter"),
}


def make_bars(closes, volumes=None, start=date(2026, 6, 1)):
    days, d = [], start
    while len(days) < len(closes):
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    vols = volumes or [1000.0] * len(closes)
    return [Bar(day, c, c, c * 1.01, c * 0.99, v) for day, c, v in zip(days, closes, vols)]


def test_rsi_och_glidande_medel():
    up = [float(100 + i) for i in range(60)]
    m = swing.series(make_bars(up))[-1]
    assert m["rsi2"] == 100.0 and m["rsi14"] == 100.0  # bara uppgångar
    assert m["ma20_pct"] > 0 and m["ma50_pct"] > 0 and m["ma20_over_ma50"]
    assert swing.series(make_bars(up))[49] is None  # för kort historik
    down = [float(200 - i) for i in range(60)]
    m = swing.series(make_bars(down))[-1]
    assert m["rsi2"] == 0.0 and m["ma20_pct"] < 0 and not m["ma20_over_ma50"]
    assert swing.technical_labels(m) == ["rsi2-under-10", "trend-ned"]


def test_utbrott_med_och_utan_omsattning():
    closes = [100.0] * 59 + [110.0]
    vols = [1000.0] * 59 + [3000.0]
    m = swing.series(make_bars(closes, vols))[-1]
    assert m["above_high20"] and m["volume_ratio"] == 3.0
    assert "utbrott-omsattning" in swing.technical_labels(m)
    m = swing.series(make_bars(closes))[-1]
    assert "utbrott" in swing.technical_labels(m) and "utbrott-omsattning" not in swing.technical_labels(m)


def test_rapportetiketter():
    assert swing.report_label(0, "över") == "efter-rapport-over"
    assert swing.report_label(4, "under") == "efter-rapport-under"
    assert swing.report_label(2, None) == "efter-rapport"
    assert swing.report_label(5, "över") is None  # utanför fem handelsdagar
    assert swing.report_label(None, None) is None
    # Före 17:30 reagerar samma dag, efter 17:30 nästa dag.
    assert swing.reaction_day(datetime(2026, 10, 23, 7, 30, tzinfo=TZ)) == date(2026, 10, 23)
    assert swing.reaction_day(datetime(2026, 10, 23, 17, 40, tzinfo=TZ)) == date(2026, 10, 24)


def test_build_och_validering():
    closes = [100.0 + i * 0.5 for i in range(70)]
    bars = {"ALFA.ST": make_bars(closes), "BETA.ST": make_bars([100.0] * 20)}  # BETA: för kort historik
    last = bars["ALFA.ST"][-1].day
    today = last + timedelta(days=1)
    # Rapport på fredagskvällen efter stängning -> reaktion nästa handelsdag; här på sista dagen.
    reports = {"ALFA": {"published": datetime.combine(last, datetime.min.time(), TZ).replace(hour=7).isoformat(),
                        "verdict": "över"}}
    data = swing.build(today, datetime.now(TZ), INSTRUMENTS, bars, reports, ("2026-10-27", {"ALFA": 1.25}))
    assert [c["ticker"] for c in data["companies"]] == ["ALFA"]
    a = data["companies"][0]
    assert a["days_since_report"] == 0 and a["short_pct"] == 1.25
    assert "efter-rapport-over" in a["labels"] and "trend-upp" in a["labels"]
    assert validate_swing(data, INSTRUMENTS).errors == []
    a["labels"] = ["utbrott"]
    assert any("stämmer inte" in e for e in validate_swing(data, INSTRUMENTS).errors)
    a["labels"] = swing.technical_labels(a) + ["efter-rapport-over"]
    data["labels"]["utbrott"] = "Köpläge"
    assert any("uppmaning" in e for e in validate_swing(data, INSTRUMENTS).errors)


def test_historik_per_etikett(tmp_path):
    # Index platt; ALFA stiger jämnt (trend upp, bättre än index), BETA faller (trend ned, sämre).
    n = 120
    bars = {
        "^OMXSPI": make_bars([1000.0] * n),
        "ALFA.ST": make_bars([100.0 + i for i in range(n)]),
        "BETA.ST": make_bars([300.0 - i for i in range(n)]),
    }
    hist = swing_history.build(bars, INSTRUMENTS, date(2026, 12, 31), results_dir=tmp_path)
    assert hist["base"]["5"]["n"] > 0 and abs(hist["base"]["5"]["better"] - 0.5) < 0.01  # hälften upp, hälften ned
    assert hist["labels"]["trend-upp"]["5"]["better"] == 1.0
    assert hist["labels"]["trend-ned"]["5"]["better"] == 0.0
    assert hist["labels"]["efter-rapport-over"]["5"]["n"] == 0
