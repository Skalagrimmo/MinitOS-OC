# K1 Acceptance

**Status: PASS** for the checks listed below, on the recorded host and
toolchain. This document does not claim any test that was not executed.

## 1. Environment

| Item | Value |
|---|---|
| Date of run | 2026-11-02T10:43:47+02:00 |
| Host | Windows 10 Pro, build 19045 |
| Python | 3.15.2 |
| Compiler | xPack GNU Arm Embedded GCC 15.2.1 20251203 |
| Target triple | `arm-none-eabi` |
| Linker | GNU ld 2.45.1.20251203 |
| QEMU | 11.1.0 (`v11.1.0-12130-ge470268ff4`) |
| Machine / CPU | `integratorcp` / `arm1136` |
| RAM | `-m 128M` |
| Kernel ELF SHA-256 | `5f516ed5fc18cc460f1308fb0256d9b7aa40e78d153c3c2b260788da8d4d5bd1` |
| Flat BIN SHA-256 | `07c98c313a9ced3b0c4e291c9b1185597e60e27dd271016ea7f2b387d17ceb30` |

## 2. Acceptance command

The complete sequence was run with:

```sh
python tools/acceptance.py --evidence
```

It executes, in order:

1. `python tools/build.py build`
2. `python tools/build.py verify --no-build`
3. `python tools/verify_platform.py`
4. `python tools/run_qemu.py`
5. `python tools/build.py repro`

The full captured log is
[`docs/evidence/acceptance-run.txt`](evidence/acceptance-run.txt).

## 3. Result matrix

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | ELF32 ARM image builds | **PASS** | ELF 18,200 bytes, `EM_ARM`, `ELFCLASS32`, LSB |
| 2 | Entry point is checked | **PASS** | `e_entry = _start = .vectors = 0x00010000`; vector 0 branches to `reset_handler` |
| 3 | QEMU configuration is ARM1136 | **PASS** | `-M integratorcp -cpu arm1136`; runtime MIDR `0x4117b363` (part `0xB36`) |
| 4 | Kernel actually executes | **PASS** | UART output captured; QEMU guest-error log empty |
| 5 | UART prints `MINITOS KERNEL STARTED` | **PASS** | first serial line is exactly the banner |
| 6 | Rebuild is reproducible | **PASS** | two clean builds; ELF and BIN hashes match |
| 7 | Assumptions and limits documented | **PASS** | `ASSUMPTIONS_AND_LIMITATIONS.md` |

Structural checker: **63 checks passed**.
Platform checker: **7 checks passed**.
Runtime checker: **8 checks passed**.
Acceptance sequence: **5/5 steps passed**.

## 4. Entry-point verification detail

From the ELF checker and disassembly:

```text
e_entry                  = 0x00010000
_start                   = 0x00010000  (FUNC GLOBAL, size 32)
.vectors                 = 0x00010000, size 32, AX
first instruction        = 0xEA000006  b 0x00010020 <reset_handler>
reset_handler            = 0x00010020
kernel_main              = 0x0001036C
```

The checker also verifies:

- vectors 1–7 are distinct self-loop traps;
- the first `PT_LOAD` starts at `0x00010000` and is executable;
- all `PT_LOAD` segments have `p_vaddr == p_paddr`;
- the entry point lies inside a loaded segment;
- the flat binary matches the allocated ELF image byte-for-byte;
- no undefined symbols or libc/libgcc helpers are present.

## 5. QEMU platform verification detail

`tools/verify_platform.py` asks the installed QEMU:

- `-M help` contains `integratorcp`;
- `-M integratorcp -cpu help` contains `arm1136`;
- QMP `info mtree` reports:
  - `0x00000000–0x07FFFFFF` `integrator.ram`;
  - `0x16000000–0x16000FFF` `pl011` (UART0);
  - `0x17000000–0x17000FFF` `pl011` (UART1);
  - `0x10000000–0x107FFFFF` `integratorcm`.

The live map is captured in
[`docs/evidence/qemu-mtree.txt`](evidence/qemu-mtree.txt).

## 6. Runtime verification detail

Command (paths abbreviated):

```text
qemu-system-arm -M integratorcp -cpu arm1136 -m 128M \
  -kernel build/minitos-k1.elf \
  -display none -monitor none \
  -serial file:build/serial.log \
  -no-reboot -d guest_errors -D build/qemu-guest-errors.log
```

