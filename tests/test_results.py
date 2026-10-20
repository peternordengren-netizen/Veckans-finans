"""Tester för rapportutfall: scripts/report_list.py, scripts/validate_results.py och scripts/results.py
(påhittade bolag och rapporttexter)."""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import results  # noqa: E402
from report_list import is_report_title, list_reports  # noqa: E402
from validate import Instrument, Result, _normalize_ws, load_sector_kpis  # noqa: E402
from validate_results import check_kpi, period_before, surprise_pct, validate_batch, validate_results, verdict  # noqa: E402

WEEK = "2026-W43"
NOW = datetime(2026, 10, 26, 7, 30, tzinfo=ZoneInfo("Europe/Stockholm"))
INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", (), "ALFA", "ALFA.ST", "Stockholm", mfn_slug="alfaverken", sektor="industri"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm", sektor="fastigheter"),
}

ALFA_TEXT = """Rubrik: Alfaverken delårsrapport januari-september 2026
---
Delårsrapport januari - september 2026

Juli - september 2026
* Orderingången ökade med 12 % till 1 344 MSEK (1 200)
* Nettoomsättningen uppgick till 1 500 MSEK (1 400)
* Rörelsemarginalen var 11,2 % (10,5)
* Resultat per aktie ökade med 25 % till 2,50 SEK (2,00)

Januari - september 2026
* Nettoomsättningen uppgick till 4 300 MSEK (4 000)
* Resultat per aktie uppgick till 7,10 SEK (6,00)
"""


