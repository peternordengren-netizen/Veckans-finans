"""Tester för scripts/workdays.py (arbetsdagar på Nasdaq Stockholm)."""

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import workdays  # noqa: E402


@pytest.mark.parametrize("year, expected", [(2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)), (2025, date(2025, 4, 20))])
def test_paskdagen(year, expected):
    assert workdays.easter(year) == expected


def test_stangda_dagar_2026():
    closed = workdays.non_business_days(2026)
    for d in [date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1),
              date(2026, 5, 14), date(2026, 6, 6), date(2026, 6, 19), date(2026, 12, 24), date(2026, 12, 25),
              date(2026, 12, 26), date(2026, 12, 31)]:
        assert d in closed, d
    assert date(2026, 6, 20) not in closed  # midsommardagen är lördag – helg ändå


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (date(2026, 10, 2), date(2026, 10, 7), 3),    # fre -> ons: mån, tis, ons
        (date(2026, 9, 30), date(2026, 10, 5), 3),    # ons -> mån: tor, fre, mån
        (date(2026, 10, 1), date(2026, 10, 7), 4),    # en dag för mycket
        (date(2026, 4, 2), date(2026, 4, 7), 1),      # långfredag och annandag påsk räknas inte
        (date(2026, 12, 23), date(2026, 12, 29), 2),  # julafton, juldagen, annandag (lör) bort
        (date(2026, 10, 7), date(2026, 10, 7), 0),    # samma dag
        (date(2026, 10, 7), date(2026, 10, 5), 0),    # publicerad före transaktionen (felaktig data)
    ],
)
def test_arbetsdagar_mellan(start, end, expected):
    assert workdays.business_days_between(start, end) == expected