Observed serial output (raw file uses CRLF):

```text
MINITOS KERNEL STARTED
board: integratorcp
uart: pl011 @ 0x16000000
cpu midr: 0x4117b363
idle
```

Runtime checks that passed:

- the guest produced serial output;
- the first line is exactly `MINITOS KERNEL STARTED`;
- the board line is `board: integratorcp`;
- the UART line is `uart: pl011 @ 0x16000000`;
- MIDR is reported;
- MIDR implementer is `0x41` (ARM);
- MIDR part is `0xB36` (ARM1136);
- QEMU's `-d guest_errors` log is empty.

Raw capture:
[`docs/evidence/qemu-serial.txt`](evidence/qemu-serial.txt).
Detailed checks:
[`docs/evidence/runtime-evidence.txt`](evidence/runtime-evidence.txt).

## 7. Image size and memory

From `sizes-all.txt` for the reference build:

| Section | Size | Address |
|---|---|---|
| `.vectors` | 32 B | `0x00010000` |
| `.text` | 968 B | `0x00010020` |
| `.rodata` | 133 B | `0x000103E8` |
| `.bss` | 16 B | `0x00010470` |
| `.stack` | 16,384 B | `0x00010480` |
| Image end | — | `0x00014480` |

The image span including the stack is **17,536 bytes**, inside the enforced
64 KiB budget. The loadable flat binary is **1,133 bytes**. Maximum static
stack usage reported by GCC `-fstack-usage` is **24 bytes**
(`console_write_hex32`).

## 8. Reproducibility detail

Two independent clean builds produced:

```text
minitos-k1.elf: 5f516ed5fc18cc460f1308fb0256d9b7aa40e78d153c3c2b260788da8d4d5bd1  MATCH
minitos-k1.bin: 07c98c313a9ced3b0c4e291c9b1185597e60e27dd271016ea7f2b387d17ceb30  MATCH
```

Evidence:
[`docs/evidence/repro.txt`](evidence/repro.txt).

This is a same-host, same-toolchain result. Cross-host byte identity is not
claimed.

## 9. Evidence inventory

| File | Contents |
|---|---|
| `evidence/acceptance-run.txt` | full acceptance console log |
| `evidence/qemu-serial.txt` | raw UART capture |
| `evidence/runtime-evidence.txt` | runtime command, checks, serial output |
| `evidence/qemu-mtree.txt` | live QMP memory map |
| `evidence/qemu-platform.txt` | machine/CPU/map check log |
| `evidence/sha256sums.txt` | ELF and BIN hashes |
| `evidence/repro.txt` | double-build comparison |
| `evidence/toolchain.txt` | compiler, linker, Python, host versions |
| `evidence/sizes.txt` | size report |
| `evidence/readelf-header.txt` | ELF header |
| `evidence/readelf-program-headers.txt` | program headers |
| `evidence/readelf-sections.txt` | section headers |
| `evidence/readelf-symbols.txt` | symbol table |
| `evidence/readelf-attributes.txt` | ARM ABI attributes |

## 10. Not run / not claimed

| Item | Status |
|---|---|
| Samsung Galaxy Gio GT-S5660 | **NOT RUN** |
| Any physical ARMv6 board | **NOT RUN** |
| Real UART baud accuracy | **NOT RUN** |
| Interrupts, exceptions, MMU, caches | **NOT IMPLEMENTED / NOT TESTED** |
| Scheduler, allocator, framebuffer, apps | **NOT IMPLEMENTED** |
| Cross-host reproducibility | **NOT RUN** |
| QEMU versions other than 11.1.0 | **NOT RUN** |
| Toolchains other than GCC 15.2.1-1.1 | **NOT RUN** |
| Long-duration soak | **NOT RUN** |

See `ASSUMPTIONS_AND_LIMITATIONS.md` for the full list.

## 11. How to reproduce

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
`qemu-system-arm`.

## 12. Claims discipline

A `PASS` in this document means the named command completed successfully on
the recorded host and produced the stated evidence. Static checks, emulator
checks and real-hardware behaviour are kept separate. In particular, the K0
compile/link `PASS` is not treated as execution evidence, and the QEMU run is
not treated as a Galaxy Gio port.
