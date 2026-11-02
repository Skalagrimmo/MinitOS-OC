# Assumptions and Limitations

This file is part of the K2 deliverable. It lists what the project relies on,
what was actually verified, and what remains unknown. A K2 `PASS` is limited to
the environment and checks recorded in `K2_ACCEPTANCE.md`.

K1 remains the baseline stage and is preserved by the `k1-baseline` tag. Its
original evidence and limitations are archived under `docs/evidence/k1/` and
`docs/K1_ACCEPTANCE.md`.

## 1. Verified facts

These were checked by running the tools or by inspecting the produced images,
not inferred from K0 or K1:

| Fact | Evidence |
|---|---|
| The image is ELF32, little-endian, `EM_ARM`, EABI5, soft-float | `tools/elfcheck.py`, `readelf-header.txt`, `readelf-attributes.txt` |
| The vector table is 32 bytes at address 0 in an executable `PT_LOAD` | `elfcheck.py`, `readelf-program-headers.txt`, `linker-map.txt` |
| Entry point is `0x00010000`, equal to `_start` and `reset_handler` | `elfcheck.py`, `readelf-symbols.txt`, `disassembly-startup.txt` |
| All eight vector slots branch to defined symbols | `elfcheck.py`, `disassembly-vectors.txt` |
| `SCTLR.V=0` was written and read back before C | `disassembly-startup.txt`; runtime `K2 sctlr: 0x00050078` |
| SVC/UND/ABT/IRQ/FIQ stacks exist, have fixed sizes and are 8-byte aligned | `elfcheck.py`, `symbols.txt`, runtime stack lines |
| A real `udf #0` enters vector `0x04` in UND mode | `undef-uart.log`, `undef-runtime.txt`, `disassembly-tests-undef.txt` |
| A real unaligned word `LDR` enters vector `0x10` in ABT mode | `data-abort-uart.log`, `data-abort-runtime.txt`, `disassembly-tests-data-abort.txt` |
| `SCTLR.A` and `SCTLR.U` read back as 1 before the abort test | data-abort UART log (`0x0045007a` after write) |
| The Data Abort is an alignment fault at `probe + 1` | `dfsr=0x00000001`, `dfar=0x00010e41`, probe `0x00010e40` |
| The exception frame is 72 bytes, 8-byte aligned, with the declared offsets | `_Static_assert`, compiled `.rodata.k2abi` values, `elfcheck.py` |
| Fault paths print `K2 EXCEPTION CAPTURED`, do not reboot and do not return | runtime logs, last-line/halt checks, disassembly |
| QEMU has `integratorcp` and accepts `-cpu arm1136` | `verify_platform.py`, `qemu-platform.log` |
| QEMU RAM is 128 MiB at `0x00000000` | live QMP `info mtree` |
| UART0 is a PL011 at `0x16000000` | live QMP `info mtree` |
| The executed CPU reports ARM1136 MIDR (`0x4117b363`) | serial output, runtime evidence |
| QEMU logged no guest errors during any profile run | `-d guest_errors` logs are empty |
| Two clean builds of all three profiles are byte-identical | `build.py repro`, `repro-hashes.txt` |
| No undefined libc/libgcc symbols are present | link `--no-undefined`, ELF symbol check |

## 2. Assumptions that are not verified by QEMU

| Assumption | Why it is used | Status | If wrong |
|---|---|---|---|
| Integrator/CP UART clock is 7,372,800 Hz | Needed to compute a real PL011 divisor | **Unverified board assumption**; QEMU does not enforce baud for output | Real hardware baud would be wrong; output may be garbled until measured |
| `115200 8N1` is the intended console setting | Common bring-up default | **Unverified on hardware**; QEMU accepts it | Host terminal configuration would need to change |
| 16 KiB SVC / 4 KiB UND / 4 KiB ABT / 2 KiB IRQ / 1 KiB FIQ are sufficient | Simple, predictable per-mode stacks | Static stack use measured at 24 bytes max; **no runtime high-water mark** | A future deep handler chain could overflow; K2 has no guard page |
| The loader leaves MMU and caches off | QEMU reset state; K2 does not configure them | **QEMU verified by execution**; real bootloader unknown | K2 would need explicit CP15 setup before using memory |
| The loader starts the CPU in a privileged, non-User mode | QEMU starts in SVC | **Verified by runtime**; a different loader may differ | `reset_handler` refuses User-mode entry and self-loops |
| `r0`–`r2` are not a boot protocol | QEMU ELF path does not provide Linux ATAGS | **Verified by QEMU source inspection and runtime**; a future bootloader may differ | A future board entry must define its own register contract |
| Physical addresses are identity-mapped | MMU is off | **True for QEMU and the current linker layout** | A board with a different physical map needs a new linker script |
| Low vectors at address 0 are writable/loadable on the target | ARM1136 low-vector base | **Verified on QEMU**; real board may map address 0 differently | The vector segment would need relocation or a high-vector design |
| The ARM1136 model matches the MSM7227 core | Same ARMv6 family | **Not verified**; QEMU model revision is `0x4117b363` | Instruction/errata differences could appear on real silicon |
| QEMU's DFAR/DFSR alignment model matches real ARM1136 | Used to test Data Abort decoding | **Model-level verified only** | Real abort status encoding or timing may differ |
| QEMU's PL011 model is representative of the real PL011 | Used for driver development | **Model-level verified only** | Real FIFO/clock/line behaviour may differ |
| The UART is present at the board address | Board descriptor | **Verified on QEMU** | A wrong address hangs in the TX poll loop |

