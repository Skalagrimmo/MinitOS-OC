#!/usr/bin/env python3
"""MinitOS K2 build driver.

The kernel is small, but the build is deliberately explicit: fixed source
lists, fixed flags, a fixed link order, no implicit libc/libgcc, and one
artifact set per K2 test profile. A new translation unit or profile must be
added here.

Commands:
    build     compile/link all selected profiles and write inspection files
    verify    build (unless --no-build) and run the structural ELF checker
    repro     build every selected profile twice and compare hashes
    info      print toolchain versions and artifact hashes
    disasm    print the normal-profile disassembly
    clean     remove the output directory
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "build"
LINKER_SCRIPT = ROOT / "linker" / "integratorcp.ld"

NAME = "minitos-k2"

PROFILES = {
    "normal": 0,
    "undef": 1,
    "data-abort": 2,
}
PROFILE_ORDER = ["normal", "undef", "data-abort"]

# Source lists are explicit: a new translation unit must be added here.
ASM_SOURCES = [
    "src/arch/armv6/start.S",
    "src/arch/armv6/exception.S",
]

C_SOURCES = [
    "src/arch/armv6/cpu.c",
    "src/arch/armv6/exception.c",
    "src/board/board_integratorcp.c",
    "src/drivers/pl011.c",
    "src/kernel/console.c",
    "src/kernel/k2_tests.c",
    "src/kernel/main.c",
]

# ARM1136JF-S is the ARMv6 core class used by the MSM7227 and by the QEMU
# arm1136 model. K2 does not use VFP; soft-float keeps the ABI independent of
# an FPU that a future board port may not enable.
ARCH_FLAGS = [
    "-mcpu=arm1136jf-s",
    "-marm",
    "-mfloat-abi=soft",
]

COMMON_FLAGS = [
    "-ffreestanding",
    "-fno-builtin",
    "-fno-common",
    "-fno-stack-protector",
    "-fno-pic",
    "-fno-pie",
    "-fno-unwind-tables",
    "-fno-asynchronous-unwind-tables",
    "-ffunction-sections",
    "-fdata-sections",
    "-frandom-seed=minitos-k2",
    "-ffile-prefix-map=" + str(ROOT).replace("\\", "/") + "=.",
    "-g",
]

CFLAGS = COMMON_FLAGS + [
    "-std=c11",
    "-O2",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
    "-Wundef",
    "-Wvla",
    "-fstack-usage",
    "-I" + str(ROOT / "include"),
    "-I" + str(ROOT / "src"),
]

ASFLAGS = COMMON_FLAGS


class BuildError(RuntimeError):
    pass


def _toolchain_candidates():
    env_value = os.environ.get("MINITOS_ARM_BIN") or os.environ.get("ARM_GCC_BIN")
    if env_value:
        path = Path(env_value)
        yield path.parent if path.is_file() else path

    on_path = shutil.which("arm-none-eabi-gcc")
    if on_path:
        yield Path(on_path).parent

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            tools = Path(local) / "Tools"
            if tools.is_dir():
                yield from sorted(tools.glob("xpack-arm-none-eabi-gcc-*/bin"),
                                  reverse=True)
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(var)
            if base:
                yield Path(base) / "GNU Arm Embedded Toolchain" / "bin"
    else:
        yield Path("/usr/bin")
        yield Path("/usr/local/bin")


def find_toolchain() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    for candidate in _toolchain_candidates():
        gcc = candidate / ("arm-none-eabi-gcc" + suffix)
        if gcc.is_file():
            return candidate
    raise BuildError(
        "ARM toolchain not found. Set MINITOS_ARM_BIN to the directory that "
        "contains arm-none-eabi-gcc, or put it on PATH."
    )


class Toolchain:
    def __init__(self) -> None:
        self.bin = find_toolchain()
        self.suffix = ".exe" if os.name == "nt" else ""

    def __call__(self, name: str) -> str:
        path = self.bin / (name + self.suffix)
        if not path.is_file():
            raise BuildError(f"missing tool: {path}")
        return str(path)

    @property
    def gcc(self) -> str:
        return self("arm-none-eabi-gcc")


def run(cmd, *, cwd=ROOT, check=True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        raise BuildError(f"command failed ({proc.returncode}): {' '.join(map(str, cmd))}")
    return proc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_path(objdir: Path, source: str) -> Path:
    # Keep the source extension in the object name: exception.S and
    # exception.c are different translation units in the same directory.
    stem = source.replace("\\", "_").replace("/", "_").replace(".", "_")
    return objdir / (stem + ".o")


def profile_flags(profile: str) -> list[str]:
    if profile not in PROFILES:
        raise BuildError(f"unknown profile {profile!r}")
    return [f"-DMINITOS_TEST_MODE={PROFILES[profile]}", "-DMINITOS_K2=1"]


def compile_sources(tc: Toolchain, objdir: Path, profile: str) -> list[Path]:
    objects: list[Path] = []
    extra = profile_flags(profile)

    for source in ASM_SOURCES:
        obj = object_path(objdir, source)
        run([tc.gcc, *ASFLAGS, *extra, "-c", source, "-o", str(obj)])
        objects.append(obj)

    for source in C_SOURCES:
        obj = object_path(objdir, source)
        run([tc.gcc, *CFLAGS, *extra, "-c", source, "-o", str(obj)])
        objects.append(obj)

    return objects


def collect_stack_usage(objdir: Path) -> list[tuple[int, str, str]]:
    entries: list[tuple[int, str, str]] = []
    for su_file in sorted(objdir.glob("*.su")):
        for line in su_file.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                size = int(parts[1])
            except ValueError:
                continue
            location = parts[0]
            qualifier = parts[2] if len(parts) > 2 else ""
            entries.append((size, location, qualifier))
    return entries


def _disassemble_symbol(tc: Toolchain, elf: Path, symbol: str,
                        symbols: set[str]) -> str:
    if symbol not in symbols:
        return ""
    result = run([tc("arm-none-eabi-objdump"), "-d",
                  f"--disassemble={symbol}", str(elf)], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    return f"===== {symbol} =====\n{result.stdout.strip()}\n\n"


def write_disassemblies(tc: Toolchain, elf: Path, outdir: Path) -> None:
    objdump = tc("arm-none-eabi-objdump")

    full = run([objdump, "-d", str(elf)]).stdout
    (outdir / "disassembly.txt").write_text(full, encoding="utf-8")

    vectors = run([objdump, "-d", "--start-address=0", "--stop-address=32",
                   str(elf)]).stdout
    (outdir / "disassembly-vectors.txt").write_text(vectors, encoding="utf-8")

    symbols_text = run([tc("arm-none-eabi-nm"), "-n", str(elf)]).stdout
    symbols = set()
    for line in symbols_text.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            symbols.add(parts[2])

    selected = [
        ("disassembly-startup.txt", ["_start"]),
        ("disassembly-handlers.txt", [
            "undef_entry", "data_abort_entry", "svc_entry", "prefetch_entry",
            "reserved_entry", "irq_entry", "fiq_entry",
            "exception_dispatch", "exception_unexpected",
        ]),
        ("disassembly-tests.txt", [
            "k2_trigger_undef", "k2_trigger_data_abort",
            "k2_undef_test", "k2_data_abort_test",
        ]),
    ]
    for filename, names in selected:
        chunks = [_disassemble_symbol(tc, elf, name, symbols) for name in names]
        (outdir / filename).write_text("".join(chunks), encoding="utf-8")


def build_one(tc: Toolchain, profile: str, outdir: Path,
              announce: bool = True) -> tuple[Path, Path]:
    outdir = outdir.resolve()
    if outdir.exists():
        shutil.rmtree(outdir)
    objdir = outdir / "obj"
    objdir.mkdir(parents=True)

    objects = compile_sources(tc, objdir, profile)

    elf = outdir / f"{NAME}.elf"
    binary = outdir / f"{NAME}.bin"
    map_file = outdir / f"{NAME}.map"
    memory_usage = outdir / "memory-usage.txt"

    link_cmd = [
        tc.gcc,
        *ARCH_FLAGS,
        "-nostdlib",
        "-nostartfiles",
        "-nodefaultlibs",
        "-Wl,-T," + str(LINKER_SCRIPT),
        "-Wl,-Map," + str(map_file),
        "-Wl,--build-id=none",
        "-Wl,--gc-sections",
        "-Wl,--no-undefined",
        "-Wl,--fatal-warnings",
        "-Wl,--print-memory-usage",
        *[str(obj) for obj in objects],
        "-o", str(elf),
    ]
    link = run(link_cmd)
    # --print-memory-usage writes to stdout on some binutils versions and to
    # stderr on others. Record whichever stream carried it.
    memory_usage.write_text(link.stdout + link.stderr, encoding="utf-8")

    run([tc("arm-none-eabi-objcopy"), "-O", "binary", str(elf), str(binary)])

    write_disassemblies(tc, elf, outdir)

    readelf = tc("arm-none-eabi-readelf")
    for option, filename in (
        ("-h", "readelf-header.txt"),
        ("-l", "readelf-program-headers.txt"),
        ("-S", "readelf-sections.txt"),
        ("-s", "readelf-symbols.txt"),
        ("-A", "readelf-attributes.txt"),
    ):
        text = run([readelf, option, str(elf)]).stdout
        (outdir / filename).write_text(text, encoding="utf-8")

    sizes = run([tc("arm-none-eabi-size"), str(elf)]).stdout
    (outdir / "sizes.txt").write_text(sizes, encoding="utf-8")
    size_all = run([tc("arm-none-eabi-size"), "-A", str(elf)]).stdout
    (outdir / "sizes-all.txt").write_text(size_all, encoding="utf-8")

    symbols = run([tc("arm-none-eabi-nm"), "-n", str(elf)]).stdout
    (outdir / "symbols.txt").write_text(symbols, encoding="utf-8")

    toolchain_report = [
        run([tc.gcc, "--version"]).stdout.strip(),
        run([tc.gcc, "-dumpmachine"]).stdout.strip(),
        run([tc("arm-none-eabi-ld"), "--version"]).stdout.strip(),
        f"profile: {profile}",
        f"python: {platform.python_version()}",
        f"host: {platform.platform()}",
        f"root: {ROOT}",
    ]
    (outdir / "toolchain.txt").write_text("\n".join(toolchain_report) + "\n",
                                          encoding="utf-8")

    checksums = [
        f"{sha256(elf)}  {elf.name}",
        f"{sha256(binary)}  {binary.name}",
    ]
    (outdir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n",
                                           encoding="utf-8")

    stack_entries = collect_stack_usage(objdir)
    max_stack = max((entry[0] for entry in stack_entries), default=0)

    if announce:
        print(f"profile   : {profile}")
        print(f"toolchain : {tc.gcc}")
        print(f"ELF       : {elf} ({elf.stat().st_size} bytes)")
        print(f"  sha256  : {sha256(elf)}")
        print(f"BIN       : {binary} ({binary.stat().st_size} bytes)")
        print(f"  sha256  : {sha256(binary)}")
        print("size      :")
        for line in sizes.strip().splitlines():
            print("  " + line)
        if stack_entries:
            print(f"stack use : max {max_stack} bytes "
                  f"({max((e for e in stack_entries if e[0] == max_stack))[1]})")
        print(f"artifacts : {outdir}")

    return elf, binary


def selected_profiles(value: str) -> list[str]:
    if value == "all":
        return list(PROFILE_ORDER)
    if value not in PROFILES:
        raise BuildError(f"unknown profile {value!r}")
    return [value]


def cmd_build(args) -> int:
    tc = Toolchain()
    base = Path(args.out).resolve()
    profiles = selected_profiles(args.profile)

    combined_hashes: list[str] = []
    for profile in profiles:
        print(f"=== building profile: {profile} ===")
        elf, binary = build_one(tc, profile, base / profile)
        combined_hashes.append(f"{sha256(elf)}  {profile}/{elf.name}")
        combined_hashes.append(f"{sha256(binary)}  {profile}/{binary.name}")

    (base / "SHA256SUMS.txt").write_text("\n".join(combined_hashes) + "\n",
                                          encoding="utf-8")

    reference = base / profiles[0]
    for filename, target in (
        ("toolchain.txt", "toolchain.txt"),
        ("sizes-all.txt", "sizes-all.txt"),
    ):
        source = reference / filename
        if source.is_file():
            shutil.copyfile(source, base / target)

    print(f"all artifacts under {base}")
    return 0


def cmd_verify(args) -> int:
    outdir = Path(args.out).resolve()
    profiles = selected_profiles(args.profile)
    if not args.no_build:
        build_args = argparse.Namespace(out=str(outdir), profile=args.profile)
        cmd_build(build_args)

    checker = ROOT / "tools" / "elfcheck.py"
    combined: list[str] = []
    failed = 0
    for profile in profiles:
        profile_dir = outdir / profile
        elf = profile_dir / f"{NAME}.elf"
        binary = profile_dir / f"{NAME}.bin"
        if not elf.is_file() or not binary.is_file():
            raise BuildError(f"missing artifacts for {profile}; run build first")

        result = run([sys.executable, str(checker), str(elf),
                      "--bin", str(binary), "--profile", profile],
                     check=False)
        print(f"=== ELF check: {profile} ===")
        print(result.stdout, end="")
        combined.append(f"=== {profile} ===")
        combined.append(result.stdout.rstrip("\n"))
        if result.returncode != 0:
            failed += 1
            print(result.stderr, end="", file=sys.stderr)
            combined.append(result.stderr.rstrip("\n"))

    (outdir / "elf-check.txt").write_text("\n".join(combined) + "\n",
                                          encoding="utf-8")
    if failed:
        print(f"ELF CHECK: FAIL ({failed} profile(s))")
        return 1
    print(f"ELF CHECK: PASS ({len(profiles)} profile(s))")
    return 0


def cmd_repro(args) -> int:
    tc = Toolchain()
    base = Path(args.out).resolve()
    profiles = selected_profiles(args.profile)

    ok = True
    lines: list[str] = []
    for profile in profiles:
        print(f"building repro-a/{profile} ...")
        a_elf, a_bin = build_one(tc, profile, base / "repro-a" / profile,
                                 announce=False)
        print(f"building repro-b/{profile} ...")
        b_elf, b_bin = build_one(tc, profile, base / "repro-b" / profile,
                                 announce=False)

        for name, a_path, b_path in (
            (f"{profile}/{NAME}.elf", a_elf, b_elf),
            (f"{profile}/{NAME}.bin", a_bin, b_bin),
        ):
            a_hash = sha256(a_path)
            b_hash = sha256(b_path)
            same = a_hash == b_hash
            lines.append(f"{name}: {a_hash}  {'MATCH' if same else 'MISMATCH'}")
            if not same:
                ok = False

    report = "\n".join(lines) + "\n"
    (base / "repro.txt").write_text(report, encoding="utf-8")
    print(report, end="")

    if not ok:
        print("REPRODUCIBLE BUILD: FAIL", file=sys.stderr)
        return 1

    print("REPRODUCIBLE BUILD: PASS")
    return 0


def cmd_info(args) -> int:
    outdir = Path(args.out).resolve()
    try:
        tc = Toolchain()
        print(tc.gcc)
        print(run([tc.gcc, "--version"]).stdout.strip())
        print("target:", run([tc.gcc, "-dumpmachine"]).stdout.strip())
    except BuildError as exc:
        print(f"toolchain: {exc}")

    for profile in PROFILE_ORDER:
        print(f"[{profile}]")
        for name in (f"{NAME}.elf", f"{NAME}.bin"):
            path = outdir / profile / name
            if path.is_file():
                print(f"  {name}: {path.stat().st_size} bytes  "
                      f"sha256={sha256(path)}")
            else:
                print(f"  {name}: not built")

    try:
        from qemu_common import find_qemu
        qemu = find_qemu()
        version = run([qemu, "--version"]).stdout.splitlines()[0]
        print(f"qemu: {qemu}")
        print(f"      {version}")
    except Exception as exc:  # noqa: BLE001 - informational command
        print(f"qemu: not available ({exc})")

    return 0


def cmd_disasm(args) -> int:
    outdir = Path(args.out).resolve()
    elf = outdir / "normal" / f"{NAME}.elf"
    if not elf.is_file():
        raise BuildError(f"missing {elf}; run build first")
    tc = Toolchain()
    print(run([tc("arm-none-eabi-objdump"), "-d", str(elf)]).stdout, end="")
    return 0


def cmd_clean(args) -> int:
    outdir = Path(args.out).resolve()
    if outdir.exists():
        shutil.rmtree(outdir)
        print(f"removed {outdir}")
    else:
        print(f"nothing to remove at {outdir}")
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MinitOS K2 build driver")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--out", default=str(DEFAULT_OUT),
                       help="output base directory (default: build)")
        p.add_argument("--profile", default="all",
                       choices=["all", *PROFILE_ORDER],
                       help="test profile (default: all)")
        return p

    add("build", "compile and link the selected profiles")
    verify = add("verify", "run the structural ELF checker")
    verify.add_argument("--no-build", action="store_true",
                        help="use the existing artifacts instead of rebuilding")
    add("repro", "build twice and compare artifact hashes")
    add("info", "print toolchain and artifact information")
    add("disasm", "print the normal-profile disassembly")
    add("clean", "remove the output directory")
    return parser


def main(argv=None) -> int:
    args = make_parser().parse_args(argv)
    handlers = {
        "build": cmd_build,
        "verify": cmd_verify,
        "repro": cmd_repro,
        "info": cmd_info,
        "disasm": cmd_disasm,
        "clean": cmd_clean,
    }
    try:
        return handlers[args.command](args)
    except BuildError as exc:
        print(f"BUILD ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
