"""Tester för scripts/report_calendar.py och validate_calendar (påhittade bolag)."""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_calendar import build, classify, event_date, find_dates, REPORT_CONTEXT_RE  # noqa: E402
from validate import Instrument, validate_calendar  # noqa: E402

TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime(2026, 10, 19, 8, 10, tzinfo=TZ)
TODAY = NOW.date()
WEEK = "2026-W43"  # 19–25 okt

INSTRUMENTS = {
    "ALFA": Instrument("Alfaverken", ("Alfa",), "ALFA", "ALFA.ST", "Stockholm", mfn_slug="alfaverken"),
    "BETA": Instrument("Betabolaget", (), "BETA", "BETA.ST", "Stockholm"),
    "GAMA": Instrument("Gammagruppen", (), "GAMA", "GAMA.ST", "Stockholm"),
    "DELT": Instrument("Deltafastigheter", (), "DELT", "DELT.ST", "Stockholm"),
    "EPSI": Instrument("Epsilonindustri", (), "EPSI", "EPSI.ST", "Stockholm"),
}


def make_raw(tmp_path: Path, items: list[tuple[str, str, str, str, str]]) -> Path:
    """items: (vecka, källa, company-slug, publicerad, rubrik, brödtext) -> rådatamapp."""
    raw = tmp_path / "raw"
    by_week: dict[str, list] = {}
    for n, (week, source, company, published, title, body) in enumerate(items):
        path = f"{source}/{n}.txt"
        (raw / week / source).mkdir(parents=True, exist_ok=True)
        (raw / week / path).write_text(f"Rubrik: {title}\n---\n{body}\n", encoding="utf-8")
        by_week.setdefault(week, []).append({
            "id": str(n), "source": source, "url": f"https://mfn.example/{n}", "published": published,
            "title": title, "company": company, "path": path,
        })
    for week, entries in by_week.items():
        (raw / week / "index.json").write_text(json.dumps({"week": week, "items": entries}), encoding="utf-8")
    return raw


def test_datum_med_och_utan_ar_och_radbrytning():
    pub = date(2026, 10, 8)
    assert [d for _, d in find_dates("torsdagen den 22\noktober 2026 kl. 08:00", pub)] == [date(2026, 10, 22)]
    assert [d for _, d in find_dates("fredag den 23 oktober kl. 07:00", pub)] == [date(2026, 10, 23)]
    assert [d for _, d in find_dates("on October 22, 2026 at 09:00", pub)] == [date(2026, 10, 22)]
    # Utan år och före publiceringen: nästa år.
    assert [d for _, d in find_dates("den 15 januari", pub)] == [date(2027, 1, 15)]


def test_rapportperioden_ar_inget_datum():
    pub = date(2026, 10, 8)
    assert find_dates("Delårsrapport 1 januari - 30 september", pub) == []
    assert find_dates("delårsrapport 1 januari–30 september 2026", pub) == []


def test_pressmeddelandets_eget_datum_valjs_inte():
    body = "Pressmeddelande\n\n15 oktober 2026\n\nBolaget publicerar sin delårsrapport fredag den 23 oktober kl. 07:00."
    assert event_date("Inbjudan till rapportpresentation", body, date(2026, 10, 15), REPORT_CONTEXT_RE) == date(2026, 10, 23)


def test_datum_nara_rapportord_gar_fore_forsta_datumet():
    body = "Anmäl dig senast 20 oktober. Rapporten publiceras den 28 oktober 2026 kl. 07.30."
    assert event_date("Inbjudan", body, date(2026, 10, 10), REPORT_CONTEXT_RE) == date(2026, 10, 28)


def test_datum_i_rubriken_gar_forst():
    assert event_date("Inbjudan till presentation av bokslutet den 14 oktober", "den 20 oktober", date(2026, 10, 6),
                      REPORT_CONTEXT_RE) == date(2026, 10, 14)


def test_klassning_av_rubriker():
    assert classify("Inbjudan till presentation av delårsrapport Q3") == "rapport"
    assert classify("Invitation to conference call for the third quarter report") == "rapport"
    assert classify("Kallelse till extra bolagsstämma i Alfaverken AB") == "stämma"
    assert classify("Inbjudan: Alfaverkens kapitalmarknadsdag 2026") is None
    assert classify("Alfaverken förvärvar bolag") is None


def _events(data):
    return {(e["ticker"], e["kind"]): e for e in data["events"]}


