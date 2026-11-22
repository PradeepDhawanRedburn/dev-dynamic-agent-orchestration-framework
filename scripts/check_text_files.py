#!/usr/bin/env python3
"""Check that committed text files are UTF-8 without a byte-order mark and use LF line endings.

A file written by a tool that adds a BOM or CRLF (some PowerShell versions do) would change the
bytes of a prompt, a migration or a golden file, and with them a hash. The check reads what is
committed (the index), so a Windows checkout with core.autocrlf does not matter.

Standard library only. Run from the repository root:  python3 scripts/check_text_files.py"""

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".json",
    ".txt",
    ".ps1",
    ".cfg",
    ".ini",
    ".example",
}
BOM = b"\xef\xbb\xbf"


def problems_in(path: str, data: bytes, index_eol: str) -> list[str]:
    found: list[str] = []
    if data.startswith(BOM):
        found.append("starts with a byte-order mark")
    if index_eol in ("i/crlf", "i/mixed") or b"\r" in data:
        found.append("has CR line endings in the committed file; use LF")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        found.append("is not valid UTF-8")
    return [f"{path}: {message}" for message in found]


def tracked_text_files() -> Iterable[tuple[str, str]]:
    listing = subprocess.run(
        ["git", "ls-files", "--eol", "-z"], capture_output=True, check=True, text=True
    ).stdout
    for entry in listing.split("\0"):
        if not entry:
            continue
        info, _, path = entry.partition("\t")
        index_eol = info.split()[0]
        if Path(path).suffix in TEXT_SUFFIXES and not index_eol.endswith("-text"):
            yield path, index_eol


def blob_ids() -> dict[str, str]:
    listing = subprocess.run(
        ["git", "ls-files", "-s", "-z"], capture_output=True, check=True, text=True
    ).stdout
    ids: dict[str, str] = {}
    for entry in listing.split("\0"):
        if entry:
            info, _, path = entry.partition("\t")
            ids[path] = info.split()[1]
    return ids


def read_blobs(ids: list[str]) -> dict[str, bytes]:
    """Every blob in one `git cat-file --batch` process (a process per file is far too slow)."""
    done = subprocess.run(
        ["git", "cat-file", "--batch"],
        input="".join(f"{i}\n" for i in ids).encode(),
        capture_output=True,
        check=True,
    )
    out, position, blobs = done.stdout, 0, {}
    for _ in ids:
        newline = out.index(b"\n", position)
        sha, _type, size = out[position:newline].decode().split()
        start = newline + 1
        blobs[sha] = out[start : start + int(size)]
        position = start + int(size) + 1
    return blobs


def main() -> int:
    failures: list[str] = []
    wanted = list(tracked_text_files())
    ids = blob_ids()
    blobs = read_blobs(sorted({ids[path] for path, _ in wanted if path in ids}))
    for path, index_eol in wanted:
        if path in ids:
            failures += problems_in(path, blobs[ids[path]], index_eol)
    for failure in failures:
        print(failure)
    print("FAILED" if failures else f"OK: {len(wanted)} text files are UTF-8, no BOM, LF")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
