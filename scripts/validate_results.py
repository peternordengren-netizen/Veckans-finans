"""Validering av rapportutfall: omgångsfiler från /rapportutfall och den sammanslagna filen
från scripts/results.py.

Samma princip som för nyheterna – Claude skriver, valideringen kontrollerar mot källtexten:
- bara bolagen och rapportfilerna som scripts/report_list.py listar för omgången, alla med
- bara bolagets nyckeltal (sektorns plus omsättning och resultat per aktie)
- citatet: högst 25 ord och ordagrant i rapporttexten (efter normalisering av mellanslag)
- årets värde, föregående års värde och en eventuell procentsats finns som tal i citatet
- förändringen i procent stämmer med värdena (±1,5 procentenheter för avrundning)
- enheten passar nyckeltalets typ (belopp, procent, per aktie …)
- perioden: närmaste periodangivelse före citatet i rapporten ("juli–september",
  "tredje kvartalet", "januari–september" …) ska vara samma sorts period som uppgetts
  (kvartal, delår eller helår), så att kvartalets siffror inte blandas med årets hittills
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from validate import (
    DATA_DIR, RAW_DIR, Instrument, Result, _check_datetime, _normalize_ws, _schema_errors, _schema_validator,
    extract_numbers, iso_week_period, load_sector_kpis,
)

MAX_QUOTE_WORDS = 25
CHANGE_TOLERANCE_PP = 1.5
PERIOD_LOOKBACK_CHARS = 2500

CURRENCIES = {"SEK", "EUR", "USD", "DKK", "NOK"}
SCALES = {"T": Decimal(1_000), "M": Decimal(1_000_000), "MD": Decimal(1_000_000_000)}
UNIT_KINDS = {
    "belopp": {f"{s}{c}" for s in SCALES for c in CURRENCIES} | CURRENCIES,
    "per_aktie": CURRENCIES,
    "procent": {"procent"},
    "volym": {"ton", "kton", "Mton", "st", "MWh", "GWh", "TWh", "boe", "kboe", "oz", "koz"},
    "pris": {f"{c}/{u}" for c in CURRENCIES | {f"T{c}" for c in CURRENCIES} for u in ("ton", "oz", "MWh", "boe", "kg")},
}


# Per aktie i hundradelar, som rapporten skriver det: "Euro cent", "EUR cent", "US cent", "öre" …
# (Hexagon 2026-10-23). Jämförs efter att mellanslag tagits bort och små bokstäver.
CENT_UNITS = {"eurocent": "EUR", "eurocents": "EUR", "eurcent": "EUR", "eurcents": "EUR", "usdcent": "USD",
              "usdcents": "USD", "uscent": "USD", "uscents": "USD", "öre": "SEK", "nokøre": "NOK", "dkkøre": "DKK"}


def cent_currency(unit: str) -> str | None:
    """'Euro cent' -> 'EUR', 'öre' -> 'SEK'; övriga -> None."""
    return CENT_UNITS.get(re.sub(r"\s+", "", unit).casefold())


def unit_factor(unit: str) -> tuple[Decimal, str] | None:
    """'MSEK' -> (1 000 000, 'SEK'); 'SEK' -> (1, 'SEK'); 'Euro cent' -> (0,01, 'EUR');
    övriga (procent, ton …) -> None."""
    if unit in CURRENCIES:
        return Decimal(1), unit
    if cent_currency(unit):
        return Decimal("0.01"), cent_currency(unit)
    for prefix in ("MD", "T", "M"):
        if unit.startswith(prefix) and unit[len(prefix):] in CURRENCIES:
            return SCALES[prefix], unit[len(prefix):]
    return None


# --- Period ------------------------------------------------------------------

_MONTHS = {
    "januari": 1, "jan": 1, "january": 1, "februari": 2, "feb": 2, "february": 2, "mars": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4, "maj": 5, "may": 5, "juni": 6, "jun": 6, "june": 6, "juli": 7, "jul": 7, "july": 7,
    "augusti": 8, "aug": 8, "august": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_M = "|".join(sorted(_MONTHS, key=len, reverse=True))
_RANGE_RE = re.compile(
    rf"(?:\d{{1,2}}\s+)?\b({_M})\b\.?\s*(?:20\d\d\s*)?[-–—]\s*(?:\d{{1,2}}\s+)?\b({_M})\b", re.IGNORECASE)
_QUARTER_RE = re.compile(
    r"(första|andra|tredje|fjärde) kvartalet|kvartal(et)? [1-4]\b|\bkvartalet\b|\bq[1-4]\b|"
    r"(first|second|third|fourth) quarter|\bthe quarter\b",
    re.IGNORECASE)
_YTD_RE = re.compile(
    r"nio månader|niomånaders|sex månader|första halvåret|delåret|hela perioden|first (nine|six) months|"
    r"first half|year[- ]to[- ]date|the period",
    re.IGNORECASE)
_YEAR_RE = re.compile(r"helåret|full[- ]year|räkenskapsåret", re.IGNORECASE)


def period_before(text: str, pos: int) -> str | None:
    """Sorts period ('kvartal', 'delår', 'helår') för närmaste periodangivelse före pos."""
    window_start = max(0, pos - PERIOD_LOOKBACK_CHARS)
    window = text[window_start:pos]
    found: list[tuple[int, str]] = []
    for m in _RANGE_RE.finditer(window):
        a, b = _MONTHS[m.group(1).lower()], _MONTHS[m.group(2).lower()]
        span = (b - a) % 12 + 1
        found.append((m.end(), "kvartal" if span == 3 else "helår" if span == 12 else "delår"))
    found += [(m.end(), "kvartal") for m in _QUARTER_RE.finditer(window)]
    found += [(m.end(), "delår") for m in _YTD_RE.finditer(window)]
    found += [(m.end(), "helår") for m in _YEAR_RE.finditer(window)]
    return max(found)[1] if found else None


# --- Kontroll av ett nyckeltal ------------------------------------------------


def _in_quote(value: float, numbers, percent: bool = False) -> bool:
    v = abs(Decimal(str(value)))
    return any(abs(n.value) == v and (n.percent or not percent) for n in numbers)


def check_kpi(k: dict, kind: str, raw_text: str, where: str, res: Result) -> None:
    """Kontrollerar ett nyckeltal mot rapporttexten (raw_text: normaliserade mellanslag)."""
    quote = _normalize_ws(k["quote"])
    if len(quote.split()) > MAX_QUOTE_WORDS:
        res.errors.append(f"{where}: citatet har fler än {MAX_QUOTE_WORDS} ord")
    pos = raw_text.find(quote)
    if pos < 0:
        res.errors.append(f"{where}: citatet finns inte i rapporttexten: {k['quote']!r}")
    numbers = extract_numbers(quote)
    if not _in_quote(k["value"], numbers):
        res.errors.append(f"{where}: värdet {k['value']} finns inte i citatet")
    if k["previous_value"] is None and k["change_pct"] is None:
        res.errors.append(f"{where}: varken föregående års värde eller förändring anges")
    if k["previous_value"] is not None and not _in_quote(k["previous_value"], numbers):
        res.errors.append(f"{where}: föregående års värde {k['previous_value']} finns inte i citatet")
    if k["change_pct"] is not None:
        if kind == "procent":
            res.errors.append(f"{where}: förändring i procent anges inte för procenttal (jämför värdena)")
        elif not _in_quote(k["change_pct"], numbers, percent=True):
            res.errors.append(f"{where}: förändringen {k['change_pct']} % finns inte i citatet")
        elif k["previous_value"] not in (None, 0):
            computed = (k["value"] / k["previous_value"] - 1) * 100
            if abs(abs(computed) - abs(k["change_pct"])) > CHANGE_TOLERANCE_PP:
                res.errors.append(f"{where}: förändringen {k['change_pct']} % stämmer inte med värdena "
                                  f"({computed:.1f} %)")
    if k["unit"] not in UNIT_KINDS[kind] and not (kind == "per_aktie" and cent_currency(k["unit"])):
        res.errors.append(f"{where}: enheten {k['unit']!r} passar inte nyckeltalets typ {kind!r}")
    if pos >= 0:
        # Perioden avgörs av närmaste angivelse före värdet – även inne i citatet, t.ex.
        # "+12,93 (+7,45) för hela perioden och för kvartalet till -1,13 (+1,70)".
        value_at = next((quote.find(n.raw) for n in numbers
                         if abs(n.value) == abs(Decimal(str(k["value"]))) and quote.find(n.raw) >= 0), 0)
        found = period_before(raw_text, pos + value_at)
        if found is None:
            res.warnings.append(f"{where}: ingen periodangivelse hittades före citatet")
        elif found != k["period_kind"]:
            res.errors.append(f"{where}: citatet står under en {found}sangivelse men anges som {k['period_kind']}")


def _kpi_kinds(instruments: dict[str, Instrument]) -> dict[str, dict[str, str]]:
    """ticker -> {nyckeltal-id: typ} enligt report_list.kpis_for."""
    from report_list import kpis_for

    sector_kpis = load_sector_kpis()
    return {t: {k["id"]: k["kind"] for k in kpis_for(i, sector_kpis)} for t, i in instruments.items()}


def _check_report(r: dict, listed: dict, kinds: dict[str, str], where: str, res: Result) -> None:
    from report_list import report_path

    if r["raw_file"] != listed["raw_file"]:
        res.errors.append(f"{where}: raw_file {r['raw_file']!r} är inte rapporten {listed['raw_file']!r}")
        return
    path = report_path(listed)
    if not path.is_file():
        res.errors.append(f"{where}: rapporttexten {path} finns inte")
        return
    raw_text = _normalize_ws(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for k in r["kpis"]:
        kw = f"{where} {k['id']}"
        if k["id"] not in kinds:
            res.errors.append(f"{kw}: nyckeltalet hör inte till bolaget ({', '.join(kinds)})")
            continue
        if k["id"] in seen:
            res.errors.append(f"{kw}: dubblett")
        seen.add(k["id"])
        check_kpi(k, kinds[k["id"]], raw_text, kw, res)
    if not r["kpis"] and not r.get("note"):
        res.errors.append(f"{where}: inga nyckeltal och ingen förklaring (note)")


def _listing(scope: str, instruments: dict[str, Instrument], dirs: dict) -> list[dict]:
    from report_list import list_scope

    return list_scope(scope, instruments, load_sector_kpis(), **dirs)


def _dirs(raw_dir: Path, morning_raw: Path | None, results_dir: Path | None) -> dict:
    return {"raw_dir": raw_dir, "morning_raw": morning_raw, "results_dir": results_dir}


def validate_batch(data: dict, week: str, batch: int, instruments: dict[str, Instrument],
                   raw_dir: Path = RAW_DIR, morning_raw: Path | None = None,
                   results_dir: Path | None = None) -> Result:
    """En omgångsfil från /rapportutfall: data/results/<vecka>/omgang-<N>.json eller
    data/results/morning/<datum>/omgang-<N>.json (week är då datumet)."""
    from report_list import MORNING_RAW, RESULTS_DIR

    dirs = _dirs(raw_dir, morning_raw or MORNING_RAW, results_dir or RESULTS_DIR)
    res = Result()
    res.errors += _schema_errors(_schema_validator("results-batch.schema.json"), data)
    if res.errors:
        return res
    if data["week"] != week or data["batch"] != batch:
        res.errors.append(f"week/batch ({data['week']}, {data['batch']}) stämmer inte med filen ({week}, {batch})")
    listed = {r["ticker"]: r for r in _listing(week, instruments, dirs) if r["batch"] == batch}
    got = [r["ticker"] for r in data["reports"]]
    for t in sorted(set(listed) - set(got)):
        res.errors.append(f"{t}: rapporten saknas i omgången")
    for t in sorted(set(got) - set(listed)):
        res.errors.append(f"{t}: inte en rapport i omgång {batch} enligt report_list.py")
    if len(set(got)) != len(got):
        res.errors.append("samma bolag förekommer flera gånger")
    kinds = _kpi_kinds(instruments)
    for r in data["reports"]:
        if r["ticker"] in listed:
            _check_report(r, listed[r["ticker"]], kinds[r["ticker"]], r["ticker"], res)
    return res


def scope_period(scope: str) -> dict:
    """{start, end} för en vecka, en dag eller en uppdatering (dess datum)."""
    if re.fullmatch(r"\d{4}-W\d{2}", scope):
        start, end = iso_week_period(scope)
        return {"start": start.isoformat(), "end": end.isoformat()}
    return {"start": scope[:10], "end": scope[:10]}


def validate_results(data: dict, week: str, instruments: dict[str, Instrument], raw_dir: Path = RAW_DIR,
                     morning_raw: Path | None = None, results_dir: Path | None = None,
                     consensus_dir: Path | None = DATA_DIR / "consensus") -> Result:
    """Den sammanslagna filen från scripts/results.py: data/results/<vecka>.json eller
    data/results/morning/<datum>.json. Varje rapport valideras mot listan för sitt eget
    läge (scope): veckans fil innehåller också morgonkörningarnas rapporter."""
    from report_list import MORNING_RAW, RESULTS_DIR

    dirs = _dirs(raw_dir, morning_raw or MORNING_RAW, results_dir or RESULTS_DIR)
    res = Result()
    res.errors += _schema_errors(_schema_validator("results.schema.json"), data)
    if res.errors:
        return res
    if data["week"] != week or data["period"] != scope_period(week):
        res.errors.append("week/period stämmer inte med filnamnet")
    _check_datetime(data["generated_at"], "generated_at", res)
    listings: dict[str, dict[str, dict]] = {}
    kinds = _kpi_kinds(instruments)
    for r in data["reports"]:
        where = f"{r['ticker']} ({r['scope']})"
        if r["scope"] != week and not (re.fullmatch(r"\d{4}-W\d{2}", week) and scope_period(week)["start"]
                                       <= r["scope"][:10] <= scope_period(week)["end"]):
            res.errors.append(f"{where}: läget {r['scope']} hör inte till {week}")
            continue
        if r["scope"] not in listings:
            listings[r["scope"]] = {x["ticker"]: x for x in _listing(r["scope"], instruments, dirs)}
        listed = listings[r["scope"]]
        if r["ticker"] not in listed:
            res.errors.append(f"{where}: inte en rapport i {r['scope']} enligt report_list.py")
            continue
        inst = instruments[r["ticker"]]
        if r["name"] != inst.namn or r["url"] != listed[r["ticker"]]["url"]:
            res.errors.append(f"{where}: namn eller url stämmer inte med listan")
        _check_report(r, listed[r["ticker"]], kinds[r["ticker"]], where, res)
        for k in r["kpis"]:
            _check_yoy(k, kinds[r["ticker"]].get(k["id"]), f"{where} {k['id']}", res)
        _check_comparison(r, where, res, consensus_dir)
    return res


def _check_yoy(k: dict, kind: str | None, where: str, res: Result) -> None:
    """yoy_pct = rapportens procentsats, annars (värde − fjol) / |fjol|, inte för procenttal."""
    if k["change_pct"] is not None:
        expected = k["change_pct"]
    elif kind == "procent" or k["previous_value"] in (None, 0):
        expected = None
    else:
        expected = round((k["value"] - k["previous_value"]) / abs(k["previous_value"]) * 100, 1)
    if k["yoy_pct"] != expected:
        res.errors.append(f"{where}: yoy_pct {k['yoy_pct']} ≠ {expected}")


IN_LINE_PCT = 2.0  # inom ±2 % av förväntan räknas som "i linje"


def surprise_pct(actual: float, expected: float) -> float:
    """Avvikelse från förväntan i procent av förväntans belopp (rätt tecken även om förväntan är negativ)."""
    return (actual - expected) / abs(expected) * 100


def verdict(surprise: float) -> str:
    return "i linje" if abs(surprise) <= IN_LINE_PCT else "över" if surprise > 0 else "under"


# Samma regel som varningen "stor förändring, få analytiker" i src/lib/consensus.ts: förväntad
# förändring mot fjol över ±50 % från färre än 3 analytiker. Har bolagets konsensus den varningen
# (för vinst per aktie eller omsättning) bedöms utfallet inte som över/under.
BIG_CHANGE_PCT = 50.0
MIN_ANALYSTS = 3
UNCERTAIN = "osäker konsensus"


def expected_change(estimate: dict) -> float | None:
    """Förväntad förändring mot fjol i procent; None om fjolåret saknas, är noll eller har annat tecken."""
    ya = estimate.get("year_ago")
    if not ya or (ya > 0) != (estimate["avg"] > 0):
        return None
    return (estimate["avg"] - ya) / abs(ya) * 100


def big_change_few_analysts(estimate: dict | None) -> bool:
    if not estimate or not estimate.get("avg"):
        return False
    change = expected_change(estimate)
    return change is not None and abs(change) > BIG_CHANGE_PCT and (estimate.get("analysts") or 0) < MIN_ANALYSTS


def uncertain_consensus(company: dict) -> bool:
    """Sant om bolagets konsensus har varningen "stor förändring, få analytiker"."""
    return big_change_few_analysts(company.get("eps")) or big_change_few_analysts(company.get("revenue"))


def _check_comparison(r: dict, where: str, res: Result, consensus_dir: Path | None) -> None:
    """Utfall mot förväntan: räknas om ur nyckeltalet och den sparade konsensusen. Osäker
    konsensus kontrolleras mot konsensusfilen när den finns lokalt."""
    cmp = r.get("vs_consensus")
    if not cmp:
        return
    uncertain = cmp.get("uncertain", False)
    snap = consensus_dir / f"{cmp['consensus_date']}.json" if consensus_dir else None
    if snap and snap.exists():
        company = next((c for c in json.loads(snap.read_text(encoding="utf-8"))["companies"]
                        if c["ticker"] == r["ticker"]), None)
        if company is not None and uncertain_consensus(company) != uncertain:
            res.errors.append(f"{where}: uncertain={uncertain} stämmer inte med konsensus {cmp['consensus_date']}")
    by_id = {k["id"]: k for k in r["kpis"]}
    for key, kpi_id in (("eps", "resultat-per-aktie"), ("revenue", "nettoomsattning")):
        c = cmp.get(key)
        if not c:
            continue
        k = by_id.get(kpi_id)
        if k is None or k["period_kind"] != "kvartal":
            res.errors.append(f"{where}: jämförelse {key} utan kvartalsvärde för {kpi_id}")
            continue
        factor = unit_factor(k["unit"])
        if factor is None or factor[1] != c["currency"]:
            res.errors.append(f"{where}: {key} jämförs i fel valuta eller enhet")
            continue
        actual = float(Decimal(str(k["value"])) * factor[0])
        if abs(actual - c["actual"]) > max(1e-6, abs(actual) * 1e-9):
            res.errors.append(f"{where}: {key} utfall {c['actual']} ≠ {actual}")
        surprise = surprise_pct(actual, c["expected"])
        if abs(surprise - c["surprise_pct"]) > 0.051:
            res.errors.append(f"{where}: {key} avvikelse {c['surprise_pct']} % ≠ {surprise:.1f} %")
        if c["verdict"] != (UNCERTAIN if uncertain else verdict(c["surprise_pct"])):
            res.errors.append(f"{where}: {key} bedömningen {c['verdict']!r} stämmer inte med avvikelsen")

