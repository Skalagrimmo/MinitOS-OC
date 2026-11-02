# Engineering Decision Journal

Each entry records the decision, the alternatives considered, and the
consequence accepted by the stage that made it (K1 or K2). These are decisions,
not claims that the alternatives are invalid.

---

## ADR-001 — Build K1 in a separate tree and leave K0 untouched

**Context.** K0 is the input proof-of-concept, not the product.

**Decision.** Create `minitos-k1/` as an independent repository. Extract K0
only for reading and ELF inspection. Do not edit, reformat or import K0 source
files.

**Alternatives.** Patch K0 in place; copy K0 and refactor incrementally.

**Consequence.** K0 remains an auditable historical artifact. K1 can choose a
different structure without pretending it is a continuation by line count.

---

## ADR-002 — Use pinned GNU Arm Embedded GCC instead of K0's Clang

**Context.** K0 assumed `clang`, `llvm-objcopy`, `llvm-objdump`, GNU `readelf`,
`python3` and Make. None were present in the reference environment. K0 never
ran the image, so its toolchain was not runtime-proven.

**Decision.** Pin xPack GNU Arm Embedded GCC **15.2.1-1.1** for Windows x64,
verify the archive SHA-256, and use its `gcc`, `ld`, `objcopy`, `objdump`,
`readelf`, `nm` and `size`. Keep the build driver toolchain-agnostic enough to
use any `arm-none-eabi-gcc` on another host.

**Alternatives.** Download LLVM/Clang; use a vendor IDE toolchain; cross-compile
from WSL.

**Consequence.** The reference build is tied to a specific GCC/binutils
version. Cross-toolchain byte identity is not claimed. The toolchain download
is large (~320 MiB) but reproducible and self-contained.

---

## ADR-003 — Target ARM1136JF-S, ARM state, soft-float

**Context.** The eventual hardware is an MSM7227-1, an ARMv6 core. QEMU's
Integrator/CP supports an ARM1136 model.

**Decision.** Compile with `-mcpu=arm1136jf-s -marm -mfloat-abi=soft`; run QEMU
with `-cpu arm1136`.

**Alternatives.** Generic `-march=armv6`; Thumb-2 (not available on ARMv6);
hard-float (unnecessary and not enabled by K1).

**Consequence.** K1 may use ARMv6 instructions but no VFP. The MIDR read proves
the emulated part is an ARM1136. It does not prove a specific MSM7227 revision.

---

## ADR-004 — Link at `0x00010000` and use the ELF entry point

**Context.** QEMU's Integrator/CP sets `loader_start = 0`. An ELF image is
loaded at `p_paddr` and started at `e_entry`; a raw Linux-style image would take
a different path and get a bootloader stub.

**Decision.** Produce a proper ELF, link the first segment at `0x00010000`, and
load it with `-kernel`. `e_entry` is `_start`, the first word of the vector
table. The flat binary is produced for inspection/future use, not used by the
QEMU runtime test.

**Alternatives.** Link at 0; load a raw binary at QEMU's Linux load address;
write a custom QEMU loader.

**Consequence.** The boot contract is explicit and checkable: first segment
`p_paddr == 0x10000`, entry equals image base, vector 0 branches to
`reset_handler`. `0x00010000` remains a QEMU reference address, not a Gio
address.

---

## ADR-005 — Put an 8-word vector table at the image entry

**Context.** K0 had no vector table. K1 needs a defined reset entry and a place
for future exception handling.

**Decision.** Reserve the first 32 bytes for the ARM exception vectors. Vector
0 branches to `reset_handler`; vectors 1–7 are distinct self-loop traps.

**Alternatives.** Start directly with `reset_handler`; place vectors at
address 0; use high vectors at `0xFFFF0000`.

**Consequence.** The entry point is a real reset vector. Faults hang at a
recognisable vector address instead of running into arbitrary memory. Adding
real handlers later does not move the entry point. Vectors are not yet copied
to address 0, because K1 runs from an ELF at `0x10000` and has no Gio boot
contract.

---

## ADR-006 — One 16 KiB SVC boot stack, no per-mode stacks yet

**Context.** K1 runs only in SVC mode with interrupts masked. It has no
exception handlers that need a stack.

**Decision.** Define a 16 KiB `.stack (NOLOAD)` section immediately after BSS,
8-byte aligned at the top. Do not allocate IRQ/FIQ/abort stacks yet.

**Alternatives.** One stack per mode now; a 4 KiB stack; a stack in low memory.

**Consequence.** Memory use is predictable and checked by the ELF verifier.
A future exception implementation must add mode stacks and a stack-switch
discipline before enabling interrupts.

