"""Content-addressed cache with atomic rename. Never overwrite an existing hash."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ContentCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, namespace: str, digest: str) -> Path:
        folder = self.root / namespace / digest[:2]
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{digest}.json"

    def get_json(self, namespace: str, digest: str) -> dict[str, Any] | None:
        path = self.path_for(namespace, digest)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put_json(self, namespace: str, digest: str, payload: dict[str, Any]) -> Path:
        dest = self.path_for(namespace, digest)
        if dest.exists():
            return dest
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=digest, suffix=".tmp", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, dest)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        return dest


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