## 3. Explicit non-assumptions

K2 does **not** assume:

- that the vector table belongs at the same physical address on a phone;
- that `0x00010000` is a Galaxy Gio load address;
- that the Gio bootloader jumps to an ELF entry point;
- that the Gio has RAM at address 0, or 128 MiB of it;
- that UART0 on the Gio is a PL011 at `0x16000000`;
- that the MSM7227 boot ROM, SBL or Android boot chain is understood;
- that QEMU's peripheral set matches the Gio;
- that QEMU's exception entry timing, DFSR encoding or cache behaviour matches
  real silicon;
- that K0's 16 MiB linker region is a target-board fact;
- that Clang/LLVM/readelf/python3 names from K0 are available.

The Gio port is future work with its own evidence requirements.

## 4. Limitations of the current implementation

### Exceptions and CPU

- Undefined Instruction and Data Abort are diagnosed and then halt.
- SVC, Prefetch Abort, IRQ and FIQ are detected but not implemented as
  services: they print an unexpected-path diagnostic and halt.
- No exception recovery, no instruction emulation, no PC advance, no task
  termination.
- No interrupt controller, timer tick or IRQ dispatch.
- No MMU setup, cache maintenance policy, write-buffer control or TEX/AP
  configuration.
- Single core only; no SMP, no CPU hotplug, no secondary core boot.
- IRQ and FIQ are masked for the entire run.
- No power management or idle instruction; the idle path is a `nop` loop.

### Memory

- No physical page allocator, no virtual memory, no heap.
- Static `.bss` only; the console state and PL011 state are fixed objects.
- Stack overflow is not detected and there are no guard pages.
- The 64 KiB image budget is a link-time check, not a runtime memory map.
- `__image_end__` is the first free address, but no allocator consumes it yet.
- The vector segment relies on address 0 being loadable and not claimed by
  firmware.

### I/O

- UART TX only; RX is enabled in `CR` but never read.
- No UART interrupts, DMA, flow control or error handling.
- The TX poll loop has no timeout. A missing/disabled UART hangs the kernel.
- Diagnostics are synchronous; a fault before `console_init()` cannot be
  printed (the fatal path still halts safely).
- No framebuffer, MMC, Ethernet, USB, audio, keyboard or mouse driver.
- No device probing; the board descriptor is compile-time selected.

### Kernel structure

- No scheduler, no tasks, no threads, no user mode.
- No syscall interface; the SVC vector is a fail-stop stub.
- No IPC, no filesystem, no application loader.
- No panic console beyond the exception diagnostics; no logging subsystem.
- The three fault scenarios are compile-time profiles, not runtime-selectable.

### Build and reproducibility

- Byte-identical output is verified on one Windows 10 host with the pinned
  xPack GCC 15.2.1-1.1. Cross-host, cross-version and cross-filesystem
  reproducibility are **not** claimed.
- The build depends on Python 3 and an `arm-none-eabi-gcc` toolchain.
- The Windows fetch script uses `tar.exe` and PowerShell; the POSIX QEMU
  launcher was not executed in the reference environment.
- Debug information is retained; it is not part of the loadable image.
- Default build/test artifacts are ~69 KiB flat binaries per profile because
  the vector segment at 0 and the image at `0x10000` are materialised with a
  gap by `objcopy`; the in-memory layout is what matters.

### Platform

- No real-hardware test of any kind.
- No Galaxy Gio, MSM7227, bootloader, flashing or fastboot test.
- QEMU does not model electrical behaviour, instruction timing, cache
  behaviour, real exception latency or the real UART clock.
- The QEMU result proves the emulated ARMv6 exception/PL011/ELF path, not the
  phone.

## 5. Not-run tests

The following are explicitly **not** PASS:

| Test | Status |
|---|---|
| Boot on Samsung Galaxy Gio GT-S5660 | NOT RUN |
| Boot on any physical ARM1136/ARMv6 board | NOT RUN |
| Low vectors on real silicon / firmware-reserved address 0 | NOT RUN |
| UART baud accuracy on hardware | NOT RUN |
| IRQ/FIQ entry and return | NOT TESTED (stubs only, no dispatch) |
| Prefetch Abort handling | NOT TESTED (unexpected-path stub only) |
| SVC syscall behaviour | NOT TESTED (fail-stop stub only) |
| Exception recovery / resume | NOT TESTED (not implemented) |
| MMU/cache enable and maintenance | NOT TESTED (not implemented) |
| Stack overflow / high-water measurement | NOT TESTED |
| Long-duration soak (hours/days) | NOT RUN |
| Cross-host reproducible build | NOT RUN |
| QEMU versions other than 11.1.0 | NOT RUN |
| Toolchains other than GCC 15.2.1-1.1 | NOT RUN |

## 6. Safety

This image is a QEMU reference artifact. It has no phone bootloader contract,
no partition layout, no flashing instructions and no recovery path. Do not
write it to a phone or any persistent device.
