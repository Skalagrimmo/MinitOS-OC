# Assumptions and Limitations

This file is part of the K1 deliverable. It lists what the project relies on,
what was actually verified, and what remains unknown. A K1 `PASS` is limited to
the environment and checks recorded in `K1_ACCEPTANCE.md`.

## 1. Verified facts

These were checked by running the tools or by inspecting the produced image,
not inferred from K0:

| Fact | Evidence |
|---|---|
| The image is ELF32, little-endian, `EM_ARM`, EABI5, soft-float | `tools/elfcheck.py`, `readelf-header.txt`, `readelf-attributes.txt` |
| Entry point is `0x00010000`, equal to `_start` and `.vectors` | `elfcheck.py`, `readelf-symbols.txt`, disassembly |
| Vector 0 branches to `reset_handler` | `elfcheck.py` decodes the ARM branch |
| QEMU has `integratorcp` and accepts `-cpu arm1136` | `verify_platform.py`, `qemu-platform.txt` |
| QEMU RAM is 128 MiB at `0x00000000` | live QMP `info mtree` |
| UART0 is a PL011 at `0x16000000` | live QMP `info mtree` |
| The kernel executes and writes the banner | `run_qemu.py`, `qemu-serial.txt` |
| The executed CPU reports ARM1136 MIDR (`0x4117b363`) | serial output, runtime evidence |
| QEMU logged no guest errors during the run | `-d guest_errors` log is empty |
| Two clean builds are byte-identical on this host/toolchain | `build.py repro`, `repro.txt` |
| No undefined libc/libgcc symbols are present | link `--no-undefined`, ELF symbol check |

## 2. Assumptions that are not verified by QEMU

| Assumption | Why it is used | Status | If wrong |
|---|---|---|---|
| Integrator/CP UART clock is 7,372,800 Hz | Needed to compute a real PL011 divisor | **Unverified board assumption**; QEMU does not enforce baud for output | Real hardware baud would be wrong; output may be garbled until measured |
| `115200 8N1` is the intended console setting | Common bring-up default | **Unverified on hardware**; QEMU accepts it | Host terminal configuration would need to change |
| A 16 KiB SVC stack is sufficient | Simple, predictable boot stack | Static stack usage measured at 24 bytes max; **no runtime high-water mark** | A future deep call chain could overflow; K1 has no guard page |
| The loader leaves MMU and caches off | QEMU reset state; K1 does not configure them | **QEMU verified by execution**; real bootloader unknown | K1 would need explicit CP15 setup before using memory |
| `r0`–`r2` are not a boot protocol | QEMU ELF path does not provide Linux ATAGS | **Verified by QEMU source inspection and runtime**; a future bootloader may differ | A future board entry must define its own register contract |
| Physical addresses are identity-mapped | MMU is off | **True for QEMU and the current linker layout** | A board with a different physical map needs a new linker script |
| The ARM1136 model matches the MSM7227 core | Same ARMv6 family | **Not verified**; QEMU model revision is `0x4117b363` | Instruction/errata differences could appear on real silicon |
| QEMU's PL011 model is representative of the real PL011 | Used for driver development | **Model-level verified only** | Real FIFO/clock/line behaviour may differ |
| The UART is present at the board address | Board descriptor | **Verified on QEMU** | A wrong address hangs in the TX poll loop |

## 3. Explicit non-assumptions

K1 does **not** assume:

- that `0x00010000` is a Galaxy Gio load address;
- that the Gio bootloader jumps to an ELF entry point;
- that the Gio has RAM at address 0, or 128 MiB of it;
- that UART0 on the Gio is a PL011 at `0x16000000`;
- that the MSM7227 boot ROM, SBL or Android boot chain is understood;
- that QEMU's peripheral set matches the Gio;
- that K0's 16 MiB linker region is a target-board fact;
- that Clang/LLVM/readelf/python3 names from K0 are available.

The Gio port is future work with its own evidence requirements.

## 4. Limitations of the current implementation

### Runtime and CPU

- Single core only; no SMP, no CPU hotplug, no secondary core boot.
- No exception recovery. Fault vectors are self-loops.
- No interrupts. IRQ and FIQ are masked for the entire run.
- No timer, no clock source, no watchdog.
- No MMU setup, no cache maintenance, no write buffer control.
- No power management or idle instruction; the idle path is a `nop` loop.

### Memory

- No physical page allocator, no virtual memory, no heap.
- Static `.bss` only; the console state and PL011 state are fixed objects.
- Stack overflow is not detected.
- The 64 KiB image budget is a link-time check, not a runtime memory map.
- `__image_end__` is the first free address, but no allocator consumes it yet.

### I/O

- UART TX only; RX is enabled in `CR` but never read.
- No UART interrupts, DMA, flow control or error handling.
- The TX poll loop has no timeout. A missing/disabled UART hangs the kernel.
- No framebuffer, MMC, Ethernet, USB, audio, keyboard or mouse driver.
- No device probing; the board descriptor is compile-time selected.

### Kernel structure

- No scheduler, no tasks, no threads, no user mode.
- No syscall interface; the SVC vector is a trap placeholder.
- No IPC, no filesystem, no application loader.
- No panic console; a fault after UART init does not print a diagnostic.
- No logging subsystem; the console is the only sink.

### Build and reproducibility

- Byte-identical output is verified on one Windows 10 host with the pinned
  xPack GCC 15.2.1-1.1. Cross-host, cross-version and cross-filesystem
  reproducibility are **not** claimed.
- The build depends on Python 3 and an `arm-none-eabi-gcc` toolchain.
- The Windows fetch script uses `tar.exe` and PowerShell; the POSIX QEMU
  launcher was not executed in the reference environment.
- Debug information is retained; it is not part of the loadable image.

### Platform

- No real-hardware test of any kind.
- No Galaxy Gio, MSM7227, bootloader, flashing or fastboot test.
- QEMU does not model electrical behaviour, instruction timing, cache
  behaviour, or the real UART clock.
- The QEMU result proves the emulated ARMv6/PL011/ELF path, not the phone.

## 5. Not-run tests

The following are explicitly **not** PASS:

| Test | Status |
|---|---|
| Boot on Samsung Galaxy Gio GT-S5660 | NOT RUN |
| Boot on any physical ARM1136/ARMv6 board | NOT RUN |
| UART baud accuracy on hardware | NOT RUN |
| Interrupt entry/return | NOT TESTED (not implemented) |
| MMU/cache enable and maintenance | NOT TESTED (not implemented) |
| Stack overflow / high-water measurement | NOT TESTED |
| Long-duration soak (hours/days) | NOT RUN |
| Cross-host reproducible build | NOT RUN |
| QEMU versions other than 11.1.0 | NOT RUN |
| Toolchains other than GCC 15.2.1-1.1 | NOT RUN |
| Fault injection / exception recovery | NOT TESTED |

## 6. Safety

This image is a QEMU reference artifact. It has no phone bootloader contract,
no partition layout, no flashing instructions and no recovery path. Do not
write it to a phone or any persistent device.
