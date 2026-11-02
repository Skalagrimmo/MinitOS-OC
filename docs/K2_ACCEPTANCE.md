# K2 Acceptance

**Status: PASS** for the checks listed below, on the recorded host and
toolchain. This document does not claim any test that was not executed.

K1 is preserved as Git tag `k1-baseline` (commit `6964e66`). K2 is the
exception-handling stage described by `MINITOS-K2-TZ`; its evidence does not
replace or reinterpret the archived K1 evidence.

## 1. Environment

| Item | Value |
|---|---|
| Date of run | 2026-11-02T11:28:16+02:00 |
| Host | Windows 10 Pro, build 19045 |
| Python | 3.15.2 |
| Compiler | xPack GNU Arm Embedded GCC 15.2.1 20251203 |
| Target triple | `arm-none-eabi` |
| Linker | GNU ld 2.45.1.20251203 |
| QEMU | 11.1.0 (`v11.1.0-12130-ge470268ff4`) |
| Machine / CPU | `integratorcp` / `arm1136` |
| RAM | `-m 128M` |

Artifact hashes:

| Profile | ELF SHA-256 | BIN SHA-256 |
|---|---|---|
| `normal` | `176d1acc5b21432d9cc8f227f1572576c63b9e1038a4f0575a7ee35d863ea63c` | `4ab2ca63f5c5a8e923d293209da93ae39a1d53b7b4df5add27ba248676bcd2db` |
| `undef` | `23e8aafa191e731f17bf227d7af1fcd9ad77940e9eb2602ca12d75e898dc2273` | `ad23fd42f4cbd5bffa1fdf7eadfe3362f302913251eebec35232c62d89122e2b` |
| `data-abort` | `306bf5bc6509cbdcc856bbe353e115cc93d1330f0e67135d381e6c9e35b9330a` | `792e6e91e7287e220b83200849ed1c09d09ce6350a27c4aae5a13614e1a47ba7` |

## 2. Acceptance command

The complete sequence was run with:

```sh
python tools/acceptance.py --evidence
```

It executes, in order, and stops at the first failure:

1. `python tools/build.py build`
2. `python tools/build.py verify --no-build`
3. `python tools/verify_platform.py`
4. `python tools/run_qemu.py`
5. `python tools/build.py repro`

The full captured log is
[`docs/evidence/acceptance-run.txt`](evidence/acceptance-run.txt).

Result summary:

```text
ELF CHECK: PASS (3 profile(s))          normal 105, undef 105, data-abort 107 checks
PLATFORM CHECK: PASS (7 checks)
RUNTIME CHECK: PASS (3 profiles, 113 checks)
REPRODUCIBLE BUILD: PASS                6/6 ELF/BIN hashes matched
RESULT: PASS                            5/5 acceptance steps
```

## 3. K2-01…K2-14 matrix

| ID | Requirement | Result | Evidence |
|---|---|---|---|
| K2-01 | K1 preserved as a reproducible baseline build/run | **PASS** | tag `k1-baseline` on commit `6964e66`; archived K1 report and evidence in `docs/evidence/k1/` |
| K2-02 | Active table has all 8 vector slots | **PASS** | `.vectors` 32 B at `0x0` in its own `PT_LOAD`; all 8 branches decoded by `elfcheck.py`; `disassembly-vectors.txt` |
| K2-03 | Low vectors really active on ARM1136 | **PASS** | `SCTLR.V=0` written and read back in `disassembly-startup.txt`; runtime `K2 sctlr: 0x00050078` |
| K2-04 | Kernel entry remains `0x00010000` | **PASS** | `e_entry = _start = reset_handler = 0x00010000`; linker assertions and ELF checks |
| K2-05 | SVC/UND/ABT stacks configured before C | **PASS** | 16/4/4 KiB regions, 8-byte aligned, contiguous; startup disassembly and `symbols.txt` |
| K2-06 | IRQ/FIQ stacks configured and safe stubs present | **PASS** | 2/1 KiB regions reported at runtime; `irq_entry`/`fiq_entry` in `disassembly-handlers.txt` |
| K2-07 | Undefined Instruction really enters UND mode | **PASS** | real `udf #0`; `undef-uart.log`, `undef-runtime.txt` |
| K2-08 | Data Abort really enters ABT mode | **PASS** | real unaligned `LDR`; `data-abort-uart.log`, `data-abort-runtime.txt` |
| K2-09 | Alignment test uses an unaligned RAM word `LDR` | **PASS** | `add r0,#1; ldr r1,[r0]` in disassembly; `DFSR=0x1`, `DFAR=probe+1` |
| K2-10 | Exception frame has a checked ABI | **PASS** | 72 bytes / 8-byte alignment at C compile time and in the ELF; `EXCEPTION_ABI.md` |
| K2-11 | Fault path is fail-stop, not a reset loop | **PASS** | `K2 EXCEPTION CAPTURED` is the last serial line; no second banner; handler disassembly ends in a halt loop |
| K2-12 | `normal`, `undef`, `data-abort` are separate profiles | **PASS** | three ELFs and three independent UART logs under `build/run/` and `docs/evidence/` |
| K2-13 | Builds are reproducible | **PASS** | two clean builds; 6/6 ELF/BIN hashes match |
| K2-14 | Assumptions/limitations and acceptance report | **PASS** | `ASSUMPTIONS_AND_LIMITATIONS.md`, this report, `docs/evidence/README.md` |