---

## ADR-007 — Polled PL011 TX with precomputed divisors

**Context.** Early bring-up needs reliable output without interrupt
infrastructure. ARM1136 has no hardware integer divide, so a runtime division
would pull in a libgcc helper.

**Decision.** Implement a minimal PL011 driver: 8N1, FIFO, no interrupts,
UARTEN/TXE/RXE enabled, poll `FR.TXFF` before writing `DR`. Precompute
`IBRD=4`, `FBRD=0` in the board header for the assumed 7.3728 MHz UART clock.

**Alternatives.** Use QEMU semihosting; use the debug LEDs; link libgcc and
compute divisors at runtime; use interrupts.

**Consequence.** Output is simple, synchronous and dependency-free. A missing
UART hangs visibly rather than dropping output. Baud timing is not proven by
QEMU and remains a hardware assumption.

---

## ADR-008 — Describe the board with an immutable descriptor

**Context.** K0 mixed a load address in the linker script with no peripheral
facts. K1 needs UART and RAM facts without hard-coding them throughout the
kernel.

**Decision.** `struct board` holds name, RAM range, UART base/clock/baud and
precomputed divisors. `board_current()` returns a `static const` instance.
`main.c` passes it to the console.

**Alternatives.** `#define`s in every file; a runtime device tree; probing
peripherals.

**Consequence.** A new board is a new descriptor plus a boot path, not a fork
of the console or driver. Every current value has recorded provenance from
QEMU, not from K0.

---

## ADR-009 — No libc, no libgcc, no compiler runtime

**Context.** Freestanding kernel; hidden runtime dependencies are a common
source of link-time surprises and unpredictable memory use.

**Decision.** Link with `-nostdlib -nostartfiles -nodefaultlibs
-Wl,--no-undefined`. The ELF checker separately rejects undefined symbols and
`__aeabi_*`/libc helpers.

**Alternatives.** Link libgcc for division and memory helpers; provide a local
mini-libc.

**Consequence.** The link fails if a helper is introduced accidentally. Code
must use shifts, loops and explicit routines. K1 is 1,133 loadable bytes with
no external runtime.

---

## ADR-010 — Python build driver, thin Makefile wrapper

**Context.** GNU Make was not available in the reference environment. The build
must still be transparent and reproducible.

**Decision.** Put the authoritative build logic in `tools/build.py` with
explicit source lists, flags and commands. Provide a thin `Makefile` for hosts
that have Make.

**Alternatives.** Require Make; use CMake; use a shell script only.

**Consequence.** The build works on the reference Windows host and on Unix-like
hosts with Python 3. The Makefile is convenience, not a second implementation.

---

## ADR-011 — Enforce reproducibility with a double-build hash check

**Context.** A build that happens to work once is not enough for a kernel
bring-up baseline.

**Decision.** Remove timestamps/build IDs, discard `.comment`, fix source and
link order, use a fixed random seed and relative source paths. `build.py repro`
builds into two separate directories and compares ELF and BIN SHA-256 values.

**Alternatives.** Trust the compiler; compare only section sizes; archive one
binary.

**Consequence.** Same-host, same-toolchain builds are byte-identical and this
is tested. Cross-host/cross-version identity is explicitly not claimed.

---

## ADR-012 — Runtime test from a serial file plus guest-error log

**Context.** The kernel never exits. A test must prove more than "QEMU started".

**Decision.** Run QEMU with `-serial file:...`, `-d guest_errors -D ...`, wait
for the banner, then terminate QEMU. Require the exact first line, board/UART
diagnostics, MIDR implementer/part and an empty guest-error log.

**Alternatives.** Use semihosting exit; add a QEMU-specific shutdown register;
use `-serial stdio` and parse a pipe; run for a fixed time without assertions.

**Consequence.** The test observes real UART output through the emulated PL011
and catches misprogrammed registers that produce guest errors. It terminates
deterministically without adding QEMU-specific code to the kernel.

---

## ADR-013 — Enforce a 64 KiB image budget

**Context.** Predictable memory use is a K1 principle. An unbounded image can
silently collide with future low-memory reservations.

**Decision.** The linker asserts that `__image_end__ - __image_start__ <= 64K`,
including the 16 KiB stack. The current image spans 17,536 bytes.

**Alternatives.** No budget; a 1 MiB budget; a per-section budget only.

**Consequence.** Accidental growth fails the build early. The budget is easy to
raise deliberately when a later stage justifies it.

---

## ADR-014 — Translate `\n` to CRLF in the console facade