def make_raw(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    (raw / WEEK / "mfn").mkdir(parents=True)
    (raw / WEEK / "mfn" / "alfa.txt").write_text(ALFA_TEXT, encoding="utf-8")
    (raw / WEEK / "mfn" / "beta.txt").write_text("Rubrik: x\n---\nInga siffror i utdraget.\n", encoding="utf-8")
    items = [
        {"source": "mfn", "source_name": "MFN", "url": "https://mfn.example/alfa", "published": "2026-10-22T07:00:00+02:00",
         "title": "Alfaverken delårsrapport januari-september 2026", "company": "alfaverken", "path": "mfn/alfa.txt",
         "text_kind": "fulltext"},
        {"source": "mfn", "source_name": "MFN", "url": "https://mfn.example/beta-datum", "published": "2026-10-19T08:00:00+02:00",
         "title": "Betabolaget publicerar delårsrapport den 30 oktober", "company": "betabolaget", "path": "mfn/x.txt"},
        {"source": "mfn", "source_name": "MFN", "url": "https://mfn.example/beta", "published": "2026-10-23T07:00:00+02:00",
         "title": "Betabolaget: Delårsrapport Q3 2026", "company": "betabolaget", "path": "mfn/beta.txt",
         "text_kind": "fulltext"},
    ]
    (raw / WEEK / "index.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    return raw


def kpi(id_, value, unit, prev, change, period, quote):
    return {"id": id_, "value": value, "unit": unit, "previous_value": prev, "change_pct": change,
            "period_kind": period, "quote": quote}


GOOD_KPIS = [
    kpi("orderingang", 1344, "MSEK", 1200, 12, "kvartal", "Orderingången ökade med 12 % till 1 344 MSEK (1 200)"),
    kpi("rorelsemarginal", 11.2, "procent", 10.5, None, "kvartal", "Rörelsemarginalen var 11,2 % (10,5)"),
    kpi("nettoomsattning", 1500, "MSEK", 1400, None, "kvartal", "Nettoomsättningen uppgick till 1 500 MSEK (1 400)"),
    kpi("resultat-per-aktie", 2.5, "SEK", 2.0, 25, "kvartal", "Resultat per aktie ökade med 25 % till 2,50 SEK (2,00)"),
]


def batch(reports):
    return {"week": WEEK, "batch": 1, "reports": reports}


def alfa(kpis=GOOD_KPIS):
    return {"ticker": "ALFA", "raw_file": "mfn/alfa.txt", "period": "Q3 2026", "note": None, "kpis": kpis}


def beta():
    return {"ticker": "BETA", "raw_file": "mfn/beta.txt", "period": "Q3 2026", "note": "utdrag utan siffror", "kpis": []}


def test_rapportrubriker():
    d = date(2026, 10, 19)
    assert is_report_title("Delårsrapport Q3 2026", d)
    assert is_report_title("Atlas: Rapport för tredje kvartalet 2026 och inbjudan till telefonkonferens", d)
    assert not is_report_title("Inbjudan till presentation av delårsrapport", d)
    assert not is_report_title("Bolaget publicerar delårsrapport den 30 oktober", d)
    # Rubriker utan ordet "rapport" (2026-10-20 missades två sådana)
    assert is_report_title("Resultat tredje kvartalet 2026", d)
    assert is_report_title("Alfaverken rapporterar resultat för tredje kvartalet 2026: starkt kassaflöde", d)
    assert not is_report_title("Alfaverken publicerar resultat för tredje kvartalet den 30 oktober", d)
    assert not is_report_title("Alfaverken: preliminärt resultat för tredje kvartalet 2026", d)
    assert not is_report_title("Inbjudan till presentation av resultat för tredje kvartalet", d)


def test_lista_hoppar_over_datumbesked(tmp_path):
    raw = make_raw(tmp_path)
    reports = list_reports(raw, WEEK, INSTRUMENTS, load_sector_kpis())
    assert [r["ticker"] for r in reports] == ["ALFA", "BETA"]
    assert reports[0]["kpis"] == ["orderingang", "rorelsemarginal", "nettoomsattning", "resultat-per-aktie"]
    assert reports[1]["kpis"][0] == "forvaltningsresultat-per-aktie"


def test_period_fore_citatet():
    text = _normalize_ws(ALFA_TEXT)
    assert period_before(text, text.find("Orderingången")) == "kvartal"
    assert period_before(text, text.find("Resultat per aktie uppgick till 7,10")) == "delår"
    assert period_before("Helåret 2026: Omsättning 5 MSEK (4)", 15) == "helår"
    assert period_before("Ingen period här", 10) is None


def test_godkant_nyckeltal_och_fel():
    text = _normalize_ws(ALFA_TEXT)

    def errors(k, kind="belopp"):
        r = Result()
        check_kpi(k, kind, text, "t", r)
        return r.errors

    assert errors(GOOD_KPIS[0]) == []
    assert errors(GOOD_KPIS[1], "procent") == []
    assert errors(GOOD_KPIS[3], "per_aktie") == []
    cases = [
        ({**GOOD_KPIS[0], "quote": "Orderingången ökade kraftigt"}, "belopp", "finns inte i rapporttexten"),
        ({**GOOD_KPIS[0], "value": 1345}, "belopp", "värdet 1345"),
        ({**GOOD_KPIS[0], "previous_value": 1100}, "belopp", "föregående års värde 1100"),
        ({**GOOD_KPIS[0], "previous_value": None, "change_pct": None}, "belopp", "varken"),
        ({**GOOD_KPIS[0], "unit": "procent"}, "belopp", "enheten"),
        ({**GOOD_KPIS[1], "change_pct": 6.7}, "procent", "procenttal"),
        # Delårets siffror angivna som kvartal.
        (kpi("nettoomsattning", 4300, "MSEK", 4000, None, "kvartal", "Nettoomsättningen uppgick till 4 300 MSEK (4 000)"),
         "belopp", "delårsangivelse"),
    ]
    for k, kind, msg in cases:
        errs = errors(k, kind)
        assert any(msg in e for e in errs), (msg, errs)


def test_forandring_som_inte_stammer_med_vardena():
    text = "Juli - september 2026: Vinsten ökade med 40 % till 1 344 MSEK (1 200)"
    r = Result()
    check_kpi(kpi("orderingang", 1344, "MSEK", 1200, 40, "kvartal", text.split(": ")[1]), "belopp", text, "t", r)
    assert any("stämmer inte med värdena" in e for e in r.errors)


def test_omgang_maste_tacka_listan(tmp_path):
    raw = make_raw(tmp_path)
    assert validate_batch(batch([alfa(), beta()]), WEEK, 1, INSTRUMENTS, raw).errors == []
    errs = validate_batch(batch([alfa()]), WEEK, 1, INSTRUMENTS, raw).errors
    assert any("BETA: rapporten saknas" in e for e in errs)
    other = {**beta(), "ticker": "GAMA"}
    errs = validate_batch(batch([alfa(), beta(), other]), WEEK, 1, INSTRUMENTS, raw).errors
    assert any("GAMA" in e for e in errs)
    errs = validate_batch(batch([alfa(), {**beta(), "note": None}]), WEEK, 1, INSTRUMENTS, raw).errors
    assert any("ingen förklaring" in e for e in errs)


def test_avvikelse_och_bedomning():
    assert surprise_pct(2.5, 2.0) == 25
    assert surprise_pct(-0.5, -1.0) == 50  # mindre förlust än väntat är bättre
    assert verdict(1.9) == "i linje" and verdict(2.1) == "över" and verdict(-3) == "under"


def test_sammanslagning_med_konsensus(tmp_path):
    raw = make_raw(tmp_path)
    results_dir, cons_dir = tmp_path / "results", tmp_path / "consensus"
    (results_dir / WEEK).mkdir(parents=True)
    (results_dir / WEEK / "omgang-1.json").write_text(json.dumps(batch([alfa(), beta()])), encoding="utf-8")
    cons_dir.mkdir()
    est = lambda avg, ccy="SEK": {"avg": avg, "low": None, "high": None, "analysts": 4, "year_ago": None, "currency": ccy}  # noqa: E731
    snap = lambda d, nxt: {"date": d, "companies": [{"ticker": "ALFA", "eps": est(2.4), "revenue": est(1.6e9),  # noqa: E731
                                                     "next_report_date": nxt}]}
    # Ögonblicksbilden samma dag som rapporten används inte; dagen före gör det.
    (cons_dir / "2026-10-21.json").write_text(json.dumps(snap("2026-10-21", "2026-10-22")), encoding="utf-8")
    (cons_dir / "2026-10-22.json").write_text(json.dumps(snap("2026-10-22", "2027-01-25")), encoding="utf-8")
    data, problems = results.build(WEEK, INSTRUMENTS, NOW, raw, results_dir, cons_dir)
    assert problems == []
    a = next(r for r in data["reports"] if r["ticker"] == "ALFA")
    assert [k["id"] for k in a["kpis"]] == ["orderingang", "rorelsemarginal", "nettoomsattning", "resultat-per-aktie"]
    assert (a["kpis"][2]["change_pct"], a["kpis"][2]["yoy_pct"]) == (None, 7.1)  # räknat ur 1 500 / 1 400
    assert a["kpis"][0]["yoy_pct"] == 12  # rapportens egen siffra
    assert a["kpis"][1]["yoy_pct"] is None  # procenttal
    c = a["vs_consensus"]
    assert c["consensus_date"] == "2026-10-21"
    assert (c["eps"]["surprise_pct"], c["eps"]["verdict"]) == (4.2, "över")
    assert (c["revenue"]["actual"], c["revenue"]["surprise_pct"], c["revenue"]["verdict"]) == (1.5e9, -6.2, "under")
    assert validate_results(data, WEEK, INSTRUMENTS, raw).errors == []
    a["kpis"][2]["yoy_pct"] = 8.0
    assert any("yoy_pct" in e for e in validate_results(data, WEEK, INSTRUMENTS, raw).errors)
    a["kpis"][2]["yoy_pct"] = 7.1
    c["eps"]["verdict"] = "under"
    assert any("bedömningen" in e for e in validate_results(data, WEEK, INSTRUMENTS, raw).errors)


def test_validate_py_valjer_resultatvalideringen_for_morgonfiler(tmp_path, monkeypatch):
    """validate.py ska känna igen morgonens omgångar och sammanslagna fil (2026-10-20 validerades
    omgången som en veckofil, så en godkänd omgång kördes alltid om)."""
    import validate
    import validate_results

    calls = []
    monkeypatch.setattr(validate_results, "validate_batch", lambda d, scope, n, i: calls.append(("omgång", scope, n)) or Result())
    monkeypatch.setattr(validate_results, "validate_results", lambda d, scope, i: calls.append(("fil", scope)) or Result())
    paths = [tmp_path / "results" / "morning" / "2026-10-20" / "omgang-1.json",
             tmp_path / "results" / "morning" / "2026-10-20.json",
             tmp_path / "results" / "2026-W43" / "omgang-2.json",
             tmp_path / "results" / "2026-W43.json"]
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
    assert validate.main([str(p) for p in paths]) == 0
    assert calls == [("omgång", "2026-10-20", 1), ("fil", "2026-10-20"), ("omgång", "2026-W43", 2), ("fil", "2026-W43")]


def test_osaker_konsensus_ger_ingen_bedomning(tmp_path):
    """Förväntad förändring över ±50 % mot fjol från färre än 3 analytiker: "osäker konsensus"
    i stället för över/under, för båda jämförelserna."""
    raw = make_raw(tmp_path)
    results_dir, cons_dir = tmp_path / "results", tmp_path / "consensus"
    (results_dir / WEEK).mkdir(parents=True)
    (results_dir / WEEK / "omgang-1.json").write_text(json.dumps(batch([alfa(), beta()])), encoding="utf-8")
    cons_dir.mkdir()
    eps = {"avg": 2.4, "low": None, "high": None, "analysts": 1, "year_ago": 1.2, "currency": "SEK"}  # +100 %
    rev = {"avg": 1.6e9, "low": None, "high": None, "analysts": 8, "year_ago": 1.5e9, "currency": "SEK"}
    snap = {"date": "2026-10-21", "companies": [{"ticker": "ALFA", "eps": eps, "revenue": rev,
                                                 "next_report_date": "2026-10-22"}]}
    (cons_dir / "2026-10-21.json").write_text(json.dumps(snap), encoding="utf-8")
    data, _ = results.build(WEEK, INSTRUMENTS, NOW, raw, results_dir, cons_dir)
    c = next(r for r in data["reports"] if r["ticker"] == "ALFA")["vs_consensus"]
    assert c["uncertain"] is True
    assert (c["eps"]["verdict"], c["revenue"]["verdict"]) == ("osäker konsensus", "osäker konsensus")
    assert c["eps"]["surprise_pct"] == 4.2  # avvikelsen sparas men visas inte
    assert validate_results(data, WEEK, INSTRUMENTS, raw, consensus_dir=cons_dir).errors == []
    # Över/under trots varningen underkänns, liksom en flagga som inte stämmer med konsensusbilden.
    c["eps"]["verdict"] = "över"
    assert any("bedömningen" in e for e in validate_results(data, WEEK, INSTRUMENTS, raw, consensus_dir=cons_dir).errors)
    c["eps"]["verdict"], c["revenue"]["verdict"], c["uncertain"] = "över", "under", False
    assert any("uncertain" in e for e in validate_results(data, WEEK, INSTRUMENTS, raw, consensus_dir=cons_dir).errors)
    # Med tre analytiker är konsensus inte osäker.
    eps["analysts"] = 3
    (cons_dir / "2026-10-21.json").write_text(json.dumps(snap), encoding="utf-8")
    data, _ = results.build(WEEK, INSTRUMENTS, NOW, raw, results_dir, cons_dir)
    c = next(r for r in data["reports"] if r["ticker"] == "ALFA")["vs_consensus"]
    assert (c["uncertain"], c["eps"]["verdict"]) == (False, "över")


def test_saknad_omgang_listas(tmp_path):
    raw = make_raw(tmp_path)
    data, problems = results.build(WEEK, INSTRUMENTS, NOW, raw, tmp_path / "results", tmp_path / "consensus")
    assert data["missing_batches"] == [1] and problems == ["omgång 1 saknas"]


def test_period_inne_i_citatet():
    text = _normalize_ws("Januari - september 2026\nResultat per aktie uppgick till +12,93 (+7,45) för hela perioden "
                         "och för kvartalet till -1,13 (+1,70).")
    quote = "Resultat per aktie uppgick till +12,93 (+7,45) för hela perioden och för kvartalet till -1,13 (+1,70)"
    r = Result()
    check_kpi(kpi("resultat-per-aktie", -1.13, "SEK", 1.70, None, "kvartal", quote), "per_aktie", text, "t", r)
    assert r.errors == []
    r = Result()
    check_kpi(kpi("resultat-per-aktie", 12.93, "SEK", 7.45, None, "kvartal", quote), "per_aktie", text, "t", r)
    assert any("delårsangivelse" in e for e in r.errors)


def _alfa_snapshot(d, nxt="2026-10-22", after=False):
    est = {"avg": 2.4, "low": None, "high": None, "analysts": 4, "year_ago": None, "currency": "SEK"}
    return {"date": d, "companies": [{"ticker": "ALFA", "eps": est, "revenue": None, "next_report_date": nxt,
                                      "after_report": after}]}


def test_konsensus_samma_dag_eller_efter_rapport_anvands_aldrig(tmp_path):
    report = {"ticker": "ALFA", "kpis": [GOOD_KPIS[3]]}
    cons = tmp_path / "consensus"
    cons.mkdir()
    published = date(2026, 10, 22)
    # Bara en bild samma dag som rapporten: ingen jämförelse.
    (cons / "2026-10-22.json").write_text(json.dumps(_alfa_snapshot("2026-10-22")), encoding="utf-8")
    assert results.vs_consensus(report, published, cons) is None
    # Bild dagen före, men bolaget hade redan rapporterat när den togs: ingen jämförelse.
    (cons / "2026-10-21.json").write_text(json.dumps(_alfa_snapshot("2026-10-21", after=True)), encoding="utf-8")
    assert results.vs_consensus(report, published, cons) is None
    # Bild dagen före utan after_report: jämförs.
    (cons / "2026-10-21.json").write_text(json.dumps(_alfa_snapshot("2026-10-21")), encoding="utf-8")
    assert results.vs_consensus(report, published, cons)["consensus_date"] == "2026-10-21"


def _morning_setup(tmp_path):
    """Actions- och morgonrådata med samma rapport i båda, och ett fönster för 22 okt."""
    from report_list import create_window

    raw = make_raw(tmp_path)
    morning_raw = tmp_path / "morning-raw"
    (morning_raw / WEEK / "mfn").mkdir(parents=True)
    (morning_raw / WEEK / "mfn" / "alfa.txt").write_text(ALFA_TEXT, encoding="utf-8")
    item = {"id": "alfa-1", "source": "mfn", "source_name": "MFN", "url": "https://mfn.example/alfa",
            "published": "2026-10-22T07:00:00+02:00", "title": "Alfaverken delårsrapport januari-september 2026",
            "company": "alfaverken", "path": "mfn/alfa.txt", "text_kind": "fulltext"}
    (morning_raw / WEEK / "index.json").write_text(json.dumps({"items": [item]}), encoding="utf-8")
    results_dir = tmp_path / "results"
    tz = ZoneInfo("Europe/Stockholm")
    create_window("2026-10-22", datetime(2026, 10, 22, 8, 10, tzinfo=tz), results_dir)
    return raw, morning_raw, results_dir


def test_dagslage_fonster_och_dubbletter(tmp_path):
    from report_list import list_scope, load_window

    raw, morning_raw, results_dir = _morning_setup(tmp_path)
    since, until = load_window("2026-10-22", results_dir)
    assert since.isoformat() == "2026-10-21T08:10:00+02:00"  # förra handelsdagen 08:10
    listed = list_scope("2026-10-22", INSTRUMENTS, load_sector_kpis(), raw, morning_raw, results_dir)
    # Alfaverken 07:00 (finns i båda rådatamapparna, räknas en gång); Betabolaget 23 okt ligger efter fönstret.
    assert [r["ticker"] for r in listed] == ["ALFA"]
    ok = {"week": "2026-10-22", "batch": 1, "reports": [alfa()]}
    assert validate_batch(ok, "2026-10-22", 1, INSTRUMENTS, raw, morning_raw, results_dir).errors == []


def test_nasta_fonster_borjar_dar_forra_slutade(tmp_path):
    from report_list import create_window

    tz = ZoneInfo("Europe/Stockholm")
    d = tmp_path / "results"
    create_window("2026-10-22", datetime(2026, 10, 22, 9, 30, tzinfo=tz), d)
    since, _ = create_window("2026-10-23", datetime(2026, 10, 23, 8, 10, tzinfo=tz), d)
    assert since.isoformat() == "2026-10-22T09:30:00+02:00"
    # Ett befintligt fönster ändras aldrig.
    again = create_window("2026-10-23", datetime(2026, 10, 23, 15, 0, tzinfo=tz), d)
    assert again[1].isoformat() == "2026-10-23T08:10:00+02:00"


def test_veckan_hoppar_over_morgonens_bolag_och_tar_med_dem(tmp_path):
    from report_list import list_scope

    raw, morning_raw, results_dir = _morning_setup(tmp_path)
    (results_dir / "morning" / "2026-10-22").mkdir(parents=True, exist_ok=True)
    (results_dir / "morning" / "2026-10-22" / "omgang-1.json").write_text(
        json.dumps({"week": "2026-10-22", "batch": 1, "reports": [alfa()]}), encoding="utf-8")
    tz = ZoneInfo("Europe/Stockholm")
    day, _ = results.build("2026-10-22", INSTRUMENTS, datetime(2026, 10, 22, 8, 15, tzinfo=tz), raw, results_dir,
                           tmp_path / "consensus", morning_raw)
    assert [r["scope"] for r in day["reports"]] == ["2026-10-22"]
    (results_dir / "morning" / "2026-10-22.json").write_text(json.dumps(day), encoding="utf-8")
    week_list = list_scope(WEEK, INSTRUMENTS, load_sector_kpis(), raw, morning_raw, results_dir)
    assert [r["ticker"] for r in week_list] == ["BETA"]  # Alfaverken klarades redan på morgonen
    (results_dir / WEEK).mkdir()
    (results_dir / WEEK / "omgang-1.json").write_text(json.dumps(batch([beta()])), encoding="utf-8")
    week, problems = results.build(WEEK, INSTRUMENTS, NOW, raw, results_dir, tmp_path / "consensus", morning_raw)
    assert problems == []
    assert [(r["ticker"], r["scope"]) for r in week["reports"]] == [("ALFA", "2026-10-22"), ("BETA", WEEK)]
    assert validate_results(week, WEEK, INSTRUMENTS, raw, morning_raw, results_dir).errors == []
