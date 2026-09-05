from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.domain.errors import SolverFailed
from app.infrastructure.optimization.solver_watchdog import (
    owned_solver_pids,
    run_with_hard_deadline,
    terminate_pids,
)


def test_run_with_hard_deadline_returns_when_work_finishes() -> None:
    assert run_with_hard_deadline(lambda: 7, deadline_s=1.0, on_expire=lambda: None) == 7


def test_run_with_hard_deadline_kills_and_raises_when_work_hangs() -> None:
    expired: list[bool] = []

    def hang() -> int:
        time.sleep(5)
        return 1

    with pytest.raises(SolverFailed) as captured:
        run_with_hard_deadline(hang, deadline_s=0.2, on_expire=lambda: expired.append(True))

    assert expired == [True]
    assert captured.value.code == "SOLVER_FAILED"
    assert captured.value.details.get("killed") is True


def test_owned_solver_pids_finds_direct_child() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        names = frozenset({Path(sys.executable).name.lower()})
        found = owned_solver_pids(names=names)
        assert child.pid in found
    finally:
        terminate_pids([child.pid])
        child.wait(timeout=5)


def test_terminate_pids_stops_child_process() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    terminate_pids([child.pid])
    child.wait(timeout=5)
    assert child.returncode is not None