**Context.** Raw serial captures and terminals differ in newline handling.

**Decision.** `console_putc('\n')` emits `\r\n`; callers use `\n` only.

**Alternatives.** Emit LF only; require callers to send CRLF.

**Consequence.** Captured output is readable in both contexts. The exact
banner line is still a single logical line after CRLF normalisation.

---

## ADR-015 — Do not assume anything about the Galaxy Gio boot chain

**Context.** The eventual target is a Samsung Galaxy Gio GT-S5660 (MSM7227-1),
but its bootloader, load address and peripheral map are not established here.

**Decision.** Keep QEMU and Gio facts separate. The linker script and board
header say explicitly that their addresses are QEMU Integrator/CP facts.
Do not add a Gio board descriptor until its boot contract is measured.

**Alternatives.** Guess a Gio load address from common Android/MSM7227
practice; reuse QEMU addresses and label them "Gio".

**Consequence.** K1 cannot be flashed to a phone, by design. A future port has
a clean boundary: new board descriptor, new linker layout, new boot entry,
same kernel core.

---

## ADR-016 — Keep debug information, discard non-deterministic metadata

**Context.** QEMU/GDB debugging is useful, but build metadata can break
reproducibility.

**Decision.** Compile with `-g` (DWARF), discard `.comment`, `.note*`,
`.eh_frame*` and `.ARM.exidx*`, use `--build-id=none`, and map absolute paths to
`.` with `-ffile-prefix-map`.

**Alternatives.** Strip all debug info; embed build timestamps; keep build IDs.

**Consequence.** The ELF is larger on disk (18,200 bytes) but the loadable
image is small (1,133 bytes). Debug symbols remain available, and the two
builds compare byte-identically.

---

## ADR-017 — Preserve K1 as a tag and evolve the same tree into K2

**Context.** K2 changes the boot path, vector location and stack layout. The K1
result must remain reproducible and auditable.

**Decision.** Tag the verified K1 commit as `k1-baseline` and push the tag
before modifying the tree. Build K2 in place, keep the K1 acceptance report,
and archive the original K1 evidence under `docs/evidence/k1/`.

**Alternatives.** Fork a separate K2 repository; rewrite history; keep only the
latest state.

**Consequence.** K1 can be checked out and rebuilt exactly as accepted. K2
documentation is separate from K1 documentation and does not overwrite K1
claims. The archive is a copied snapshot, not a second source of truth.

---

## ADR-018 — Use the real low-vector table at address 0

**Context.** K1 placed 32 bytes of vector-shaped data at `0x00010000`, but
`SCTLR.V` was left at its reset value and the CPU never used that table. K2
must have an architecturally active table.

**Decision.** Clear `SCTLR.V`, verify the read-back, and link `.vectors` as its
own executable `PT_LOAD` at virtual and physical address 0. Keep the kernel
image and ELF entry point at `0x00010000`.

**Alternatives.** High vectors at `0xFFFF0000`; copy the table at runtime;
keep the K1 table and claim it is active.

**Consequence.** The table is real and observable in the ELF, linker map and
disassembly. The reset slot at 0 and `_start` at `0x10000` enter the same
handler, so QEMU's `e_entry` path and the architectural reset vector agree.
Address 0 must be loadable on the target; this is verified on QEMU and listed
as a hardware assumption.

---

## ADR-019 — Install every banked stack before the first C call

**Context.** An exception can occur at any instruction. If the entered mode has
no valid stack, the handler faults recursively with no diagnostic.

**Decision.** Allocate SVC 16 KiB, UND 4 KiB, ABT 4 KiB, IRQ 2 KiB and FIQ
1 KiB stacks, 8-byte aligned and contiguous after `.bss`. `reset_handler`
switches through the modes and sets each banked SP before clearing BSS and
calling C.

**Alternatives.** Allocate only SVC/UND/ABT; share the SVC stack; allocate
stacks lazily.

**Consequence.** Every vector has a valid stack from the first instruction after
startup. The linker and ELF checker enforce sizes, ordering and alignment.
Stack overflow is still undetected, and the sizes are engineering choices, not
measured high-water marks.

---

## ADR-020 — Use a fixed 72-byte exception frame declared twice

**Context.** Assembly must build the frame and C must consume it. A silent
layout mismatch would produce plausible-looking but wrong diagnostics.

**Decision.** Define `struct exception_frame` as 18 words with named offsets,
`_Static_assert` its size/alignment/offsets in C, duplicate the offsets as
`.equ` constants in assembly, and export the compiled `sizeof`/`_Alignof` in
`.rodata.k2abi` for `tools/elfcheck.py`.

