"""Hard deadline around CBC so a wedged solver cannot hold the semaphore forever."""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from app.domain.errors import SolverFailed

T = TypeVar("T")

HARD_DEADLINE_GRACE_S = 5.0
CBC_PROCESS_NAMES = frozenset({"cbc", "cbc.exe"})


def run_with_hard_deadline(
    fn: Callable[[], T],
    *,
    deadline_s: float,
    on_expire: Callable[[], None],
    grace_join_s: float = 2.0,
) -> T:
    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 — re-raised on the caller thread
            box["exc"] = exc

    worker = threading.Thread(target=target, name="cbc-watchdog", daemon=True)
    worker.start()
    worker.join(deadline_s)
    if worker.is_alive():
        on_expire()
        worker.join(grace_join_s)
        raise SolverFailed(
            "CBC exceeded the hard deadline and was terminated",
            details={"deadline_s": deadline_s, "killed": True, "status": "Terminated"},
        )
    if "exc" in box:
        raise box["exc"]  # type: ignore[misc]
    return box["value"]  # type: ignore[return-value]


def owned_solver_pids(*, names: frozenset[str] | None = None) -> list[int]:
    wanted = {item.lower() for item in (names or CBC_PROCESS_NAMES)}
    parent = os.getpid()
    children = _windows_children(parent) if os.name == "nt" else _unix_children(parent)
    return [pid for pid, name in children if Path(name).name.lower() in wanted]


def kill_owned_solver_processes() -> list[int]:
    pids = owned_solver_pids()
    terminate_pids(pids)
    return pids


def terminate_pids(pids: Sequence[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue


def _windows_children(parent_pid: int) -> list[tuple[int, str]]:
    import ctypes
    from ctypes import wintypes

    th32cs_snapprocess = 0x00000002

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot in {wintypes.HANDLE(-1).value, ctypes.c_void_p(-1).value}:
        return []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        found: list[tuple[int, str]] = []
        while True:
            if int(entry.th32ParentProcessID) == parent_pid:
                found.append((int(entry.th32ProcessID), str(entry.szExeFile)))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return found
    finally:
        kernel32.CloseHandle(snapshot)


def _unix_children(parent_pid: int) -> list[tuple[int, str]]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    found: list[tuple[int, str]] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            text = (entry / "status").read_text(encoding="utf-8")
        except OSError:
            continue
        name = ""
        ppid: int | None = None
        for line in text.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("PPid:"):
                ppid = int(line.split(":", 1)[1].strip())
        if ppid == parent_pid and name:
            found.append((int(entry.name), name))
    return found
