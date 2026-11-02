#!/usr/bin/env python3
"""Run the MinitOS K1 ELF in QEMU and verify observable execution.

The kernel never exits by itself, so the harness waits for the UART marker,
then terminates QEMU. A pass requires:
  - QEMU actually started the guest (no early exit),
  - the first serial line is exactly "MINITOS KERNEL STARTED",
  - the board/UART/MIDR diagnostics are present,
  - MIDR identifies an ARM1136 (implementer 0x41, part 0xB36),
  - QEMU's guest-error log is empty.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from qemu_common import ROOT, QemuError, find_qemu, qemu_version

MARKER = "MINITOS KERNEL STARTED"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run MinitOS K1 in QEMU")
    parser.add_argument("--elf", default=str(ROOT / "build" / "minitos-k1.elf"),
                        help="kernel ELF path")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds to wait for the banner (default: 5)")
    parser.add_argument("--log", default=str(ROOT / "build" / "serial.log"),
                        help="serial capture path")
    args = parser.parse_args(argv)

    elf = Path(args.elf).resolve()
    log = Path(args.log).resolve()
    log.parent.mkdir(parents=True, exist_ok=True)
    guest_errors = log.parent / "qemu-guest-errors.log"

    if not elf.is_file():
        print(f"RUNTIME CHECK: FAIL: missing {elf}", file=sys.stderr)
        print("run: python tools/build.py build", file=sys.stderr)
        return 2

    try:
        qemu = find_qemu()
        version = qemu_version(qemu)
    except QemuError as exc:
        print(f"RUNTIME CHECK: FAIL: {exc}", file=sys.stderr)
        return 2

    for stale in (log, guest_errors):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass

    log_arg = str(log.relative_to(ROOT)) if log.is_relative_to(ROOT) else str(log)
    errors_arg = (str(guest_errors.relative_to(ROOT))
                  if guest_errors.is_relative_to(ROOT) else str(guest_errors))

    command = [
        str(qemu),
        "-M", "integratorcp",
        "-cpu", "arm1136",
        "-m", "128M",
        "-kernel", str(elf),
        "-display", "none",
        "-monitor", "none",
        "-serial", f"file:{log_arg}",
        "-no-reboot",
        "-d", "guest_errors",
        "-D", errors_arg,
    ]

    print("QEMU:", " ".join(command))
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    deadline = time.monotonic() + args.timeout
    observed = ""
    while time.monotonic() < deadline:
        observed = read_text(log)
        if MARKER in observed:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

    stdout, stderr = proc.communicate()
    observed = read_text(log)
    guest_text = read_text(guest_errors).strip()

    normalised = observed.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalised.splitlines()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("guest produced serial output", bool(observed), ""))
    checks.append(("first serial line is the K1 banner",
                   bool(lines) and lines[0] == MARKER,
                   f"first line={lines[0]!r}" if lines else "no lines"))
    checks.append(("board diagnostic is present",
                   "board: integratorcp" in normalised, ""))
    checks.append(("UART diagnostic is present",
                   "uart: pl011 @ 0x16000000" in normalised, ""))

    midr_match = re.search(r"^cpu midr: 0x([0-9a-fA-F]{8})$", normalised, re.M)
    if midr_match is None:
        checks.append(("CPU MIDR is reported", False, "no MIDR line"))
    else:
        midr = int(midr_match.group(1), 16)
        implementer = (midr >> 24) & 0xFF
        part = (midr >> 4) & 0xFFF
        checks.append(("CPU MIDR is reported", True, ""))
        checks.append(("CPU implementer is ARM (0x41)", implementer == 0x41,
                       f"implementer=0x{implementer:02x}"))
        checks.append(("CPU part is ARM1136 (0xB36)", part == 0xB36,
                       f"part=0x{part:03x}"))

    checks.append(("QEMU guest-error log is empty", not guest_text,
                   guest_text.splitlines()[0] if guest_text else ""))

    failed = 0
    for name, ok, detail in checks:
        if ok:
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name}" + (f": {detail}" if detail else ""))

    print()
    print("serial output:")
    for line in lines:
        print("  | " + line)
    if stdout.strip():
        print("qemu stdout:")
        print(stdout.strip())
    if stderr.strip():
        print("qemu stderr:")
        print(stderr.strip())
    if guest_text:
        print("qemu guest errors:")
        print(guest_text)

    evidence = log.parent / "runtime-evidence.txt"
    evidence_lines = [
        "MinitOS K1 runtime evidence",
        f"qemu: {qemu}",
        version,
        "command: " + " ".join(command),
        "",
        "checks:",
    ]
    for name, ok, detail in checks:
        evidence_lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}"
                              + (f": {detail}" if detail and not ok else ""))
    evidence_lines += ["", "serial output:", normalised.rstrip("\n")]
    evidence.write_text("\n".join(evidence_lines) + "\n", encoding="utf-8")
    print(f"evidence: {evidence}")

    if failed:
        print(f"RUNTIME CHECK: FAIL ({failed} failed / {len(checks)} checks)")
        return 1
    print(f"RUNTIME CHECK: PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
