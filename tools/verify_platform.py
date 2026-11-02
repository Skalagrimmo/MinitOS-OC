#!/usr/bin/env python3
"""Verify the QEMU platform contract used by MinitOS K1.

This is not a documentation lookup. It asks the installed QEMU:
  1. whether the integratorcp machine exists,
  2. whether it accepts the arm1136 CPU model,
  3. what the live machine's memory map actually is (QMP `info mtree`).

The observed map is written to build/qemu-mtree.txt so the board constants
can be audited against real emulator output.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from qemu_common import ROOT, QemuError, find_qemu, qemu_version, run_capture


def main() -> int:
    try:
        qemu = find_qemu()
    except QemuError as exc:
        print(f"PLATFORM CHECK: FAIL: {exc}", file=sys.stderr)
        return 2

    outdir = ROOT / "build"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence = outdir / "qemu-platform.txt"
    mtree_file = outdir / "qemu-mtree.txt"

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append((name, bool(condition), detail))

    try:
        version = qemu_version(qemu)
    except QemuError as exc:
        print(f"PLATFORM CHECK: FAIL: {exc}", file=sys.stderr)
        return 2

    machines = run_capture([qemu, "-M", "help"], timeout=15)
    machine_ok = "integratorcp" in machines.stdout
    check("QEMU has the integratorcp machine", machine_ok)

    cpu_help = run_capture(
        [qemu, "-M", "integratorcp", "-cpu", "help"], timeout=15
    )
    cpu_names = [line.strip() for line in cpu_help.stdout.splitlines()]
    arm1136_ok = "arm1136" in cpu_names
    check("integratorcp accepts -cpu arm1136", arm1136_ok,
          f"available: {', '.join(cpu_names[:8])}...")

    qmp_script = "\n".join(json.dumps(message) for message in [
        {"execute": "qmp_capabilities"},
        {"execute": "human-monitor-command",
         "arguments": {"command-line": "info mtree"}},
        {"execute": "quit"},
    ]) + "\n"

    try:
        qmp = run_capture(
            [qemu, "-M", "integratorcp", "-cpu", "arm1136", "-m", "128M",
             "-qmp", "stdio", "-serial", "none", "-display", "none"],
            timeout=20,
            input_text=qmp_script,
        )
    except QemuError as exc:
        print(f"PLATFORM CHECK: FAIL: QMP probe failed: {exc}", file=sys.stderr)
        return 2

    mtree = ""
    for line in qmp.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        returned = message.get("return")
        if isinstance(returned, str) and "integrator.ram" in returned:
            mtree = returned
            break

    check("QMP info mtree returned a memory map", bool(mtree))

    if mtree:
        mtree_file.write_text(
            f"# {version}\n"
            f"# command: {qemu} -M integratorcp -cpu arm1136 -m 128M "
            f"-qmp stdio -serial none -display none\n"
            f"# QMP human-monitor-command: info mtree\n\n{mtree}\n",
            encoding="utf-8",
        )
        check("RAM is 128 MiB at 0x00000000",
              re.search(r"0000000000000000-0000000007ffffff.*integrator\.ram",
                        mtree) is not None)
        check("UART0 is PL011 at 0x16000000",
              re.search(r"0000000016000000-0000000016000fff.*pl011", mtree)
              is not None)
        check("UART1 is PL011 at 0x17000000",
              re.search(r"0000000017000000-0000000017000fff.*pl011", mtree)
              is not None)
        check("system controller is at 0x10000000",
              "0000000010000000-00000000107fffff" in mtree)

    lines = [f"QEMU: {qemu}", version, ""]
    for name, ok, detail in checks:
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}"
                     + (f": {detail}" if detail and not ok else ""))
    evidence.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"QEMU: {qemu}")
    print(version)
    failed = 0
    for name, ok, detail in checks:
        if ok:
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name}" + (f": {detail}" if detail else ""))
    print(f"evidence: {evidence}")

    if failed:
        print(f"PLATFORM CHECK: FAIL ({failed} failed / {len(checks)} checks)")
        return 1
    print(f"PLATFORM CHECK: PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
