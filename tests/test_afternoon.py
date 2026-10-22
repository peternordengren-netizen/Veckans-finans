"""Tester för eftermiddagsuppdateringens kursreaktion (scripts/afternoon.py) och dess validering
(påhittade bolag och kurser)."""

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import afternoon  # noqa: E402
from signals import Bar  # noqa: E402
from validate import Instrument, validate_afternoon  # noqa: E402

TZ = ZoneInfo("Europe/Stockholm")
TODAY = date(2026, 10, 22)  # torsdag; förra handelsdagen 21 okt
NOW = datetime(2026, 10, 22, 17, 46, tzinfo=TZ)
INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", (), "ALFA", "ALFA.ST", "Stockholm"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm"),
    "GAMMA": Instrument("Gammagruppen", (), "GAMMA", "GAMMA.OL", "Oslo"),
    "DELTA": Instrument("Deltahem", (), "DELTA", "DELTA.ST", "Stockholm"),
}
UPDATE = "2026-10-22T1745"


def row(ticker, published):
    return {"ticker": ticker, "name": INSTRUMENTS[ticker].namn, "published": published,
            "title": f"{INSTRUMENTS[ticker].namn} delårsrapport", "url": f"https://mfn.example/{ticker.lower()}"}


LISTS = {
    "2026-10-22": [row("DELTA", "2026-10-21T12:00:00+02:00"),  # före gårdagens stängning: reaktionen var i går
                   row("ALFA", "2026-10-22T07:00:00+02:00")],
    UPDATE: [row("GAMMA", "2026-10-22T12:00:00+02:00"),
             row("BETA", "2026-10-22T17:40:00+02:00")],  # efter stängning
}


def list_fn(scope, instruments, sector_kpis, results_dir=None):
    return LISTS[scope]


def bars(*closes):
    days = [date(2026, 10, 21), date(2026, 10, 22)][: len(closes)]
    return [Bar(d, c, c, c, c, 1000) for d, c in zip(days, closes)]


def fetch_today(tickers, start, end):
    return {"^OMXSPI": bars(100, 99), "ALFA.ST": bars(50, 53), "GAMMA.OL": bars(10, 9), "BETA.ST": bars(20, 21),
            "DELTA.ST": bars(30, 30)}


def results_dir(tmp_path):
    d = tmp_path / "results"
    (d / "morning" / "2026-10-22").mkdir(parents=True)
    (d / "updates" / UPDATE).mkdir(parents=True)
    return d


def test_kursreaktion_for_dagens_rapporterande_bolag(tmp_path):
    data = afternoon.build(TODAY, NOW, INSTRUMENTS, fetch_today, results_dir(tmp_path), list_fn)
    assert data["scopes"] == ["2026-10-22", UPDATE]
    assert data["price_day"] == "2026-10-22" and data["index"]["change_pct"] == -1.0
    by = {c["ticker"]: c for c in data["companies"]}
    assert "DELTA" not in by  # rapporten kom före förra handelsdagens stängning
    assert (by["ALFA"]["change_pct"], by["ALFA"]["relative_pp"], by["ALFA"]["close"]) == (6.0, 7.0, 53)
    assert (by["GAMMA"]["change_pct"], by["GAMMA"]["relative_pp"]) == (-10.0, None)  # inte i kronor: inget mot index
    assert by["BETA"]["after_close"] and by["BETA"]["change_pct"] is None and by["BETA"]["close"] is None
    assert [c["ticker"] for c in data["companies"]] == ["ALFA", "GAMMA", "BETA"]  # efter stängning sist
    assert validate_afternoon(data, "2026-10-22", INSTRUMENTS).errors == []


def test_validering_av_kursreaktionen(tmp_path):
    data = afternoon.build(TODAY, NOW, INSTRUMENTS, fetch_today, results_dir(tmp_path), list_fn)
    by = {c["ticker"]: c for c in data["companies"]}
    by["ALFA"]["relative_pp"] = 5.0
    by["BETA"]["change_pct"], by["BETA"]["close"] = 5.0, 21
    errors = validate_afternoon(data, "2026-10-22", INSTRUMENTS).errors
    assert any("mot index" in e for e in errors)
    assert any("efter stängning" in e for e in errors)
    assert validate_afternoon(data, "2026-10-23", INSTRUMENTS).errors  # fel datum mot filnamnet


def test_inga_kurser_i_dag_ger_ingen_reaktion(tmp_path):
    no_today = lambda t, s, e: {k: v[:1] for k, v in fetch_today(t, s, e).items()}  # noqa: E731
    data = afternoon.build(TODAY, NOW, INSTRUMENTS, no_today, results_dir(tmp_path), list_fn)
    assert data["price_day"] is None and data["index"]["change_pct"] is None
    assert all(c["change_pct"] is None and c["relative_pp"] is None for c in data["companies"])
    assert validate_afternoon(data, "2026-10-22", INSTRUMENTS).errors == []


def test_kursfel_stoppar_inte_uppdateringen(tmp_path):
    def broken(t, s, e):
        raise RuntimeError("Yahoo svarar inte")

    data = afternoon.build(TODAY, NOW, INSTRUMENTS, broken, results_dir(tmp_path), list_fn)
    assert data["errors"] == ["kursdata: Yahoo svarar inte"]
    assert validate_afternoon(data, "2026-10-22", INSTRUMENTS).errors == []
