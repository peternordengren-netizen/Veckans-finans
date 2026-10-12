"""Arbetsdagar på Nasdaq Stockholm (för t.ex. sen anmälan i insynsregistret).

Arbetsdag = vardag som inte är en dag då börsen är stängd: nyårsdagen,
trettondedag jul, långfredagen, annandag påsk, 1 maj, Kristi himmelsfärdsdag,
nationaldagen, midsommarafton, julafton, juldagen, annandag jul och nyårsafton.
"""

from __future__ import annotations

from datetime import date, timedelta


def easter(year: int) -> date:
    """Påskdagen (gregoriansk, anonym algoritm/Gauss)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def non_business_days(year: int) -> set[date]:
    """Dagar då Nasdaq Stockholm är stängd (förutom lördag/söndag)."""
    e = easter(year)
    midsummer_eve = next(date(year, 6, d) for d in range(19, 26) if date(year, 6, d).weekday() == 4)
    return {
        date(year, 1, 1), date(year, 1, 6), e - timedelta(days=2), e + timedelta(days=1),
        date(year, 5, 1), e + timedelta(days=39), date(year, 6, 6), midsummer_eve,
        date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31),
    }


def business_days_between(start: date, end: date) -> int:
    """Antal arbetsdagar efter start till och med end (0 om end ≤ start)."""
    days, d = 0, start
    holidays: dict[int, set[date]] = {}
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays.setdefault(d.year, non_business_days(d.year)):
            days += 1
    return days
