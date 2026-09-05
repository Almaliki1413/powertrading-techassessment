#!/usr/bin/env python3
"""Root workflow runner. Works on Windows without GNU make."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(args: list[str], cwd: Path | None = None) -> None:
    print("+", *args)
    command: list[str] | str = args
    kwargs: dict[str, object] = {"cwd": str(cwd or ROOT)}
    if os.name == "nt":
        resolved = shutil.which(args[0])
        if resolved is None:
            raise FileNotFoundError(
                f"{args[0]} was not found on PATH. Install Node.js LTS and reopen the terminal."
            )
        # CreateProcess cannot launch npm.cmd/npx.cmd without a shell.
        if Path(resolved).suffix.lower() in {".cmd", ".bat"}:
            command = subprocess.list2cmdline([resolved, *args[1:]])
            kwargs["shell"] = True
        else:
            command = [resolved, *args[1:]]
    subprocess.check_call(command, **kwargs)


def python() -> str:
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def bootstrap() -> None:
    if not (BACKEND / ".venv").exists():
        run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
    run([python(), "-m", "pip", "install", "-e", ".[dev]"], cwd=BACKEND)
    run(["npm", "install"], cwd=FRONTEND)
    run([python(), str(ROOT / "scripts" / "record_versions.py")])
    run([python(), str(ROOT / "scripts" / "verify_pinned_data.py")])


def dev() -> None:
    print("API: http://127.0.0.1:8000")
    print("UI:  http://127.0.0.1:5173  (also http://localhost:5173)")
    api = subprocess.Popen(
        [python(), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
        cwd=BACKEND,
    )
    try:
        run(["npm", "run", "dev"], cwd=FRONTEND)
    finally:
        api.terminate()


def test() -> None:
    run([python(), "-m", "pytest"], cwd=BACKEND)
    run(["npm", "test"], cwd=FRONTEND)


def lint() -> None:
    run([python(), "-m", "ruff", "check", "app", "tests"], cwd=BACKEND)
    run([python(), "-m", "mypy", "app"], cwd=BACKEND)
    run(["npm", "run", "lint"], cwd=FRONTEND)


def build() -> None:
    run(["npm", "run", "build"], cwd=FRONTEND)
    run([python(), str(ROOT / "scripts" / "record_versions.py")])


def serve() -> None:
    print("Serving API + built UI at http://127.0.0.1:8000")
    run([python(), "-m", "uvicorn", "app.main:app", "--port", "8000"], cwd=BACKEND)


def verify_data() -> None:
    run([python(), str(ROOT / "scripts" / "verify_pinned_data.py")])


COMMANDS = {
    "bootstrap": bootstrap,
    "dev": dev,
    "test": test,
    "lint": lint,
    "build": build,
    "run": serve,
    "verify-data": verify_data,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: python scripts/make.py <" + "|".join(COMMANDS) + ">")
        return 2
    COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
