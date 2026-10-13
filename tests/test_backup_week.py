"""Tester för scripts/backup_week.py mot ett lokalt git-repo med en bare-remote."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backup_week import backup  # noqa: E402

WEEK = "2026-W42"


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def make_repos(tmp_path: Path):
    """Skapar remote.git, en klon som data/raw och en data-mapp med veckofil."""
    remote = tmp_path / "remote.git"
    run("git", "init", "-q", "--bare", "-b", "main", str(remote))
    raw = tmp_path / "data" / "raw"
    run("git", "clone", "-q", str(remote), str(raw))
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
        run("git", "-C", str(raw), "config", key, value)
    (raw / "README.md").write_text("rå\n", encoding="utf-8")
    run("git", "-C", str(raw), "add", "README.md")
    run("git", "-C", str(raw), "commit", "-q", "-m", "start")
    run("git", "-C", str(raw), "push", "-q", "-u", "origin", "main")
    data = tmp_path / "data"
    (data / "weeks").mkdir()
    (data / "weeks" / f"{WEEK}.json").write_text('{"week": "2026-W42"}', encoding="utf-8")
    return remote, raw, data


def remote_log(remote: Path) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(remote), "log", "--format=%s", "main"], capture_output=True, text=True,
        encoding="utf-8",
    ).stdout


def test_kopierar_committar_och_pushar(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    (data / "prices").mkdir()
    (data / "prices" / f"{WEEK}.json").write_text("{}", encoding="utf-8")
    ok, msg = backup(WEEK, data, raw, validation_ok=True)
    assert ok, msg
    assert "pushad" in msg
    assert (raw / "weeks" / f"{WEEK}.json").exists()
    assert (raw / "prices" / f"{WEEK}.json").exists()
    assert not (raw / "analysis").exists()  # analysfilen saknades och kopieras inte
    assert remote_log(remote).splitlines()[0] == f"Säkerhetskopia {WEEK} (validering OK)"


def test_ej_godkand_anges_i_meddelandet(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    ok, _ = backup(WEEK, data, raw, validation_ok=False)
    assert ok
    assert remote_log(remote).splitlines()[0] == f"Säkerhetskopia {WEEK} (validering EJ GODKÄND)"


def test_oforandrad_ger_ingen_ny_commit(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    backup(WEEK, data, raw, validation_ok=True)
    ok, msg = backup(WEEK, data, raw, validation_ok=True)
    assert ok
    assert "oförändrad" in msg
    assert len(remote_log(remote).splitlines()) == 2


def test_stoppar_vid_oincheckade_andringar(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    (raw / "annat.txt").write_text("någon annans", encoding="utf-8")
    ok, msg = backup(WEEK, data, raw, validation_ok=True)
    assert not ok
    assert "oincheckade" in msg
    assert not (raw / "weeks").exists()
    assert len(remote_log(remote).splitlines()) == 1


def test_lagger_inte_till_andra_filer(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    ok, _ = backup(WEEK, data, raw, validation_ok=True)
    assert ok
    files = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "--name-only", "--format=", "main"], capture_output=True,
        text=True,
    ).stdout.split()
    assert files == [f"weeks/{WEEK}.json"]


def test_hamtar_actions_commit_innan_push(tmp_path):
    remote, raw, data = make_repos(tmp_path)
    other = tmp_path / "annan-klon"
    run("git", "clone", "-q", str(remote), str(other))
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "Actions")):
        run("git", "-C", str(other), "config", key, value)
    (other / "ny.txt").write_text("hämtat", encoding="utf-8")
    run("git", "-C", str(other), "add", "ny.txt")
    run("git", "-C", str(other), "commit", "-q", "-m", "Hämtning")
    run("git", "-C", str(other), "push", "-q")
    ok, msg = backup(WEEK, data, raw, validation_ok=True)
    assert ok, msg
    assert remote_log(remote).splitlines()[:2] == [f"Säkerhetskopia {WEEK} (validering OK)", "Hämtning"]


def test_ogiltig_vecka_och_saknad_veckofil(tmp_path):
    _, raw, data = make_repos(tmp_path)
    assert backup("2026-42", data, raw, True)[0] is False
    ok, msg = backup("2026-W43", data, raw, True)
    assert not ok and "saknas" in msg
