"""The committed-text-files check (scripts/check_text_files.py)."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_text_files.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_text_files", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_clean_file_has_no_problems() -> None:
    assert load().problems_in("a.py", b"x = 1\n", "i/lf") == []


def test_a_byte_order_mark_is_reported() -> None:
    found = load().problems_in("a.py", b"\xef\xbb\xbfx = 1\n", "i/lf")
    assert found == ["a.py: starts with a byte-order mark"]


def test_crlf_in_the_committed_file_is_reported_by_content_and_by_index() -> None:
    check = load()
    assert check.problems_in("a.py", b"x = 1\r\n", "i/lf")
    assert check.problems_in("a.py", b"x = 1\n", "i/crlf")
    assert check.problems_in("a.py", b"x = 1\n", "i/mixed")


def test_text_that_is_not_utf_8_is_reported() -> None:
    assert load().problems_in("a.py", b"caf\xe9\n", "i/lf") == ["a.py: is not valid UTF-8"]


def test_the_repository_itself_passes() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=SCRIPT.parent.parent,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("OK:")
