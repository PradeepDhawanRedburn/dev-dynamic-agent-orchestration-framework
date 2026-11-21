#!/usr/bin/env python3
"""Run the local development PostgreSQL. Standard library only; needs Docker.

    python scripts/dev_db.py up       create .env if missing, start the database, wait until healthy
    python scripts/dev_db.py down     stop it, keep the data
    python scripts/dev_db.py reset    stop it and delete the data
    python scripts/dev_db.py dsn      print the connection string (contains the password)

.env is git-ignored and holds a random password generated on first use; nothing secret is committed.
Every run keeps DATABASE_URL in step with POSTGRES_PASSWORD and POSTGRES_PORT in .env, so editing
either (or copying .env.example) never leaves a stale or missing connection string.
Production uses Azure Database for PostgreSQL, not this.
"""

import pathlib
import secrets
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
PORT = "5432"


def parse(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def dsn(password: str, port: str) -> str:
    quoted = urllib.parse.quote(password, safe="")  # '/', '?', '#' and '@' must not end the userinfo
    return f"postgresql://orchestrator:{quoted}@127.0.0.1:{port}/orchestrator"


def set_value(lines: list[str], key: str, value: str) -> list[str]:
    """Replace the first `key=` line, or append one, leaving every other line untouched."""
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("#") and line.partition("=")[0].strip() == key:
            lines[index] = f"{key}={value}"
            return lines
    return [*lines, f"{key}={value}"]


def ensure_env() -> dict[str, str]:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    values = parse(lines)
    created = not values.get("POSTGRES_PASSWORD") or values["POSTGRES_PASSWORD"] == "change-me"
    if created:
        lines = set_value(lines, "POSTGRES_PASSWORD", secrets.token_hex(16))
    if not values.get("POSTGRES_PORT"):
        lines = set_value(lines, "POSTGRES_PORT", PORT)
    values = parse(lines)
    lines = set_value(lines, "DATABASE_URL", dsn(values["POSTGRES_PASSWORD"], values["POSTGRES_PORT"]))
    text = "\n".join(lines) + "\n"
    if not ENV_FILE.exists() or ENV_FILE.read_text(encoding="utf-8") != text:
        ENV_FILE.write_text(text, encoding="utf-8")
        print(f"Updated {ENV_FILE.name} (git-ignored)" + (" with a generated password." if created else "."))
    return parse(lines)


def compose(*args: str) -> int:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT).returncode


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "up"
    if command == "up":
        values = ensure_env()
        code = compose("up", "-d", "--wait")
        if code == 0:
            print(f"PostgreSQL is ready on 127.0.0.1:{values['POSTGRES_PORT']} (database and user: orchestrator).")
            print(f"The connection string is DATABASE_URL in {ENV_FILE.name}.")
        return code
    if command == "down":
        return compose("down")
    if command == "reset":
        return compose("down", "-v")
    if command == "dsn":
        print(ensure_env()["DATABASE_URL"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
