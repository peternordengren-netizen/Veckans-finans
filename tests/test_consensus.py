"""Tester för scripts/consensus.py och validate_consensus (påhittade bolag)."""

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from consensus import _estimate, build  # noqa: E402
from validate import Instrument, validate_consensus  # noqa: E402

NOW = datetime(2026, 10, 19, 8, 10, tzinfo=ZoneInfo("Europe/Stockholm"))
INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", (), "ALFA", "ALFA.ST", "Stockholm"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm"),
    "GAMA": Instrument("Gammagruppen", (), "GAMA", "GAMA.ST", "Stockholm"),
    "DELT": Instrument("Deltafastigheter", (), "DELT", "DELT.ST", "Stockholm"),
}


def est(avg, low, high, n, year_ago, ccy="SEK"):
    return {"avg": avg, "low": low, "high": high, "analysts": n, "year_ago": year_ago, "currency": ccy}


def fake(ticker):
    if ticker == "BETA.ST":
        raise ConnectionError("timeout")
    if ticker == "GAMA.ST":
        return {"eps": None, "revenue": None, "next_report_date": None, "most_recent_quarter": None,
                "financial_currency": "SEK", "analyst_opinions": None}
    return {"eps": est(5.4, 5.3, 5.7, 4, 5.5, "EUR" if ticker == "DELT.ST" else "SEK"),
            "revenue": est(18.6e9, 17.7e9, 19.0e9, 11, 17.2e9),
            "next_report_date": "2026-10-27", "most_recent_quarter": "2026-06-30",
            "financial_currency": "EUR" if ticker == "DELT.ST" else "SEK", "analyst_opinions": 16}


def test_build_hoppar_over_fel_och_bolag_utan_konsensus():
    data = build(date(2026, 10, 19), NOW, INSTRUMENTS, fake)
    assert [c["ticker"] for c in data["companies"]] == ["ALFA", "DELT"]
    assert data["errors"] == ["BETA.ST: ConnectionError"]
    assert data["companies"][1]["eps"]["currency"] == "EUR"
    assert validate_consensus(data, INSTRUMENTS).errors == []


def test_validering_snitt_utanfor_intervall_och_okant_bolag():
    data = build(date(2026, 10, 19), NOW, INSTRUMENTS, fake)
    data["companies"][0]["eps"]["avg"] = 9.9
    data["companies"].append({**data["companies"][1], "ticker": "OKAND"})
    errors = validate_consensus(data, INSTRUMENTS).errors
    assert any("utanför" in e for e in errors)
    assert any("instruments.csv" in e for e in errors)


def test_estimate_ur_yfinance_tabell():
    df = pd.DataFrame(
        {"avg": [5.426, 6.3], "low": [5.304, 5.8], "high": [5.68, 6.7], "numberOfAnalysts": [4, 3],
         "yearAgoEps": [5.53, 4.8], "growth": [-0.02, 0.3], "currency": ["SEK", "SEK"]},
        index=pd.Index(["0q", "+1q"], name="period"),
    )
    assert _estimate(df, "yearAgoEps") == est(5.426, 5.304, 5.68, 4, 5.53)
    assert _estimate(None, "yearAgoEps") is None
    nan = df.copy()
    nan.loc["0q", "avg"] = float("nan")
    assert _estimate(nan, "yearAgoEps") is None
