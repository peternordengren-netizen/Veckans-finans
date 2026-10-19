"""Tester för scripts/valuation.py och validate_valuation (påhittade bolag och kurser)."""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from signals import Bar  # noqa: E402
from validate import Instrument, validate_valuation  # noqa: E402
from valuation import build, ttm  # noqa: E402

WEEK = "2026-W42"
NOW = datetime(2026, 10, 19, 7, 30, tzinfo=ZoneInfo("Europe/Stockholm"))
INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", (), "ALFA", "ALFA.ST", "Stockholm", sektor="industri"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm", sektor="fastigheter"),
    "GAMA": Instrument("Gammagruppen", (), "GAMA", "GAMA.ST", "Stockholm", sektor="industri"),
    "DELT": Instrument("Deltainvest", (), "DELT", "DELT.ST", "Stockholm", typ="investmentbolag"),
    "EPSI": Instrument("Epsilonindustri", (), "EPSI", "EPSI.ST", "Stockholm", sektor="industri"),
    "ZETA": Instrument("Zetabolaget", (), "ZETA", "ZETA.ST", "Stockholm", sektor="teknik"),
}


def bars(start_price, end_price, jump_on=None, jump=1.0):
    """Handelsdagar 15 dec 2025 – 16 okt 2026; linjär kurs, ev. ett hopp en viss dag."""
    out, d = [], date(2025, 12, 15)
    days = []
    while d <= date(2026, 10, 16):
        if d.weekday() < 5 and d != date(2025, 12, 31):
            days.append(d)
        d += timedelta(days=1)
    in_year = [d for d in days if d.year == 2026]
    for day in days:
        # Konstant kurs fram till årsskiftet, sedan linjärt till slutkursen.
        n = in_year.index(day) + 1 if day.year == 2026 else 0
        p = start_price + (end_price - start_price) * n / len(in_year)
        if jump_on and day >= jump_on:
            p *= jump
        out.append(Bar(day, p, p, p, p, 1000.0))
    return out


def eps_series(values):
    """Kvartalsrapporter, nyast först: (rapportdag, vinst per aktie)."""
    dates = [date(2026, 10, 15), date(2026, 7, 15), date(2026, 4, 20), date(2026, 2, 10),
             date(2025, 10, 15), date(2025, 7, 15), date(2025, 4, 22), date(2025, 2, 12)]
    return list(zip(dates, values))


def fetch_bars(_t, _s, _e):
    return {
        "^OMXSPI": bars(100, 110),
        "ALFA.ST": bars(100, 130),                 # +30 % i år
        "BETA.ST": bars(50, 45),
        "GAMA.ST": bars(80, 60, date(2026, 6, 8), 0.4),  # −60 % på en dag
        "DELT.ST": bars(200, 230),
        "EPSI.ST": bars(40, 44),
        "ZETA.ST": bars(10, 12),
    }


EPS = {
    "ALFA.ST": eps_series([1.2, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0]),   # 12 mån: 4,0 -> 4,5
    "BETA.ST": eps_series([1, 1, 1, 1, 1, 1, 1, 1]),
    "GAMA.ST": eps_series([1, 1, 1, 1, 1, 1, 1, 1]),
    "DELT.ST": eps_series([5, 5, 5, 5, 5, 5, 5, 5]),
    "EPSI.ST": eps_series([-0.5, 0.2, 0.1, 0.1, 0.3, 0.3, 0.3, 0.3]),  # förlust nu
    "ZETA.ST": [(date(2026, 10, 15), 1.0), (date(2026, 7, 15), 1.0)],   # för kort historik
}


