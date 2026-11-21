"""S-07: killing the process mid-superstep and restarting does not re-run completed branches."""

import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.postgres

CHILD = Path(__file__).with_name("kill_restart_child.py")


def start(dsn: str, log: Path, *, mode: str, durability: str, hang: str) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "SPIKE_DSN": dsn,
        "SPIKE_LOG": str(log),
        "SPIKE_THREAD": "kill-restart",
        "SPIKE_MODE": mode,
        "SPIKE_DURABILITY": durability,
        "SPIKE_HANG": hang,
    }
    return subprocess.Popen(
        [sys.executable, str(CHILD)], env=env, stderr=subprocess.PIPE, text=True
    )


def lines(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def wait_for(log: Path, expected: set[str], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not expected <= set(lines(log)):
        assert time.monotonic() < deadline, f"timed out waiting for {expected}: {lines(log)}"
        time.sleep(0.05)


def run_to_completion(
    dsn: str, log: Path, *, mode: str, durability: str
) -> tuple[Counter[str], int, str]:
    before = Counter(lines(log))
    process = start(dsn, log, mode=mode, durability=durability, hang="")
    _, stderr = process.communicate(timeout=120)
    return Counter(lines(log)) - before, process.returncode, stderr


def kill_mid_run(dsn: str, log: Path, durability: str, settle: float) -> None:
    process = start(dsn, log, mode="run", durability=durability, hang="c")
    try:
        wait_for(log, {"done a", "done b", "start c"})
        time.sleep(settle)
    finally:
        process.kill()
        process.communicate()


@pytest.mark.parametrize("durability", ["sync", "async"])
def test_s07_completed_branches_are_not_rerun_after_a_kill(
    pg_dsn: str, tmp_path: Path, durability: str
) -> None:
    log = tmp_path / "side-effects.log"
    kill_mid_run(pg_dsn, log, durability, settle=2)

    after, code, stderr = run_to_completion(pg_dsn, log, mode="resume", durability=durability)
    assert code == 0, stderr[-500:]
    assert "start a" not in after and "start b" not in after
    assert after["start c"] == 1 and after["done c"] == 1
    assert after["finish"] == 1
    assert after['result ["a", "b", "c"]'] == 1


def test_s07_exit_durability_saves_nothing_so_a_kill_cannot_be_resumed(
    pg_dsn: str, tmp_path: Path
) -> None:
    log = tmp_path / "side-effects.log"
    kill_mid_run(pg_dsn, log, "exit", settle=2)

    _, code, stderr = run_to_completion(pg_dsn, log, mode="resume", durability="exit")
    assert code != 0 and "EmptyInputError" in stderr

    after, code, _ = run_to_completion(pg_dsn, log, mode="run", durability="exit")
    assert code == 0
    assert after["start a"] == after["start b"] == after["start c"] == 1, "everything runs again"


@pytest.mark.parametrize("durability", ["sync", "async"])
def test_s07_kill_immediately_after_a_branch_finishes(
    pg_dsn: str, tmp_path: Path, durability: str
) -> None:
    """Informational: with no settling time the completed branches may or may not be saved."""
    log = tmp_path / "side-effects.log"
    kill_mid_run(pg_dsn, log, durability, settle=0)
    after, code, _ = run_to_completion(pg_dsn, log, mode="resume", durability=durability)
    print(durability, "kill at once ->", dict(after))
    assert code == 0
    assert after["finish"] == 1