def test_status_per_rapport(tmp_path):
    raw = make_raw(tmp_path, [
        # Alfaverken: MFN 22 okt (via mfn_slug), Yahoo 22 okt -> bekräftat.
        ("2026-W41", "mfn", "alfaverken", "2026-10-08T08:00:00+02:00", "Inbjudan till presentation av Q3-rapport",
         "Rapporten publiceras den 22 oktober 2026."),
        # Betabolaget: MFN 23 okt (namn i rubriken), Yahoo 21 okt -> avvikelse.
        ("2026-W42", "cision", "beta-ab", "2026-10-13T08:00:00+02:00",
         "Betabolaget: Inbjudan till presentation av delårsrapport", "Delårsrapporten publiceras den 23 oktober 2026."),
        # Gammagruppen: bara MFN.
        ("2026-W42", "mfn", "gammagruppen", "2026-10-14T08:00:00+02:00",
         "Inbjudan till Gammagruppens rapport för tredje kvartalet", "Rapporten kommer den 20 oktober 2026."),
        # Deltafastigheter: MFN-datum som redan passerats räknas inte -> bara Yahoo.
        ("2026-W41", "mfn", "delta", "2026-10-05T08:00:00+02:00",
         "Deltafastigheter: Inbjudan till presentation av delårsrapport", "Rapporten publiceras den 9 oktober 2026."),
        # Epsilonindustri: stämma.
        ("2026-W42", "mfn", "epsilon", "2026-10-12T08:00:00+02:00", "Kallelse till extra bolagsstämma i Epsilonindustri",
         "Aktieägarna kallas till extra bolagsstämma den 24 oktober 2026."),
    ])
    yahoo = {"ALFA.ST": [date(2026, 10, 22)], "BETA.ST": [date(2026, 10, 21)], "DELT.ST": [date(2026, 10, 24)]}
    data = build(WEEK, raw, INSTRUMENTS, TODAY, NOW, lambda t: yahoo.get(t, []))
    ev = _events(data)
    assert ev[("ALFA", "rapport")]["status"] == "bekräftat"
    beta = ev[("BETA", "rapport")]
    assert (beta["status"], beta["date"], beta["yahoo_date"], beta["mfn_date"]) == \
        ("avvikelse", "2026-10-21", "2026-10-21", "2026-10-23")
    assert ev[("GAMA", "rapport")]["status"] == "mfn"
    delt = ev[("DELT", "rapport")]
    assert (delt["status"], delt["mfn_date"]) == ("yahoo", None)
    assert ev[("EPSI", "stämma")]["status"] == "mfn"
    assert [e["date"] for e in data["events"]] == sorted(e["date"] for e in data["events"])
    assert validate_calendar(data, WEEK, INSTRUMENTS, raw).errors == []


def test_avvikelse_nar_mfn_datumet_ligger_utanfor_veckan(tmp_path):
    raw = make_raw(tmp_path, [
        ("2026-W42", "mfn", "alfaverken", "2026-10-13T08:00:00+02:00", "Inbjudan till presentation av Q3-rapport",
         "Rapporten publiceras den 28 oktober 2026."),
    ])
    data = build(WEEK, raw, INSTRUMENTS, TODAY, NOW, lambda t: [date(2026, 10, 22)] if t == "ALFA.ST" else [])
    alfa = _events(data)[("ALFA", "rapport")]
    assert (alfa["status"], alfa["date"], alfa["mfn_date"]) == ("avvikelse", "2026-10-22", "2026-10-28")


def test_yahoo_fel_stoppar_inte_resten(tmp_path):
    raw = make_raw(tmp_path, [])

    def flaky(ticker):
        if ticker == "BETA.ST":
            raise ConnectionError("timeout")
        return [date(2026, 10, 22)] if ticker == "ALFA.ST" else []

    data = build(WEEK, raw, INSTRUMENTS, TODAY, NOW, flaky)
    assert data["errors"] == ["BETA.ST: ConnectionError"]
    assert list(_events(data)) == [("ALFA", "rapport")]


def _valid_event(**overrides):
    e = {"date": "2026-10-22", "kind": "rapport", "ticker": "ALFA", "yahoo_ticker": "ALFA.ST", "name": "Alfaverken",
         "status": "yahoo", "yahoo_date": "2026-10-22", "mfn_date": None, "mfn_url": None, "mfn_title": None}
    return {**e, **overrides}


def _calendar(*events):
    return {"schema_version": 1, "week": WEEK, "period": {"start": "2026-10-19", "end": "2026-10-25"},
            "generated_at": NOW.isoformat(), "events": list(events), "errors": []}


def test_validering_underkanner_fel(tmp_path):
    raw = make_raw(tmp_path, [("2026-W42", "mfn", "x", "2026-10-13T08:00:00+02:00", "Annan nyhet", "Text.")])
    ok = validate_calendar(_calendar(_valid_event()), WEEK, INSTRUMENTS, raw)
    assert ok.errors == []
    cases = [
        (_valid_event(date="2026-10-26", yahoo_date="2026-10-26"), "utanför veckan"),
        (_valid_event(status="bekräftat"), "stämmer inte med datumen"),
        (_valid_event(ticker="OKAND", yahoo_ticker="OKAND.ST"), "instruments.csv"),
        (_valid_event(status="mfn", yahoo_date=None, mfn_date="2026-10-22", mfn_url="https://mfn.example/finns-ej",
                      mfn_title="Inbjudan"), "finns inte i rådatan"),
        (_valid_event(kind="stämma", status="yahoo"), "bara från MFN"),
    ]
    for event, message in cases:
        errors = validate_calendar(_calendar(event), WEEK, INSTRUMENTS, raw).errors
        assert any(message in e for e in errors), (message, errors)
    dup = validate_calendar(_calendar(_valid_event(), _valid_event()), WEEK, INSTRUMENTS, raw).errors
    assert any("dubblett" in e for e in dup)
