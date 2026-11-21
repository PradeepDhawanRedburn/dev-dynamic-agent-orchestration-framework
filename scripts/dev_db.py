#!/usr/bin/env python3
"""Run the local development PostgreSQL. Standard library only; needs Docker.

    python scripts/dev_db.py up       create .env if missing, start the database, wait until healthy
    python scripts/dev_db.py down     stop it, keep the data
    python scripts/dev_db.py reset    stop it and delete the data
    python scripts/dev_db.py dsn      print the connection string (contains the password)

.env is git-ignored and holds a random password generated on first use; nothing secret is committed.
Production uses Azure Database for PostgreSQL, not this.
"""

import pathlib
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
PORT = "5432"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def dsn(values: dict[str, str]) -> str:
    port = values.get("POSTGRES_PORT", PORT)
    return f"postgresql://orchestrator:{values['POSTGRES_PASSWORD']}@127.0.0.1:{port}/orchestrator"


def ensure_env() -> dict[str, str]:
    values = read_env()
    if "POSTGRES_PASSWORD" in values:
        return values
    values["POSTGRES_PASSWORD"] = secrets.token_hex(16)
    values.setdefault("POSTGRES_PORT", PORT)
    values["DATABASE_URL"] = dsn(values)
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    print(f"Created {ENV_FILE.name} with a generated password (git-ignored).")
    return values


def compose(*args: str) -> int:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT).returncode


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "up"
    if command == "up":
        values = ensure_env()
        code = compose("up", "-d", "--wait")
        if code == 0:
            port = values.get("POSTGRES_PORT", PORT)
            print(f"PostgreSQL is ready on 127.0.0.1:{port} (database and user: orchestrator).")
            print(f"The connection string is DATABASE_URL in {ENV_FILE.name}.")
        return code
    if command == "down":
        return compose("down")
    if command == "reset":
        return compose("down", "-v")
    if command == "dsn":
        print(dsn(ensure_env()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
