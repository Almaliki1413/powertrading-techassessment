"""Architecture boundary: domain imports stdlib only."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN_DOMAIN = {
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "pulp",
    "httpx",
    "starlette",
    "uvicorn",
    "pandas",
    "numpy",
    "plotly",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_domain_does_not_import_frameworks() -> None:
    for path in (ROOT / "domain").rglob("*.py"):
        imported = _imports(path)
        bad = imported & FORBIDDEN_DOMAIN
        assert not bad, f"{path} imports {bad}"
