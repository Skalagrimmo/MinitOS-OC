"""Shared QEMU discovery and process helpers for MinitOS K2 tools."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class QemuError(RuntimeError):
    pass


def find_qemu() -> Path:
    candidates: list[Path] = []

    env_value = os.environ.get("QEMU_SYSTEM_ARM")
    if env_value:
        candidates.append(Path(env_value))

    on_path = shutil.which("qemu-system-arm")
    if on_path:
        candidates.append(Path(on_path))

    if os.name == "nt":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if not base:
                continue
            candidates.append(Path(base) / "qemu" / "qemu-system-arm.exe")
            candidates.append(Path(base) / "Programs" / "qemu" / "qemu-system-arm.exe")
    else:
        candidates.extend([
            Path("/usr/bin/qemu-system-arm"),
            Path("/usr/local/bin/qemu-system-arm"),
        ])

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise QemuError(
        "qemu-system-arm not found. Install QEMU or set QEMU_SYSTEM_ARM to "
        "the full path of the executable."
    )


def run_capture(cmd, *, cwd: Path = ROOT, timeout: float = 20.0,
                input_text: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [str(part) for part in cmd],
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise QemuError(f"command timed out after {timeout}s: {cmd}") from exc


def qemu_version(qemu: Path) -> str:
    result = run_capture([qemu, "--version"], timeout=10)
    if result.returncode != 0:
        raise QemuError(f"cannot run {qemu}: {result.stderr.strip()}")
    return result.stdout.splitlines()[0]
