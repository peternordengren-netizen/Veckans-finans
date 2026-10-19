"""Gemensamt för testerna: inga pauser mellan nya försök mot Yahoo (scripts/retry.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import retry  # noqa: E402


@pytest.fixture(autouse=True)
def _no_retry_pause(monkeypatch):
    monkeypatch.setattr(retry, "PAUSE_S", 0.0)
