#!/usr/bin/env python3
"""Verify the QEMU platform contract used by MinitOS K2.

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
import socket
import subprocess
import sys
import time
from pathlib import Path

from qemu_common import ROOT, QemuError, find_qemu, qemu_version, run_capture


def _read_qmp_message(stream) -> dict:
    while True:
        line = stream.readline()
        if not line:
            raise QemuError("QMP connection closed before a response")
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QemuError(f"invalid QMP message: {line!r}") from exc
        # Skip asynchronous events; only command replies have return/error.
        if "return" in message or "error" in message:
            return message


def _qmp_command(stream, command: str, arguments: dict | None = None) -> dict:
    message = {"execute": command}
    if arguments is not None:
        message["arguments"] = arguments
    stream.write((json.dumps(message) + "\n").encode("utf-8"))
    stream.flush()
    return _read_qmp_message(stream)


def probe_mtree(qemu: Path, timeout: float = 15.0) -> str:
    """Ask a live QEMU for `info mtree` over a localhost QMP socket.

    A stdin pipe was flaky on Windows: closing stdin immediately after the
    script sometimes raced QEMU's greeting/response flush. A socket gives an
    explicit request/response boundary and avoids the race entirely.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    command = [
        str(qemu), "-M", "integratorcp", "-cpu", "arm1136", "-m", "128M",
        "-qmp", f"tcp:127.0.0.1:{port},server=on,wait=off",
        "-serial", "none", "-display", "none", "-monitor", "none",
    ]
    proc = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    sock = None
    stream = None
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise QemuError("QEMU exited before accepting the QMP connection")
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
                break
            except OSError:
                time.sleep(0.05)
        if sock is None:
            raise QemuError("timed out connecting to the QMP socket")

        sock.settimeout(timeout)
        stream = sock.makefile("rwb", buffering=0)

        greeting = json.loads(stream.readline().decode("utf-8", errors="replace"))
        if "QMP" not in greeting:
            raise QemuError(f"unexpected QMP greeting: {greeting!r}")

        capabilities = _qmp_command(stream, "qmp_capabilities")
        if "error" in capabilities:
            raise QemuError(f"qmp_capabilities failed: {capabilities['error']}")

        reply = _qmp_command(
            stream, "human-monitor-command",
            {"command-line": "info mtree"},
        )
        if "error" in reply:
            raise QemuError(f"info mtree failed: {reply['error']}")
        mtree = reply.get("return")
        if not isinstance(mtree, str):
            raise QemuError("info mtree returned a non-string response")

        try:
            _qmp_command(stream, "quit")
        except QemuError:
            pass  # QEMU may close the socket immediately after quit.
        return mtree
    finally:
        if stream is not None:
            stream.close()
        if sock is not None:
            sock.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        proc.communicate()


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

    # Probe the live machine over QMP. Retry once for transient host/emulator
    # startup failures; the socket protocol itself is request/response, so a
    # successful connection cannot return before the command was processed.
    mtree = ""
    qmp_error = ""
    for attempt in range(2):
        try:
            mtree = probe_mtree(qemu)
        except (QemuError, OSError, json.JSONDecodeError) as exc:
            qmp_error = str(exc)
            time.sleep(0.2)
            continue
        if mtree:
            break
        qmp_error = "QMP returned an empty memory map"

    if not mtree and not qmp_error:
        qmp_error = "QMP returned an empty memory map"

    check("QMP info mtree returned a memory map", bool(mtree), qmp_error)

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