## 4. Vector table and entry point

From `disassembly-vectors.txt` (normal profile):

```text
00000000 <_vectors>:
   0: ea003ffe  b 10000 <_start>            @ 0x00 Reset
   4: ea004033  b 100d8 <undef_entry>        @ 0x04 Undefined Instruction
   8: ea00404f  b 1014c <svc_entry>          @ 0x08 SVC
   c: ea00405c  b 10184 <prefetch_entry>     @ 0x0C Prefetch Abort
  10: ea00403e  b 10110 <data_abort_entry>   @ 0x10 Data Abort
  14: ea004084  b 1022c <reserved_entry>     @ 0x14 Reserved
  18: ea004067  b 101bc <irq_entry>          @ 0x18 IRQ
  1c: ea004074  b 101f4 <fiq_entry>          @ 0x1C FIQ
```

The ELF checker confirms:

- `.vectors` is at virtual/physical address `0x00000000`, size 32, executable;
- the vector segment is exactly 32 bytes on disk and in memory;
- `_start` and `reset_handler` are at `0x00010000`;
- the kernel text has a separate `PT_LOAD` at `0x00010000`;
- no other allocated section hides in `0x20`–`0xFFFF`;
- all `PT_LOAD` segments have `p_vaddr == p_paddr` and do not overlap;
- the flat binary begins at the vector base and matches the ELF load image.

The old K1 table at `0x00010000` is not present in K2; `0x00010000` is now only
the ELF entry point and `.text` start.

## 5. Startup state evidence

Runtime diagnostic:

```text
K2 vectors: low @ 0x00000000
K2 sctlr: 0x00050078
K2 cpsr: 0x600001d3
K2 frame bytes: 0x00000048
K2 frame align: 0x00000008
K2 stack svc: 0x00010c98 - 0x00014c98
K2 stack und: 0x00014c98 - 0x00015c98
K2 stack abt: 0x00015c98 - 0x00016c98
K2 stack irq: 0x00016c98 - 0x00017498
K2 stack fiq: 0x00017498 - 0x00017898
```

`SCTLR=0x00050078` has bit 13 clear, so low vectors are active. `CPSR=0x600001d3`
decodes as SVC mode (`0x13`) with `I=1`, `F=1`, `T=0`, little-endian. The frame
is 72 bytes (`0x48`) and 8-byte aligned. Stack boundaries match the linker
symbols and are 8-byte aligned.

## 6. Undefined Instruction evidence

The `undef` profile executes `udf #0` (`0xE7F000F0`) at `0x0001023C` after
loading sentinels. Captured UART output:

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

Assertions that passed:

- vector offset is `0x04`;
- handler mode and handler CPSR are UND (`0x1B`);
- IRQ/FIQ are masked in the handler;
- SPSR is SVC (`0x13`), so the interrupted context was the kernel;
- `LR_und - fault_pc == 4` and `fault_pc` is inside the kernel image;
- `r0`, `r1`, `r12` match the sentinels written by the fault generator.

Evidence: [`undef-uart.log`](evidence/undef-uart.log),
[`undef-runtime.txt`](evidence/undef-runtime.txt),
[`disassembly-tests-undef.txt`](evidence/disassembly-tests-undef.txt).

## 7. Data Abort evidence

The `data-abort` profile writes `SCTLR.A=1` and `SCTLR.U=1`, verifies the
read-back (`0x00050078` → `0x0045007a`), then executes a real unaligned word
`LDR` at `0x00010264` from `probe + 1`. Captured UART output:

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

Assertions that passed:

