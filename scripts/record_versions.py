#!/usr/bin/env python3
"""Record actually installed runtime and solver versions. Do not guess CBC from the PuLP name."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _node_version() -> str | None:
    try:
        return subprocess.check_output(["node", "--version"], text=True, shell=os.name == "nt").strip()
    except OSError:
        return None


def _npm_version() -> str | None:
    try:
        return subprocess.check_output(["npm", "--version"], text=True, shell=os.name == "nt").strip()
    except OSError:
        return None


def main() -> int:
    from importlib.metadata import version

    from app.infrastructure.optimization.pulp_cbc import query_cbc_identity

    identity = query_cbc_identity()
    payload = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "node": _node_version(),
        "npm": _npm_version(),
        "packages": {
            "fastapi": version("fastapi"),
            "pydantic": version("pydantic"),
            "pulp": identity.pulp_version,
        },
        "cbc": {
            "version": identity.cbc_version,
            "executable_path": identity.executable_path,
            "executable_sha256": identity.executable_sha256,
            "options": list(identity.options),
        },
        "frontend": {},
    }
    pkg = ROOT / "frontend" / "node_modules" / "react" / "package.json"
    if pkg.is_file():
        react = json.loads(pkg.read_text(encoding="utf-8"))
        payload["frontend"]["react"] = react.get("version")
    for name in ("typescript", "vite", "plotly.js-dist-min"):
        path = ROOT / "frontend" / "node_modules" / name / "package.json"
        if path.is_file():
            payload["frontend"][name] = json.loads(path.read_text(encoding="utf-8")).get("version")
    dest = ROOT / "build-info.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
