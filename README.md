# MinitOS K2 — ARMv6 exception handling

Independent implementation of the MinitOS K2 stage on top of the verified K1
kernel: a freestanding, 32-bit little-endian ARMv6 kernel that boots on the QEMU
`integratorcp` machine with an ARM1136 CPU, installs a real low-vector
exception table at `0x00000000`, and captures genuine Undefined Instruction and
Data Abort exceptions through UART diagnostics.

K1 is preserved as the reproducible baseline tag **`k1-baseline`** (commit
`6964e66`). K2 changes the boot and exception path; it does not rewrite K1
history and does not claim K1 behaviour that was not re-tested.

## Verified result

The acceptance sequence was executed on 2026-11-02 with QEMU 11.1.0 and
GCC 15.2.1. Three independent images prove three separate execution paths.

Normal profile:

```text
MINITOS KERNEL STARTED
board: integratorcp
uart: pl011 @ 0x16000000
cpu midr: 0x4117b363
K2 vectors: low @ 0x00000000
K2 sctlr: 0x00050078
K2 cpsr: 0x600001d3
K2 frame bytes: 0x00000048
K2 frame align: 0x00000008
K2 test: normal
K2 IDLE
```

Undefined Instruction profile (`udf #0` executed for real):

```text
K2 test: undefined
EXCEPTION: UNDEFINED INSTRUCTION
vector: 0x00000004
mode: UND
handler_cpsr: 0x600001db
lr: 0x00010240
spsr: 0x600001d3
spsr_mode: SVC
fault_pc: 0x0001023c
r0: 0x4b2d0001
r1: 0x4b2d0002
r2: 0x16000018
r12: 0x4b2d000c
K2 EXCEPTION CAPTURED
```

Data Abort profile (real unaligned word `LDR` with `SCTLR.A=1`, `SCTLR.U=1`):

```text
K2 test: data-abort
K2 sctlr before: 0x00050078
K2 sctlr after: 0x0045007a
K2 alignment probe: 0x00010e40
EXCEPTION: DATA ABORT
vector: 0x00000010
mode: ABT
handler_cpsr: 0x600001d7
lr: 0x0001026c
spsr: 0x600001d3
spsr_mode: SVC
dfsr: 0x00000001
dfar: 0x00010e41
fault_pc: 0x00010264
r0: 0x00010e41
r1: 0x4b2d0002
r2: 0x4b2d0003
r12: 0x4b2d000c
K2 EXCEPTION CAPTURED
```

| Criterion | Result |
|---|---|
| K1 preserved as a reproducible baseline tag | **PASS** |
| Low vector table at `0x00000000`, `SCTLR.V=0` read back | **PASS** |
| All eight vector slots branch to defined entries | **PASS** |
| SVC/UND/ABT/IRQ/FIQ banked stacks configured before C | **PASS** |
| Undefined Instruction enters UND mode with correct SPSR/LR | **PASS** |
| Data Abort enters ABT mode with correct DFSR/DFAR | **PASS** |
| Exception frame size/alignment checked at compile and ELF level | **PASS** |
| Fault paths halt after `K2 EXCEPTION CAPTURED` | **PASS** |
| Three profiles build, run and log independently | **PASS** |
| Repeated clean builds are byte-identical | **PASS** |
| Samsung Galaxy Gio / MSM7227 execution | **NOT RUN** |

See [docs/K2_ACCEPTANCE.md](docs/K2_ACCEPTANCE.md) for the K2-01…K2-14 matrix
and [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md)
for everything that is *not* verified. K1 evidence is archived under
[docs/evidence/k1/](docs/evidence/k1/).

## Platform boundary

This kernel targets QEMU's **ARM Integrator/CP** reference machine only.

- The vector table is linked at `0x00000000` because K2 clears `SCTLR.V`; this
  is the ARM1136 low-vector base, not a Gio address.
- The kernel image still starts at `0x00010000`, which is a QEMU reference
  layout, **not** a Galaxy Gio load address.
- UART0 at `0x16000000` is the **QEMU Integrator/CP** PL011, **not** a verified
  MSM7227 peripheral address.
- The Gio boot chain, SDRAM map, bootloader protocol and peripheral map are
  unknown here and are deliberately not assumed.
- Do not flash this image to a phone.

The independent board layer exists so a future Gio port can add a different
board descriptor and boot path without rewriting the kernel core.

## What K2 implements

- 32-byte low exception vector table at physical/virtual address 0, in its own
  executable `PT_LOAD` segment.
- Reset path that selects low vectors, verifies `SCTLR.V=0` by read-back, and
  establishes a known normal-run alignment policy (`A=0`, `U=0`).
- 8-byte-aligned banked stacks for SVC (16 KiB), UND (4 KiB), ABT (4 KiB),
  IRQ (2 KiB) and FIQ (1 KiB), installed before the first C call.
- Eight vector slots: reset, Undefined Instruction, SVC, Prefetch Abort, Data
  Abort, reserved, IRQ and FIQ.
- Assembly exception entry stubs that save `r0-r12`, banked LR, SPSR, the
  vector offset and — for Data Abort — DFSR/DFAR into a checked 72-byte frame.
- C diagnostic handlers for Undefined Instruction and Data Abort that print the
  mode, CPSR, LR, SPSR, fault PC and sentinel registers, then halt.
- Safe fail-stop stubs for SVC, Prefetch Abort, IRQ and FIQ; the reserved slot
  is a dependency-free self-loop.