def test_rullande_12_manader():
    s = eps_series([1.2, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert ttm(s, date(2026, 10, 18))[0] == 4.5
    assert ttm(s, date(2025, 12, 31))[0] == 4.0
    assert ttm(s, date(2027, 6, 1))[0] is None  # senaste rapporten för gammal
    gap = [x for x in s if x[0] != date(2026, 4, 20)]
    assert ttm(gap, date(2026, 10, 18))[0] is None  # lucka i serien


def test_status_och_varden():
    data = build(WEEK, INSTRUMENTS, fetch_bars, lambda t: EPS[t], {}, NOW, actions={})
    c = {x["ticker"]: x for x in data["companies"]}
    a = c["ALFA"]
    assert a["status"] == "ok" and a["ytd_pct"] == 30.0 and a["rel_index_pp"] == 20.0
    assert (a["eps_ttm_start"], a["eps_ttm_now"], a["eps_change_pct"]) == (4.0, 4.5, 12.5)
    assert (a["pe_start"], a["pe_now"], a["pe_change_pct"], a["verdict"]) == (25.0, 28.9, 15.6, "kursen före vinsten")
    assert c["BETA"]["status"] == "fastighetsbolag" and c["BETA"]["pe_now"] is None
    g = c["GAMA"]
    assert g["status"] == "kontrollera bolagshändelse" and g["ytd_pct"] is None and g["big_moves"][0]["date"] == "2026-06-08"
    assert c["DELT"]["status"] == "investmentbolag"
    assert c["EPSI"]["status"] == "förlust" and c["EPSI"]["pe_now"] is None
    assert c["ZETA"]["status"] == "otillräcklig vinsthistorik"
    assert validate_valuation(data, WEEK, INSTRUMENTS).errors == []


def test_annan_valuta_och_verifierad_bolagshandelse(tmp_path):
    actions = {"GAMA": [{"ticker": "GAMA", "ex_date": "2026-06-08", "factor": 0.4}]}
    data = build(WEEK, INSTRUMENTS, fetch_bars, lambda t: EPS[t], {"ALFA": "EUR"}, NOW, actions=actions)
    c = {x["ticker"]: x for x in data["companies"]}
    assert c["ALFA"]["status"] == "annan valuta" and c["ALFA"]["pe_now"] is None
    g = c["GAMA"]
    # Kurserna före ex-dagen justeras med faktorn: 80*0,4 = 32 -> 60*0,4 = 24 i slutet.
    assert g["status"] == "ok" and g["adjusted_ex_dates"] == ["2026-06-08"] and g["ytd_pct"] == -25.0
    # Valideringen kräver att justeringen finns i corporate_actions.json.
    p = tmp_path / "ca.json"
    p.write_text(json.dumps({"actions": []}), encoding="utf-8")
    assert any("verifierad" in e for e in validate_valuation(data, WEEK, INSTRUMENTS, p).errors)
    p.write_text(json.dumps({"actions": actions["GAMA"]}), encoding="utf-8")
    assert validate_valuation(data, WEEK, INSTRUMENTS, p).errors == []


def test_validering_raknar_om():
    data = build(WEEK, INSTRUMENTS, fetch_bars, lambda t: EPS[t], {}, NOW, actions={})
    c = {x["ticker"]: x for x in data["companies"]}
    c["ALFA"]["verdict"] = "i takt"
    c["GAMA"]["ytd_pct"] = -60.0
    errors = validate_valuation(data, WEEK, INSTRUMENTS).errors
    assert any("tolkningen" in e for e in errors)
    assert any("Gammagruppen" in e and "trots status" in e for e in errors)


def test_kand_handelse_som_inte_gar_att_justera(tmp_path):
    known = {"GAMA": [{"label": "noterad i Stockholm 8 jun", "yahoo_dates": ["2026-06-08"]}]}
    data = build(WEEK, INSTRUMENTS, fetch_bars, lambda t: EPS[t], {}, NOW, actions={}, known=known)
    g = {x["ticker"]: x for x in data["companies"]}["GAMA"]
    assert (g["status"], g["event_label"], g["ytd_pct"], g["pe_now"]) == (
        "känd bolagshändelse", "noterad i Stockholm 8 jun", None, None)
    # Valideringen läser etiketten ur corporate_actions.json.
    p = tmp_path / "ca.json"
    p.write_text(json.dumps({"actions": [], "investigated": [
        {"ticker": "GAMA", "label": "noterad i Stockholm 8 jun", "yahoo_dates": ["2026-06-08"]}]}), encoding="utf-8")
    assert validate_valuation(data, WEEK, INSTRUMENTS, p).errors == []
    # Utan den utredda posten ska statusen vara "kontrollera bolagshändelse".
    p.write_text(json.dumps({"actions": [], "investigated": []}), encoding="utf-8")
    assert any("väntat 'kontrollera bolagshändelse'" in e for e in validate_valuation(data, WEEK, INSTRUMENTS, p).errors)
    # En känd händelse som bara täcker en av två stora dagar räcker inte.
    known2 = {"GAMA": [{"label": "x", "yahoo_dates": ["2026-01-01"]}]}
    g2 = {x["ticker"]: x for x in build(WEEK, INSTRUMENTS, fetch_bars, lambda t: EPS[t], {}, NOW, actions={},
                                         known=known2)["companies"]}["GAMA"]
    assert g2["status"] == "kontrollera bolagshändelse" and g2["event_label"] is None
