"""Nya försök vid tillfälliga hämtningsfel mot Yahoo (yfinance).

yfinance kastar ibland tillfälliga fel (t.ex. KeyError eller nätverksfel) som går över vid
nästa anrop. Varje hämtning görs därför upp till ATTEMPTS gånger med PAUSE_S sekunders paus,
och varje misslyckat försök loggas på stderr:

    [försök 1/3] VICO.ST (vinsthistorik): KeyError – nytt försök om 2 s

Efter sista försöket kastas felet vidare, så att anroparen hanterar det som förut (fail-soft:
bolaget hamnar i "errors").
"""

from __future__ import annotations

import sys
import time
from typing import Callable, TypeVar

T = TypeVar("T")
ATTEMPTS = 3  # första försöket plus två nya
PAUSE_S = 2.0


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def with_retries(fn: Callable[[], T], label: str, attempts: int = ATTEMPTS, pause: float | None = None,
                 sleep: Callable[[float], None] | None = None, log: Callable[[str], None] = _log) -> T:
    """Anropar fn() upp till attempts gånger; loggar varje misslyckat försök."""
    pause = PAUSE_S if pause is None else pause
    sleep = sleep or time.sleep
    for n in range(1, attempts + 1):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 – yfinance:s fel är av många slag
            if n == attempts:
                log(f"[försök {n}/{attempts}] {label}: {type(exc).__name__} – ger upp")
                raise
            log(f"[försök {n}/{attempts}] {label}: {type(exc).__name__} – nytt försök om {pause:g} s")
            sleep(pause)
            continue
        if n > 1:
            log(f"[försök {n}/{attempts}] {label}: lyckades")
        return result
    raise AssertionError("oåtkomlig")


def retry_missing(fetch: Callable[[list[str]], dict], keys: list[str], label: str, attempts: int = ATTEMPTS,
                  pause: float | None = None, sleep: Callable[[float], None] | None = None,
                  log: Callable[[str], None] = _log) -> dict:
    """För batchhämtningar som inte kastar fel utan utelämnar det som misslyckades
    (yfinance.download): hämtar om de nycklar som saknas, upp till attempts gånger totalt."""
    pause = PAUSE_S if pause is None else pause
    sleep = sleep or time.sleep
    result = fetch(keys)
    missing = [k for k in keys if k not in result]
    for n in range(2, attempts + 1):
        if not missing:
            break
        log(f"[försök {n}/{attempts}] {label}: {len(missing)} saknas ({', '.join(missing[:5])}"
            f"{' …' if len(missing) > 5 else ''}) – nytt försök om {pause:g} s")
        sleep(pause)
        result.update(fetch(missing))
        missing = [k for k in missing if k not in result]
    if missing:
        log(f"{label}: saknas efter {attempts} försök: {', '.join(missing)}")
    return result
