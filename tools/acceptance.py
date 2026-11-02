#!/usr/bin/env python3
"""Run the complete MinitOS K1 acceptance sequence.

The sequence is intentionally sequential and fail-fast: a later PASS must
never be printed after an earlier step failed. Every command and its output
are captured in build/acceptance.txt. With --evidence, the machine-readable
evidence is copied into docs/evidence/ for the repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
EVIDENCE = ROOT / "docs" / "evidence"

STEPS = [
    ("build", [sys.executable, "tools/build.py", "build"]),
    ("ELF structure", [sys.executable, "tools/build.py", "verify", "--no-build"]),
    ("QEMU platform", [sys.executable, "tools/verify_platform.py"]),
    ("runtime execution", [sys.executable, "tools/run_qemu.py"]),
    ("reproducible build", [sys.executable, "tools/build.py", "repro"]),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MinitOS K1 acceptance sequence")
    parser.add_argument("--evidence", action="store_true",
                        help="copy logs into docs/evidence/")
    args = parser.parse_args(argv)

    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    log_lines: list[str] = [
        "MinitOS K1 acceptance run",
        f"started: {started}",
        f"root: {ROOT}",
        "",
    ]
    results: list[tuple[str, bool]] = []

    for index, (name, command) in enumerate(STEPS, start=1):
        print(f"=== [{index}/{len(STEPS)}] {name} ===")
        print("$ " + " ".join(command))
        log_lines.append(f"=== [{index}/{len(STEPS)}] {name} ===")
        log_lines.append("$ " + " ".join(command))

        result = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = result.stdout.rstrip("\n")
        if output:
            print(output)
            log_lines.append(output)
        log_lines.append("")

        ok = result.returncode == 0
        results.append((name, ok))
        if not ok:
            print(f"ACCEPTANCE: FAIL at step {index} ({name})")
            log_lines.append(f"ACCEPTANCE: FAIL at step {index} ({name})")
            break

    all_ok = len(results) == len(STEPS) and all(ok for _, ok in results)
    summary = ["", "summary:"]
    for name, ok in results:
        summary.append(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    summary.append("")
    summary.append(f"RESULT: {'PASS' if all_ok else 'FAIL'}")
    print("\n".join(summary))
    log_lines.extend(summary)

    BUILD.mkdir(parents=True, exist_ok=True)
    acceptance_log = BUILD / "acceptance.txt"
    acceptance_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    if args.evidence:
        copy_evidence(acceptance_log)
        print(f"evidence copied to {EVIDENCE}")

    return 0 if all_ok else 1


def copy_evidence(acceptance_log: Path) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    mapping = {
        "serial.log": "qemu-serial.txt",
        "qemu-mtree.txt": "qemu-mtree.txt",
        "qemu-platform.txt": "qemu-platform.txt",
        "runtime-evidence.txt": "runtime-evidence.txt",
        "SHA256SUMS.txt": "sha256sums.txt",
        "toolchain.txt": "toolchain.txt",
        "sizes.txt": "sizes.txt",
        "repro.txt": "repro.txt",
        "readelf-header.txt": "readelf-header.txt",
        "readelf-program-headers.txt": "readelf-program-headers.txt",
        "readelf-sections.txt": "readelf-sections.txt",
        "readelf-symbols.txt": "readelf-symbols.txt",
        "readelf-attributes.txt": "readelf-attributes.txt",
    }
    for source_name, target_name in mapping.items():
        source = BUILD / source_name
        if source.is_file():
            shutil.copyfile(source, EVIDENCE / target_name)

    shutil.copyfile(acceptance_log, EVIDENCE / "acceptance-run.txt")


if __name__ == "__main__":
    raise SystemExit(main())
