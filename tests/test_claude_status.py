"""Tester för Claudes användningsgräns (scripts/claude_status.py) och kvotraden i hälsokontrollen."""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import claude_status  # noqa: E402
import health_check  # noqa: E402

TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime(2026, 10, 26, 7, 30, 13, tzinfo=TZ)
# Svaret som stoppade W43 måndag 07:30 (förkortat).
LIMIT = {"type": "result", "is_error": True, "num_turns": 1, "api_error_status": 429,
         "api_error": "usage_limit_reached", "result": "You've hit your weekly limit · resets 8am (Europe/Stockholm)",
         "duration_ms": 527, "usage": {"output_tokens": 0}, "total_cost_usd": 0}
OK = {"type": "result", "is_error": False, "num_turns": 24, "result": "Klart.", "duration_ms": 300000,
      "usage": {"output_tokens": 20000}, "total_cost_usd": 0.9}


def test_aterstallningstid():
    assert claude_status.reset_time("resets 8am (Europe/Stockholm)", NOW) == datetime(2026, 10, 26, 8, 0, tzinfo=TZ)
    # Efter klockslaget: nästa dag.
    later = datetime(2026, 10, 26, 9, 0, tzinfo=TZ)
    assert claude_status.reset_time("resets 8am (Europe/Stockholm)", later) == datetime(2026, 10, 27, 8, 0, tzinfo=TZ)
    assert claude_status.reset_time("resets 8:30pm", NOW) == datetime(2026, 10, 26, 20, 30, tzinfo=TZ)
    assert claude_status.reset_time("resets Oct 27, 8am (Europe/Stockholm)", NOW) == datetime(2026, 10, 27, 8, 0, tzinfo=TZ)
    assert claude_status.reset_time("något annat", NOW) is None


def test_kvotstopp_skriver_status_och_raknas_inte(tmp_path, capsys):
    status = tmp_path / "status" / "claude-limit.json"
    out = tmp_path / "w43.json"
    out.write_text(json.dumps(LIMIT), encoding="utf-8")
    assert claude_status.check(out, "veckosammanfattning 2026-W43", NOW, status) == claude_status.EXIT_LIMIT
    printed = capsys.readouterr().out.splitlines()
    assert printed == ["Claudes användningsgräns nådd – försöker igen efter 08:00", "RESET_AT 2026-10-26T08:00+01:00"]
    s = json.loads(status.read_text(encoding="utf-8"))
    assert (s["reset_at"], s["source"]) == ("2026-10-26T08:00+01:00", "veckosammanfattning 2026-W43")
    assert "AKTIV" in claude_status.status(NOW, status)
    # En lyckad körning efteråt tar bort statusen.
    out.write_text(json.dumps(OK), encoding="utf-8")
    assert claude_status.check(out, "veckosammanfattning 2026-W43", NOW, status) == 0
    assert not status.exists()
    # Ett oläsbart svar är inget kvotstopp.
    out.write_text("inte json", encoding="utf-8")
    assert claude_status.check(out, "x", NOW, status) == 0


def test_meddelande_med_datum_om_inte_i_dag():
    assert claude_status.limit_message(datetime(2026, 10, 27, 8, 0, tzinfo=TZ), NOW) == \
        "Claudes användningsgräns nådd – försöker igen efter 27/10 08:00"
    assert claude_status.limit_message(None, NOW).endswith("efter återställningen")


def test_halsokontrollens_kvotrad(tmp_path):
    logs = tmp_path / "logs"
    (logs / "weekly").mkdir(parents=True)
    (logs / "weekly" / "2026-W43.json").write_text(json.dumps(LIMIT), encoding="utf-8")
    (logs / "morning").mkdir()
    (logs / "morning" / "2026-10-26-rapportutfall-1.json").write_text(json.dumps(OK), encoding="utf-8")
    status = tmp_path / "claude-limit.json"
    now = datetime.now(TZ)  # loggfilerna har dagens ändringstid
    name, state, detail = health_check.quota_row(now, logs, status)
    assert state == health_check.UNKNOWN and "kvotstopp" in detail and "1 körningar" in detail
    status.write_text(json.dumps({"hit_at": "x", "reset_at": None, "source": "test"}), encoding="utf-8")
    assert health_check.quota_row(now, logs, status)[1] == health_check.FAIL
