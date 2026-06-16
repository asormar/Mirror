"""Cross-platform dev workflow for CopyTrade Sim.

Usage (from repo root):
    python scripts/dev.py up
    python scripts/dev.py down
    python scripts/dev.py migrate
    python scripts/dev.py test-unit
    python scripts/dev.py test-int
    python scripts/dev.py reset-db
    python scripts/dev.py seed
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
VENV_PY = BACKEND_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
    "python.exe" if os.name == "nt" else "python"
)
DOCKER = ["docker", "compose"]


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    printable = " ".join(shlex.quote(c) for c in cmd)
    cwd_str = f" (cwd={cwd})" if cwd else ""
    print(f"$ {printable}{cwd_str}")
    result = subprocess.run(cmd, cwd=cwd, check=check)
    return result.returncode


def docker_compose(args: list[str]) -> int:
    return run([*DOCKER, *args], cwd=REPO_ROOT)


def up() -> int:
    rc = docker_compose(["up", "-d", "db"])
    if rc != 0:
        return rc
    print("Waiting for Postgres to be healthy...")
    for _ in range(30):
        time.sleep(1)
        result = subprocess.run(
            [*DOCKER, "ps", "--format", "{{.Names}}\t{{.Status}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if "healthy" in result.stdout:
            print("Postgres is ready.")
            return 0
    print("Postgres did not become healthy in time.", file=sys.stderr)
    return 1


def down() -> int:
    return docker_compose(["down"])


def reset_db() -> int:
    print("Tearing down containers + volumes...")
    rc = docker_compose(["down", "-v"])
    if rc != 0:
        return rc
    return up()


def migrate() -> int:
    return run([str(VENV_PY), "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT)


def pytest(args: list[str]) -> int:
    return run([str(VENV_PY), "-m", "pytest", *args], cwd=BACKEND_ROOT)


def test_unit() -> int:
    return pytest(["-q", "-m", "not integration"])


def test_int() -> int:
    return pytest(["-q", "-m", "integration", "tests/integration/"])


def seed() -> int:
    return run([str(VENV_PY), "scripts/seed_entities.py"], cwd=BACKEND_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="CopyTrade Sim dev workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("up", help="Start the Postgres container")
    sub.add_parser("down", help="Stop the Postgres container")
    sub.add_parser("reset-db", help="Drop volumes, restart Postgres, re-run migrations")
    sub.add_parser("migrate", help="Run alembic upgrade head")
    sub.add_parser("test-unit", help="Run unit tests only (no DB)")
    sub.add_parser("test-int", help="Run integration tests (requires Postgres)")
    sub.add_parser("seed", help="Seed target entities (TODO)")

    args = parser.parse_args()
    handlers = {
        "up": up,
        "down": down,
        "reset-db": reset_db,
        "migrate": migrate,
        "test-unit": test_unit,
        "test-int": test_int,
        "seed": seed,
    }
    return handlers[args.cmd]()


if __name__ == "__main__":
    sys.exit(main())