- `SCTLR.A` and `SCTLR.U` read back as 1;
- the probe is 16-byte aligned and `probe + 1` is not word aligned;
- vector offset is `0x10`;
- handler mode and handler CPSR are ABT (`0x17`);
- SPSR is SVC;
- `DFSR = 0x00000001` (Alignment Fault) and `DFAR = probe + 1`;
- `LR_abt - fault_pc == 8` and `fault_pc` is the unaligned `LDR`;
- `r0` is the unaligned address and `r1`, `r2`, `r12` match the sentinels.

Evidence: [`data-abort-uart.log`](evidence/data-abort-uart.log),
[`data-abort-runtime.txt`](evidence/data-abort-runtime.txt),
[`disassembly-tests-data-abort.txt`](evidence/disassembly-tests-data-abort.txt).

## 8. Exception frame ABI

`include/minitos/exception.h` declares an 18-word frame and enforces:

```text
sizeof(struct exception_frame) == 72
_Alignof(struct exception_frame) == 8
sizeof(struct exception_frame) % 8 == 0
offsetof(r0)   == 0     offsetof(r12)    == 48
offsetof(lr)   == 52    offsetof(spsr)   == 56
offsetof(vector)== 60   offsetof(dfsr)   == 64
offsetof(dfar) == 68
```

`exception.c` exports the compiled size/alignment in `.rodata.k2abi`, and
`tools/elfcheck.py` reads those values from the ELF. The runtime also prints
`K2 frame bytes: 0x00000048` and `K2 frame align: 0x00000008`.

The full contract is in [`EXCEPTION_ABI.md`](EXCEPTION_ABI.md).

## 9. Fail-stop evidence

The runtime harness requires the terminal marker to be the last non-empty
serial line and requires exactly one kernel banner, so a reset loop or a handler
that returns and re-runs startup fails the test. Both checks passed for all
three profiles. The handler disassembly ends in a self-loop after the C call as
a second line of defence; `cpu_halt()` is a `nop` loop.

K2 does not implement recovery. The SVC, Prefetch Abort, IRQ and FIQ entries
use the same frame and then call `exception_unexpected()`, which prints
`EXCEPTION: UNEXPECTED <name>` and halts.

## 10. Profile separation

| Profile | Terminal marker | Purpose |
|---|---|---|
| `normal` | `K2 IDLE` | proves startup, diagnostics and stacks without a fault |
| `undef` | `K2 EXCEPTION CAPTURED` | proves Undefined Instruction entry and UND frame |
| `data-abort` | `K2 EXCEPTION CAPTURED` | proves Data Abort entry, ABT frame and DFSR/DFAR |

Each profile has its own ELF, binary, disassembly, linker map, hashes and
`build/run/<profile>/serial.log`. No profile is reused as evidence for another.

## 11. Image size and memory

Normal profile:

| Section | Size | Address |
|---|---|---|
| `.vectors` | 32 B | `0x00000000` |
| `.text` | 2,468 B | `0x00010000` |
| `.rodata` | 737 B | `0x000109A4` |
| `.bss` | 16 B | `0x00010C88` |
| `.stack` | 27,648 B | `0x00010C98` |
| Image end | — | `0x00017898` |

The image span including all stacks is **30,872 bytes**; the linker reports
`RAM: 30872 B / 64 KB (47.11%)`. The loadable flat binary is **68,741 bytes**
because `objcopy` materialises the gap between the vector segment at 0 and the
kernel at `0x10000`.

The `undef` and `data-abort` images end at `0x00017950` and `0x00017A60`
respectively; both remain inside the 64 KiB budget. Maximum static stack usage
reported by GCC `-fstack-usage` is 24 bytes (`console_write_hex32`), which is
not a runtime high-water mark.

Evidence: [`sizes.txt`](evidence/sizes.txt),
[`memory-usage.txt`](evidence/memory-usage.txt),
[`linker-map.txt`](evidence/linker-map.txt).

## 12. Reproducibility detail

Two independent clean builds of every profile produced:

```text
normal/minitos-k2.elf:     176d1acc5b21432d9cc8f227f1572576c63b9e1038a4f0575a7ee35d863ea63c  MATCH
normal/minitos-k2.bin:     4ab2ca63f5c5a8e923d293209da93ae39a1d53b7b4df5add27ba248676bcd2db  MATCH
undef/minitos-k2.elf:      23e8aafa191e731f17bf227d7af1fcd9ad77940e9eb2602ca12d75e898dc2273  MATCH
undef/minitos-k2.bin:      ad23fd42f4cbd5bffa1fdf7eadfe3362f302913251eebec35232c62d89122e2b  MATCH
data-abort/minitos-k2.elf: 306bf5bc6509cbdcc856bbe353e115cc93d1330f0e67135d381e6c9e35b9330a  MATCH
data-abort/minitos-k2.bin: 792e6e91e7287e220b83200849ed1c09d09ce6350a27c4aae5a13614e1a47ba7  MATCH
```