**Alternatives.** Pass registers individually; use a packed byte buffer; rely
on a comment as the ABI.

**Consequence.** A layout change fails the C build, the assembly constants must
be updated deliberately, and the ELF check catches a stale object. The frame is
a multiple of 8 bytes, preserving AAPCS stack alignment at the C call.

---

## ADR-021 — Run handlers in the entered mode and make them fail-stop

**Context.** K2 needs trustworthy diagnostics, not recovery. Switching to SVC
would require a nested stack and would hide which mode the CPU actually
entered.

**Decision.** Each entry stub saves the frame on the banked stack of the mode
the CPU entered and calls C in that mode. IRQ/FIQ are masked. Handlers print
the vector, handler CPSR, SPSR, LR, fault PC, DFSR/DFAR and sentinels, then
halt. SVC/prefetch/IRQ/FIQ use a separate unexpected-path handler that also
halts. The reserved vector is a stack-free self-loop.

**Alternatives.** Switch to SVC; return after printing; retry the instruction;
use a QEMU semihosting exit.

**Consequence.** The reported `mode` value is direct runtime proof of the
entered mode. The handler never returns into an unknown context, and the
harness can assert that the terminal marker is the last output and that no
reboot occurred. Recovery remains future work.

---

## ADR-022 — Generate faults with real instructions

**Context.** A kernel that only contains exception-related strings or calls a
handler directly does not prove that the CPU took an exception.

**Decision.** The `undef` profile executes ARM `udf #0` (`0xE7F000F0`). The
`data-abort` profile sets `SCTLR.A=1` and `SCTLR.U=1`, verifies the read-back,
then executes `add r0, #1; ldr r1, [r0]` from a 16-byte-aligned probe. Both
generators load sentinel values first. If the fault does not fire, they return
and the kernel prints `K2 TEST FAILED` and halts.

**Alternatives.** Call `exception_dispatch()` directly; use an undefined
address; rely on a compiler-generated trap.

**Consequence.** The runtime evidence includes the real vector, mode, SPSR/LR
relationship, fault PC and sentinels. `tools/elfcheck.py` also decodes the UDF
word and the `add`/`ldr` pair in the profile ELFs, so the test cannot be
replaced by text alone.

---

## ADR-023 — Build one image per fault profile

**Context.** The handlers are fail-stop, so a single image cannot continue from
Undefined Instruction to a Data Abort test.

**Decision.** Compile the same sources with `-DMINITOS_TEST_MODE=0/1/2` into
`build/normal`, `build/undef` and `build/data-abort`. Each profile gets its own
ELF, binary, disassembly, map, hashes and QEMU serial log.

**Alternatives.** Runtime menu over UART; separate source trees; one image with
a resettable fault path.

**Consequence.** Every profile is independently reproducible and has its own
evidence. Build time and artifact count increase, and the three images differ
slightly in size. A future interactive test harness can replace this without
changing the exception ABI.

---

## ADR-024 — Accept only runtime evidence for the exception path

**Context.** Static text in `.rodata` and a clean link do not prove that the CPU
vectors through the table.

**Decision.** The QEMU harness requires, per profile, the terminal marker, the
expected vector offset, the handler mode, the SPSR mode, the LR/fault-PC
relationship, the fault PC inside the kernel image, the sentinel registers and
(for Data Abort) DFSR/DFAR. It also requires an empty guest-error log, the
marker to be the last line and no reboot banner. The acceptance script is
fail-fast: a later PASS is never printed after an earlier failure.

**Alternatives.** Inspect the ELF only; run QEMU for a fixed time; grep for a
single string.

**Consequence.** The K2 PASS is tied to captured UART logs and a recorded
command. The checks are more brittle to intentional output changes, which is
accepted because output is part of the diagnostic contract.

---

## ADR-025 — Keep diagnostics on the polled PL011 only

**Context.** Semihosting or a QEMU-specific device would make the fault path
depend on the emulator rather than the kernel's own driver.

**Decision.** The handlers use the same `console`/PL011 path as normal output.
No semihosting, no debugcon, no QEMU shutdown register, no host callbacks.

**Alternatives.** ARM semihosting `SYS_WRITE0` and `SYS_EXIT`; QEMU debugcon;
`-serial stdio` parsing.

**Consequence.** The diagnostics exercise the real driver stack and remain
portable to a board with a PL011. A fault before UART initialisation cannot be
printed, but it still halts safely. The harness terminates QEMU from the host,
so the kernel needs no emulator-specific exit.
