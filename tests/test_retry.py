"""Tester för scripts/retry.py och att skripten gör nya försök mot Yahoo."""

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from retry import retry_missing, with_retries  # noqa: E402


def flaky(failures, value="ok", exc=KeyError):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc("tillfälligt")
        return value

    return fn, calls


def test_lyckas_efter_tva_misslyckade_forsok_och_loggar():
    log, sleeps = [], []
    fn, calls = flaky(2)
    assert with_retries(fn, "VICO.ST (vinsthistorik)", pause=2, sleep=sleeps.append, log=log.append) == "ok"
    assert calls["n"] == 3 and sleeps == [2, 2]
    assert log == [
        "[försök 1/3] VICO.ST (vinsthistorik): KeyError – nytt försök om 2 s",
        "[försök 2/3] VICO.ST (vinsthistorik): KeyError – nytt försök om 2 s",
        "[försök 3/3] VICO.ST (vinsthistorik): lyckades",
    ]


def test_ger_upp_efter_tre_forsok():
    log = []
    fn, calls = flaky(5, exc=ConnectionError)
    with pytest.raises(ConnectionError):
        with_retries(fn, "X", sleep=lambda s: None, log=log.append)
    assert calls["n"] == 3 and log[-1] == "[försök 3/3] X: ConnectionError – ger upp"


def test_inget_loggas_nar_forsta_forsoket_lyckas():
    log = []
    assert with_retries(lambda: 1, "X", sleep=lambda s: None, log=log.append) == 1
    assert log == []


def test_batch_hamtar_om_det_som_saknas():
    rounds, log = [], []

    def fetch(keys):
        rounds.append(list(keys))
        # A kommer direkt, B först i andra omgången, C aldrig.
        return {k: len(rounds) for k in keys if k == "A" or (k == "B" and len(rounds) >= 2)}

    out = retry_missing(fetch, ["A", "B", "C"], "kursdata", sleep=lambda s: None, log=log.append)
    assert out == {"A": 1, "B": 2}
    assert rounds == [["A", "B", "C"], ["B", "C"], ["C"]]
    assert log[-1] == "kursdata: saknas efter 3 försök: C"


def test_valuation_gor_nya_forsok_for_vinsthistoriken():
    from test_valuation import EPS, INSTRUMENTS, NOW, WEEK, fetch_bars
    from valuation import build

    calls = {}

    def flaky_eps(t):
        calls[t] = calls.get(t, 0) + 1
        if t == "ALFA.ST" and calls[t] == 1:
            raise KeyError("tillfälligt")
        return EPS[t]

    data = build(WEEK, INSTRUMENTS, fetch_bars, flaky_eps, {}, NOW, actions={}, known={}, listings={})
    assert data["errors"] == [] and calls["ALFA.ST"] == 2
    assert {c["ticker"]: c for c in data["companies"]}["ALFA"]["status"] == "ok"


def test_konsensus_registrerar_fel_forst_efter_tre_forsok():
    from test_consensus import INSTRUMENTS, NOW, fake
    from consensus import build

    calls = {"n": 0}

    def always_fails_beta(t):
        if t == "BETA.ST":
            calls["n"] += 1
        return fake(t)

    data = build(date(2026, 10, 19), NOW, INSTRUMENTS, always_fails_beta)
    assert calls["n"] == 3 and data["errors"] == ["BETA.ST: ConnectionError"]


def test_tomt_svar_gors_om_och_raknas_inte_som_fel():
    from test_valuation import EPS, INSTRUMENTS, NOW, WEEK, fetch_bars
    from valuation import NoEpsData, build

    calls = {}

    def eps(t):
        calls[t] = calls.get(t, 0) + 1
        if t == "ALFA.ST" and calls[t] == 1:
            raise NoEpsData(t)  # tillfälligt tomt svar
        if t == "ZETA.ST":
            raise NoEpsData(t)  # saknas varje gång
        return EPS[t]

    data = build(WEEK, INSTRUMENTS, fetch_bars, eps, {}, NOW, actions={}, known={}, listings={})
    c = {x["ticker"]: x for x in data["companies"]}
    assert calls["ALFA.ST"] == 2 and c["ALFA"]["status"] == "ok"
    assert calls["ZETA.ST"] == 3 and c["ZETA"]["status"] == "otillräcklig vinsthistorik"
    assert data["errors"] == []
