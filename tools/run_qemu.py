#!/usr/bin/env python3
"""Run MinitOS K2 profiles in QEMU and verify observable CPU behaviour.

Each profile is a separate QEMU process with its own serial capture. The
harness waits for the profile's terminal UART marker and then terminates
QEMU. A timeout or an empty log is a failure, never a successful hang.

The checks verify the actual exception path: the vector offset, the CPU mode
reported by the handler, SPSR/LR relationships, DFSR/DFAR for the alignment
fault, and the sentinel registers saved in the exception frame.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from qemu_common import ROOT, QemuError, find_qemu, qemu_version

BANNER = "MINITOS KERNEL STARTED"
PROFILES = ["normal", "undef", "data-abort"]
TERMINAL_MARKERS = {
    "normal": "K2 IDLE",
    "undef": "K2 EXCEPTION CAPTURED",
    "data-abort": "K2 EXCEPTION CAPTURED",
}
SENTINELS = {
    "r0_undef": 0x4B2D0001,
    "r1": 0x4B2D0002,
    "r2_data": 0x4B2D0003,
    "r12": 0x4B2D000C,
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def field_hex(text: str, label: str) -> int | None:
    pattern = rf"^{re.escape(label)}: 0x([0-9a-fA-F]{{8}})$"
    match = re.search(pattern, text, re.M)
    return int(match.group(1), 16) if match else None


def field_text(text: str, label: str) -> str | None:
    pattern = rf"^{re.escape(label)}: (.+)$"
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else None


def add(check: list[tuple[str, bool, str]], name: str, condition: bool,
        detail: str = "") -> None:
    check.append((name, bool(condition), detail))


def run_profile(qemu: Path, version: str, profile: str, elf: Path,
                timeout: float) -> tuple[bool, int, int, Path]:
    run_dir = ROOT / "build" / "run" / profile
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "serial.log"
    guest_errors = run_dir / "guest-errors.log"
    evidence = run_dir / "runtime-evidence.txt"

    for stale in (log, guest_errors, evidence):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass

    def relative(path: Path) -> str:
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

    command = [
        str(qemu),
        "-M", "integratorcp",
        "-cpu", "arm1136",
        "-m", "128M",
        "-kernel", str(elf),
        "-display", "none",
        "-monitor", "none",
        "-serial", f"file:{relative(log)}",
        "-no-reboot",
        "-d", "guest_errors",
        "-D", relative(guest_errors),
    ]

    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    marker = TERMINAL_MARKERS[profile]
    deadline = time.monotonic() + timeout
    observed = ""
    while time.monotonic() < deadline:
        observed = read_text(log)
        if marker in observed:
            time.sleep(0.05)
            observed = read_text(log)
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
    add(checks, "guest produced serial output", bool(observed),
        "empty serial log")
    add(checks, "first serial line is the MinitOS banner",
        bool(lines) and lines[0] == BANNER,
        f"first line={lines[0]!r}" if lines else "no lines")
    add(checks, "board diagnostic is present",
        "board: integratorcp" in normalised)
    add(checks, "UART diagnostic is present",
        "uart: pl011 @ 0x16000000" in normalised)

    midr = field_hex(normalised, "cpu midr")
    if midr is None:
        add(checks, "CPU MIDR is reported", False, "no MIDR line")
    else:
        implementer = (midr >> 24) & 0xFF
        part = (midr >> 4) & 0xFFF
        add(checks, "CPU MIDR is reported", True)
        add(checks, "CPU implementer is ARM (0x41)", implementer == 0x41,
            f"implementer=0x{implementer:02x}")
        add(checks, "CPU part is ARM1136 (0xB36)", part == 0xB36,
            f"part=0x{part:03x}")

    add(checks, "low vector base is reported",
        "K2 vectors: low @ 0x00000000" in normalised)
    sctlr = field_hex(normalised, "K2 sctlr")
    add(checks, "boot SCTLR is reported", sctlr is not None)
    if sctlr is not None:
        add(checks, "SCTLR.V is 0 (low vectors)", (sctlr & (1 << 13)) == 0,
            f"SCTLR=0x{sctlr:08x}")

    cpsr = field_hex(normalised, "K2 cpsr")
    add(checks, "startup CPSR is reported", cpsr is not None)
    if cpsr is not None:
        add(checks, "startup mode is SVC", (cpsr & 0x1F) == 0x13,
            f"mode=0x{cpsr & 0x1F:02x}")
        add(checks, "startup IRQ is masked", (cpsr & (1 << 7)) != 0)
        add(checks, "startup FIQ is masked", (cpsr & (1 << 6)) != 0)

    frame_size = field_hex(normalised, "K2 frame bytes")
    frame_align = field_hex(normalised, "K2 frame align")
    add(checks, "exception frame size is 72 bytes", frame_size == 72,
        f"value={frame_size}")
    add(checks, "exception frame alignment is 8", frame_align == 8,
        f"value={frame_align}")
    for mode in ("svc", "und", "abt", "irq", "fiq"):
        add(checks, f"{mode.upper()} stack is reported",
            f"K2 stack {mode}:" in normalised)

    add(checks, f"terminal marker {marker!r} is present", marker in normalised,
        "timeout or missing marker")

    # Fail-stop evidence: the terminal marker must be the last output, and the
    # guest must not reboot and print a second banner. K2 has no reset loop.
    non_empty = [line for line in lines if line.strip()]
    add(checks, "terminal marker is the last serial line",
        bool(non_empty) and non_empty[-1] == marker,
        f"last line={non_empty[-1]!r}" if non_empty else "no lines")
    add(checks, "guest did not reboot after the terminal marker",
        normalised.count(BANNER) == 1,
        f"banner count={normalised.count(BANNER)}")

    if profile == "normal":
        add(checks, "normal profile selector is present",
            "K2 test: normal" in normalised)
        add(checks, "normal profile has no exception output",
            "EXCEPTION:" not in normalised)
        if sctlr is not None:
            add(checks, "normal run has SCTLR.A=0 and SCTLR.U=0",
                (sctlr & ((1 << 1) | (1 << 22))) == 0,
                f"SCTLR=0x{sctlr:08x}")
    elif profile == "undef":
        add(checks, "undefined-instruction test selector is present",
            "K2 test: undefined" in normalised)
        add(checks, "undefined instruction exception was reported",
            "EXCEPTION: UNDEFINED INSTRUCTION" in normalised)
        vector = field_hex(normalised, "vector")
        add(checks, "UND vector offset is 0x00000004", vector == 0x04,
            f"vector={vector}")
        add(checks, "handler mode is UND", field_text(normalised, "mode") == "UND",
            f"mode={field_text(normalised, 'mode')}")
        handler_cpsr = field_hex(normalised, "handler_cpsr")
        if handler_cpsr is None:
            add(checks, "handler CPSR is reported", False)
        else:
            add(checks, "handler CPSR is UND mode",
                (handler_cpsr & 0x1F) == 0x1B,
                f"mode=0x{handler_cpsr & 0x1F:02x}")
            add(checks, "handler IRQ is masked",
                (handler_cpsr & (1 << 7)) != 0)
            add(checks, "handler FIQ is masked",
                (handler_cpsr & (1 << 6)) != 0)
        spsr = field_hex(normalised, "spsr")
        add(checks, "interrupted context was SVC",
            spsr is not None and (spsr & 0x1F) == 0x13,
            f"spsr={spsr}")
        lr = field_hex(normalised, "lr")
        fault_pc = field_hex(normalised, "fault_pc")
        add(checks, "LR_und and fault_pc differ by 4",
            lr is not None and fault_pc is not None and lr - fault_pc == 4,
            f"lr={lr} fault_pc={fault_pc}")
        add(checks, "fault_pc lies in the loaded kernel image",
            fault_pc is not None and 0x00010000 <= fault_pc < 0x00020000,
            f"fault_pc={fault_pc}")
        add(checks, "saved r0 sentinel matches",
            field_hex(normalised, "r0") == SENTINELS["r0_undef"])
        add(checks, "saved r1 sentinel matches",
            field_hex(normalised, "r1") == SENTINELS["r1"])
        add(checks, "saved r12 sentinel matches",
            field_hex(normalised, "r12") == SENTINELS["r12"])
    else:
        add(checks, "data-abort test selector is present",
            "K2 test: data-abort" in normalised)
        before = field_hex(normalised, "K2 sctlr before")
        after = field_hex(normalised, "K2 sctlr after")
        add(checks, "pre-test SCTLR is reported", before is not None)
        add(checks, "post-test SCTLR is reported", after is not None)
        if after is not None:
            add(checks, "SCTLR.A and SCTLR.U read back as 1",
                (after & ((1 << 1) | (1 << 22))) ==
                ((1 << 1) | (1 << 22)),
                f"SCTLR=0x{after:08x}")
        probe = field_hex(normalised, "K2 alignment probe")
        add(checks, "alignment probe address is reported", probe is not None)
        if probe is not None:
            add(checks, "alignment probe is 16-byte aligned",
                probe % 16 == 0, f"probe=0x{probe:08x}")

        add(checks, "data abort exception was reported",
            "EXCEPTION: DATA ABORT" in normalised)
        vector = field_hex(normalised, "vector")
        add(checks, "Data Abort vector offset is 0x00000010", vector == 0x10,
            f"vector={vector}")
        add(checks, "handler mode is ABT", field_text(normalised, "mode") == "ABT",
            f"mode={field_text(normalised, 'mode')}")
        handler_cpsr = field_hex(normalised, "handler_cpsr")
        if handler_cpsr is None:
            add(checks, "handler CPSR is reported", False)
        else:
            add(checks, "handler CPSR is ABT mode",
                (handler_cpsr & 0x1F) == 0x17,
                f"mode=0x{handler_cpsr & 0x1F:02x}")
            add(checks, "handler IRQ is masked",
                (handler_cpsr & (1 << 7)) != 0)
            add(checks, "handler FIQ is masked",
                (handler_cpsr & (1 << 6)) != 0)
        spsr = field_hex(normalised, "spsr")
        add(checks, "interrupted context was SVC",
            spsr is not None and (spsr & 0x1F) == 0x13,
            f"spsr={spsr}")
        dfsr = field_hex(normalised, "dfsr")
        dfar = field_hex(normalised, "dfar")
        add(checks, "DFSR is reported", dfsr is not None)
        add(checks, "DFSR status is Alignment Fault (0b00001)",
            dfsr is not None and (dfsr & 0xF) == 1,
            f"dfsr={dfsr}")
        if probe is not None:
            add(checks, "DFAR equals the unaligned probe address probe+1",
                dfar == probe + 1, f"dfar={dfar} probe=0x{probe:08x}")
        lr = field_hex(normalised, "lr")
        fault_pc = field_hex(normalised, "fault_pc")
        add(checks, "LR_abt and fault_pc differ by 8",
            lr is not None and fault_pc is not None and lr - fault_pc == 8,
            f"lr={lr} fault_pc={fault_pc}")
        add(checks, "fault_pc lies in the loaded kernel image",
            fault_pc is not None and 0x00010000 <= fault_pc < 0x00020000,
            f"fault_pc={fault_pc}")
        add(checks, "saved r0 equals the unaligned probe address",
            probe is not None and field_hex(normalised, "r0") == probe + 1)
        add(checks, "saved r1 sentinel matches",
            field_hex(normalised, "r1") == SENTINELS["r1"])
        add(checks, "saved r2 sentinel matches",
            field_hex(normalised, "r2") == SENTINELS["r2_data"])
        add(checks, "saved r12 sentinel matches",
            field_hex(normalised, "r12") == SENTINELS["r12"])

    # QEMU's guest-error channel is diagnostic. Intentional architectural
    # faults are not guest errors; an unexpected entry is reported and fails.
    add(checks, "QEMU guest-error log is empty", not guest_text,
        guest_text.splitlines()[0] if guest_text else "")

    failed = sum(1 for _, ok, _ in checks if not ok)
    passed = len(checks) - failed

    print(f"=== runtime: {profile} ===")
    print("QEMU:", " ".join(command))
    for name, ok, detail in checks:
        if ok:
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name}" + (f": {detail}" if detail else ""))
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

    evidence_lines = [
        f"MinitOS K2 runtime evidence: {profile}",
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
    print()

    return failed == 0, passed, failed, evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run MinitOS K2 in QEMU")
    parser.add_argument("--profile", default="all",
                        choices=["all", *PROFILES],
                        help="profile to run (default: all)")
    parser.add_argument("--elf", help="explicit ELF path (single profile only)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="seconds to wait for the terminal marker (default: 10)")
    args = parser.parse_args(argv)

    if args.elf and args.profile == "all":
        print("RUNTIME CHECK: FAIL: --elf requires a single --profile",
              file=sys.stderr)
        return 2

    try:
        qemu = find_qemu()
        version = qemu_version(qemu)
    except QemuError as exc:
        print(f"RUNTIME CHECK: FAIL: {exc}", file=sys.stderr)
        return 2

    profiles = PROFILES if args.profile == "all" else [args.profile]
    total_passed = 0
    total_failed = 0
    failed_profiles = 0

    for profile in profiles:
        elf = (Path(args.elf).resolve() if args.elf
               else (ROOT / "build" / profile / "minitos-k2.elf"))
        if not elf.is_file():
            print(f"RUNTIME CHECK: FAIL: missing {elf}", file=sys.stderr)
            print("run: python tools/build.py build", file=sys.stderr)
            return 2

        ok, passed, failed, _ = run_profile(qemu, version, profile, elf,
                                            args.timeout)
        total_passed += passed
        total_failed += failed
        if not ok:
            failed_profiles += 1

    print("runtime summary:")
    for profile in profiles:
        # Per-profile result is already printed; the summary is about the run.
        print(f"  {profile}: see build/run/{profile}/runtime-evidence.txt")

    if failed_profiles:
        print(f"RUNTIME CHECK: FAIL ({failed_profiles}/{len(profiles)} profiles, "
              f"{total_failed} failed checks)")
        return 1

    print(f"RUNTIME CHECK: PASS ({len(profiles)} profiles, "
          f"{total_passed} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