Evidence: [`repro-hashes.txt`](evidence/repro-hashes.txt),
[`sha256sums.txt`](evidence/sha256sums.txt).

This is a same-host, same-toolchain result. Cross-host byte identity is not
claimed.

## 13. Evidence inventory

| File | Contents |
|---|---|
| `acceptance-run.txt` | full acceptance console log |
| `normal-uart.log`, `undef-uart.log`, `data-abort-uart.log` | raw UART captures |
| `normal-runtime.txt`, `undef-runtime.txt`, `data-abort-runtime.txt` | runtime commands, checks and serial output |
| `elf-check.log` | all per-profile structural checks |
| `qemu-platform.log` | machine/CPU/memory-map checks |
| `qemu-mtree.txt` | live QMP memory map |
| `disassembly-vectors.txt` | low table at address 0 |
| `disassembly-startup.txt` | `_start`/`reset_handler` |
| `disassembly-handlers.txt` | entry stubs and C handlers |
| `disassembly-tests-undef.txt`, `disassembly-tests-data-abort.txt` | real fault instructions |
| `disassembly-full.txt` | normal-profile full disassembly |
| `linker-map.txt`, `symbols.txt`, `memory-usage.txt` | link layout and symbols |
| `sha256sums.txt`, `repro-hashes.txt` | artifact hashes and reproducibility |
| `toolchain.txt`, `sizes.txt` | environment and size reports |
| `readelf-*.txt` | ELF header, segments, sections, symbols, attributes |
| `k1/` | archived K1 baseline evidence |

## 14. Not run / not claimed

| Item | Status |
|---|---|
| Samsung Galaxy Gio GT-S5660 | **NOT RUN** |
| Any physical ARMv6 board | **NOT RUN** |
| Low vectors on real silicon / address 0 ownership | **NOT RUN** |
| Real UART baud accuracy | **NOT RUN** |
| IRQ/FIQ dispatch and return | **NOT TESTED** (stubs only) |
| Prefetch Abort handling | **NOT TESTED** (unexpected-path stub only) |
| SVC syscall behaviour | **NOT TESTED** (fail-stop stub only) |
| Exception recovery/resume | **NOT IMPLEMENTED** |
| MMU, caches, scheduler, allocator, framebuffer, apps | **NOT IMPLEMENTED** |
| Stack high-water measurement | **NOT TESTED** |
| Cross-host reproducibility | **NOT RUN** |
| QEMU versions other than 11.1.0 | **NOT RUN** |
| Toolchains other than GCC 15.2.1-1.1 | **NOT RUN** |
| Long-duration soak | **NOT RUN** |

See `ASSUMPTIONS_AND_LIMITATIONS.md` for the full list.

## 15. How to reproduce

```sh
# Toolchain: install arm-none-eabi-gcc and either put it on PATH or set
# MINITOS_ARM_BIN to its bin directory. On Windows:
#   powershell -ExecutionPolicy Bypass -File scripts/fetch-toolchain.ps1
#   $env:MINITOS_ARM_BIN = "$env:LOCALAPPDATA\Tools\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin"

python tools/build.py build
python tools/build.py verify --no-build
python tools/verify_platform.py
python tools/run_qemu.py
python tools/build.py repro
python tools/acceptance.py --evidence
```

`run_qemu.py` requires QEMU to be on `PATH` or `QEMU_SYSTEM_ARM` to point at
`qemu-system-arm`. A single profile can be run with
`python tools/run_qemu.py --profile normal|undef|data-abort`.

## 16. Claims discipline

A `PASS` in this document means the named command completed successfully on the
recorded host and produced the stated evidence. Static checks, emulator checks
and real-hardware behaviour are kept separate. In particular:

- the presence of an exception string in `.rodata` is **not** accepted as
  runtime evidence;
- the runtime checks require the real vector, mode, LR/fault-PC relationship,
  DFSR/DFAR and sentinels;
- the QEMU run is **not** treated as a Galaxy Gio port;
- K1 evidence is archived and is **not** reused to claim K2 behaviour.