- Real fault generators: ARM `udf #0` and an `add r0,#1; ldr r1,[r0]` unaligned
  word load.
- Per-profile build artifacts, an ELF verifier, a three-process QEMU runtime
  harness and a reproducible-build check.
- Freestanding C11 kernel, no libc, no libgcc, no host runtime.

## What K2 intentionally does not implement

Exception recovery/resume, interrupt handling, MMU setup, cache configuration,
timers, physical memory allocator, scheduler, framebuffer, application
environment, UART RX, DMA or real-hardware support. The vectors and per-mode
stacks are real and tested; recovery, IRQ dispatch and a syscall gate are not.

## Quick start

### 1. Toolchain

The reference toolchain is pinned:

- xPack GNU Arm Embedded GCC **15.2.1-1.1**
- archive SHA-256
  `bae6a3d1667697ce750c3b13d6d26d80973ecedc2cc87bf04869e83447fd93ea`

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch-toolchain.ps1
$env:MINITOS_ARM_BIN = "$env:LOCALAPPDATA\Tools\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin"
```

On other hosts, install an `arm-none-eabi-gcc` toolchain and either put it on
`PATH` or set `MINITOS_ARM_BIN` to its `bin` directory. The build driver also
accepts `ARM_GCC_BIN`.

### 2. Build and check

```sh
python tools/build.py build
python tools/build.py verify --no-build
python tools/verify_platform.py
python tools/run_qemu.py
python tools/build.py repro
```

Run the complete sequence (and copy evidence into `docs/evidence/`):

```sh
python tools/acceptance.py --evidence
```

With GNU Make available, the same operations are wrapped as:

```sh
make build verify platform run repro acceptance
```

A single profile can be selected with `--profile normal|undef|data-abort`
(`PROFILE=...` for Make).

### 3. Manual QEMU run

```sh
qemu-system-arm -M integratorcp -cpu arm1136 -m 128M \
    -kernel build/normal/minitos-k2.elf -display none -monitor none -serial stdio
```

or on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-qemu.ps1
```

The normal profile never exits; stop QEMU with Ctrl+C. The fault profiles reach
`K2 EXCEPTION CAPTURED` and then halt inside the handler. The automated harness
waits for the profile's terminal marker and terminates QEMU itself.

## Build outputs

`build/` contains one directory per profile (`normal/`, `undef/`,
`data-abort/`):

| File | Purpose |
|---|---|
| `minitos-k2.elf` | ELF32 ARM executable loaded by QEMU |
| `minitos-k2.bin` | flat binary from the vector base |
| `minitos-k2.map` | linker map |
| `disassembly*.txt` | full, vector, startup, handler and test disassembly |
| `readelf-*.txt` | ELF header, segments, sections, symbols, attributes |
| `sizes.txt`, `sizes-all.txt` | size reports |
| `memory-usage.txt` | linker memory-region usage |
| `SHA256SUMS.txt` | per-profile artifact hashes |
| `run/<profile>/serial.log` | raw UART output for that profile |
| `run/<profile>/runtime-evidence.txt` | runtime checks and serial output |
| `qemu-mtree.txt` | live QEMU memory map from QMP |
| `repro.txt` | double-build hash comparison |
| `acceptance.txt` | full acceptance log |

## Project layout

```text
minitos-k1/
├── include/minitos/          public interfaces: board, console, exception, profiles
├── src/
│   ├── arch/armv6/           start.S, exception.S, CPSR/CP15 primitives
│   ├── board/                board descriptor (integratorcp)
│   ├── drivers/              PL011 UART driver
│   └── kernel/               console facade, K2 fault tests, kernel_main
├── linker/integratorcp.ld    low vectors, kernel, stacks and memory budget
├── tools/                    build, ELF check, QEMU platform/runtime tests
├── scripts/                  manual toolchain and QEMU launchers
├── docs/                     architecture, ABI, decisions, acceptance, evidence
└── Makefile                  thin wrapper over tools/build.py
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — boot flow, memory layout,
  exception path, module contracts and extension points.
- [docs/EXCEPTION_ABI.md](docs/EXCEPTION_ABI.md) — vector table, entry stubs,
  saved frame layout, mode/stack rules and DFSR/DFAR handling.
- [docs/PLATFORM_INTEGRATORCP.md](docs/PLATFORM_INTEGRATORCP.md) — verified
  QEMU machine map, PL011 programming model and load contract.
- [docs/K0_ANALYSIS.md](docs/K0_ANALYSIS.md) — what K0 actually contains and
  which assumptions this project rejects.
- [docs/DECISIONS.md](docs/DECISIONS.md) — engineering decision journal.
- [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) —
  explicit unverified assumptions and limits.
- [docs/K2_ACCEPTANCE.md](docs/K2_ACCEPTANCE.md) — K2-01…K2-14 acceptance
  matrix, commands, hashes and runtime evidence.
- [docs/K1_ACCEPTANCE.md](docs/K1_ACCEPTANCE.md) — preserved K1 baseline report.
- [docs/evidence/](docs/evidence/) — raw captured K2 evidence.
- [docs/evidence/k1/](docs/evidence/k1/) — archived K1 baseline evidence.

## Reproducibility

`tools/build.py repro` performs two independent clean builds of every profile
and compares the SHA-256 of both the ELF and the flat binary. Byte-identical
output was observed on the reference host with the pinned toolchain.
Cross-host and cross-toolchain byte identity is **not** claimed; the compiler
version is part of the build definition.
