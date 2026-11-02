# MinitOS K2 Architecture

## 1. Scope

K2 extends the verified K1 bring-up kernel with real ARMv6 exception handling.
It proves, on QEMU `integratorcp` with an ARM1136 CPU, that:

1. the active exception table is the low table at `0x00000000`, selected by
   clearing `SCTLR.V`, and the kernel image still starts at `0x00010000`;
2. every exception mode has a valid banked stack before the first C call;
3. a real `UDF` instruction enters Undefined Instruction mode through vector
   `0x04` and is diagnosed in C;
4. a real unaligned word `LDR` with `SCTLR.A=1` enters Abort mode through
   vector `0x10` and is diagnosed with DFSR/DFAR;
5. fault paths halt deterministically instead of returning into an unknown
   context.

K2 is still not a general-purpose kernel. It has no recovery, no interrupt
dispatch, no MMU setup and no scheduler. Each module exists because K2 needs it,
and each one has an explicit contract for the next stage.

## 2. Layer map

```text
                 +--------------------------------------+
                 |             kernel/main.c            |
                 |  composition root; profile dispatch  |
                 +------------------+-------------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
+---------v----------+                             +----------v---------+
|  kernel/k2_tests.c |                             | arch/armv6/        |
|  fault generation  |                             | exception.c        |
|  and SCTLR A/U     |                             | frame diagnostics  |
+---------+----------+                             +----------+---------+
          |                                                   |
          +-------------------------+-------------------------+
                                    |
                 +------------------v-------------------+
                 |           kernel/console.c           |
                 |  console facade, CRLF, hex output    |
                 +------------------+-------------------+
                                    |
                 +------------------v-------------------+
                 |           drivers/pl011.c            |
                 |  PL011 register model, polled TX     |
                 +------------------+-------------------+
                                    |
                 +------------------v-------------------+
                 |        board/board_integratorcp.c    |
                 |  immutable board facts and addresses |
                 +------------------+-------------------+
                                    |
                 +------------------v-------------------+
                 |            arch/armv6/*              |
                 |  vectors, reset, stacks, BSS, CP15,  |
                 |  exception entry stubs               |
                 +--------------------------------------+
```

Dependency direction is downward only. `main.c` does not know PL011 register
offsets; the PL011 driver does not know which board it is on; the board layer
does not know how to print. `arch/armv6` is the only layer allowed to contain
ARM assembly and CP15 instructions.

## 3. Boot flow

For the normal reference build:

| Step | Address | Action |
|---|---|---|
| 1 | — | QEMU loads ELF segments at `p_paddr` and sets PC to `e_entry` |
| 2 | `0x00010000` | `_start` / `reset_handler` begins in the loaded image |
| 3 | `0x00010000` | refuse User-mode entry; force ARM state, little-endian, SVC, IRQ/FIQ masked |
| 4 | `0x00010020` | read `SCTLR`, clear `V` (low vectors), `U` and `A`; write and verify by read-back |
| 5 | `0x00010050` | drain write buffer / flush prefetch pipeline (`c7,c5,4` and `c7,c10,5`) |
| 6 | `0x0001005C` | install SVC, UND, ABT, IRQ and FIQ banked SPs from linker symbols |
| 7 | `0x00010088` | zero `.bss` (`0x00010C88`–`0x00010C98`) |
| 8 | `0x000100A0` | store the verified boot SCTLR in `__k2_sctlr_boot` |
| 9 | `0x000100AC` | `bl kernel_main` (`0x000107FC`) with an 8-byte-aligned SP |
| 10 | C | `board_current()` → `console_init()` → PL011 init |
| 11 | C | banner, board, UART, MIDR, SCTLR, CPSR, frame ABI and stack diagnostics |
| 12 | C | dispatch the selected profile: idle, Undefined Instruction test or Data Abort test |

The reset vector at `0x00` and the ELF entry point at `0x00010000` both branch
to the same `reset_handler`. QEMU starts at `e_entry`, so the image entry does
not move; the low slot exists for architectural completeness and for a future
loader that starts at address 0.

QEMU's 32-bit ARM ELF path does **not** insert a Linux bootloader stub: it
loads the ELF at `p_paddr` and jumps to `e_entry`. Therefore `r0`–`r2` are not
a usable boot protocol and K2 ignores them. This is verified in
`docs/PLATFORM_INTEGRATORCP.md`.

## 4. Memory layout

The normal reference build uses the low 32 bytes for vectors, leaves the rest of
the first 64 KiB reserved, and places the kernel at `0x00010000`:

| Range | Size | Contents |
|---|---|---|
| `0x00000000`–`0x0000001F` | 32 B | active low exception vector table (`.vectors`) |
| `0x00000020`–`0x0000FFFF` | 65,504 B | reserved; no allocated section may appear here |
| `0x00010000`–`0x000109A4` | 2,468 B | `.text` |
| `0x000109A4`–`0x00010C85` | 737 B | `.rodata` |
| `0x00010C85`–`0x00010C88` | 3 B | alignment padding |
| `0x00010C88`–`0x00010C98` | 16 B | `.bss` (`__k2_sctlr_boot`, console/PL011 state) |
| `0x00010C98`–`0x00014C98` | 16 KiB | SVC stack |
| `0x00014C98`–`0x00015C98` | 4 KiB | UND stack |
| `0x00015C98`–`0x00016C98` | 4 KiB | ABT stack |
| `0x00016C98`–`0x00017498` | 2 KiB | IRQ stack |
| `0x00017498`–`0x00017898` | 1 KiB | FIQ stack |
| `0x00017898` | — | `__image_end__` |
| `0x16000000` | 4 KiB | PL011 UART0 (memory-mapped I/O) |

The normal image span is **30,872 bytes** including all stacks; the loadable
flat binary is **68,741 bytes**. The `undef` and `data-abort` profiles add fault
code and sentinel literals, so their image ends are slightly higher
(`0x17950` and `0x17A60`). Every profile remains inside the enforced 64 KiB
budget.

`.vectors`, `.bss` and `.stack` are `SHT_NOBITS`/image data as appropriate; the
linker script asserts the vector base, vector size, image base, stack sizes,
stack contiguity and total budget. `tools/elfcheck.py` independently re-checks
the same facts from the ELF.

`__image_end__` is the first address a future physical-memory allocator may
use. The reserved low memory is not used for anything except the 32-byte vector
table in K2.

## 5. Exception path

The full ABI is in `docs/EXCEPTION_ABI.md`. In summary:

1. The CPU vectors through `0x04` (Undefined Instruction) or `0x10` (Data
   Abort) to `undef_entry` / `data_abort_entry`.
2. The entry stub masks IRQ/FIQ, subtracts 72 bytes from the banked SP, stores
   `r0-r12`, banked LR, SPSR, the vector byte offset and (for Abort) DFSR/DFAR,
   then calls `exception_dispatch(frame)` with `r0 = sp`.
3. The C handler identifies the vector, prints the mode from the handler CPSR,
   the interrupted mode from SPSR, LR, fault PC, DFSR/DFAR and the sentinel
   registers, prints `K2 EXCEPTION CAPTURED`, and halts.
4. SVC, Prefetch Abort, IRQ and FIQ use the same frame shape and call
   `exception_unexpected()`, which prints the vector name and halts. The
   reserved vector is a stack-free self-loop so even an unexpected entry cannot
   corrupt memory.

Handlers never return. K2 has no recovery path and does not pretend that a
faulting instruction can be resumed.

### Fault generators

The test profiles execute real instructions, not a fake call into a handler:

- `undef`: `ldr` sentinel values, then `udf #0` (`0xE7F000F0`);
- `data-abort`: set `SCTLR.A=1` and `SCTLR.U=1`, verify the read-back, then
  `ldr r0, =probe; add r0, r0, #1; ldr r1, [r0]` where `probe` is 16-byte
  aligned.

If the fault does not fire, the test function returns and prints
`K2 TEST FAILED`, so a missing exception cannot be mistaken for a PASS.

## 6. Contracts

### Loader → kernel

- ELF32, little-endian, `EM_ARM`, EABI5, soft-float flags.
- All loadable segments have `p_vaddr == p_paddr`.
- The vector segment is exactly 32 bytes at address `0x00000000`.
- The kernel text segment starts at `0x00010000`.
- Execution starts at `e_entry`, which equals `_start` and `reset_handler`.
- The loader may leave arbitrary values in `r0`–`r2`; K2 does not read them.
- Code and data are loaded; BSS is zeroed by `reset_handler`, not assumed to be
  zero by the loader.

### Entry → C

- ARM state, 32-bit, little-endian.
- SVC mode with IRQ and FIQ masked (enforced by `reset_handler`).
- `SCTLR.V=0` verified by read-back before any exception can occur.
- `SCTLR.A=0`, `SCTLR.U=0` for the normal run; the Data Abort test changes them
  deliberately and verifies the change.
- SVC/UND/ABT/IRQ/FIQ stack pointers are set and 8-byte aligned.
- BSS is zero before `kernel_main` is called.
- MMU and caches are assumed to be in reset state (off). K2 does not configure
  them; this is an explicit assumption, not a hardware guarantee.

### Kernel → console

- `console_init()` must be called before any output; calls before init are
  silently dropped rather than touching an uninitialised base address.
- Output is synchronous and polled.
- `\n` becomes CRLF; callers pass `\n` only.
- `console_write_hex32()` prints exactly `0x` plus eight lowercase digits.

### Kernel → PL011

- The driver owns a `struct pl011` with base address and precomputed divisors.
- `pl011_init()` programs 8N1, FIFO, no interrupts, TX and RX enabled.
- `pl011_write_byte()` blocks while `FR.TXFF` is set. A missing UART is a
  visible hang during bring-up, not silent loss.
- RX is enabled for future use but never read.

### Board

- `board_current()` returns a pointer to an immutable, statically allocated
  descriptor.
- Addresses in the descriptor must have a recorded provenance. The current
  values come from QEMU's live `info mtree` output and are not Gio facts.

## 7. Failure behaviour

- Undefined Instruction and Data Abort are fully decoded and printed.
- SVC, Prefetch Abort, IRQ, FIQ and the reserved vector stop with
  `EXCEPTION: UNEXPECTED ...` or a self-loop; they never return.
- A fault in the handler itself cannot be recovered in K2; masking IRQ/FIQ
  keeps asynchronous events out while the diagnostic runs.
- `kernel_main()` never returns; the return path after `bl kernel_main` is a
  defensive self-loop.
- A missing expected fault prints `K2 TEST FAILED: ...` and halts, which the
  runtime harness treats as a failure.

## 8. Extension points

The current structure is deliberately compatible with the following stages
without claiming they exist:

### Interrupt handling

The IRQ/FIQ vectors and stacks are real and configured. A future stage needs an
Integrator/CP PIC driver (`0x14000000`) and PIT timer (`0x13000000`), an IRQ
dispatch table, and an interrupt-exit path that restores the saved frame.

### Exception recovery

`struct exception_frame` already contains the complete interrupted context.
A future handler could choose to advance the saved PC or terminate the faulting
task; K2 deliberately does neither.

### Physical memory management

`board.ram_base`, `board.ram_size` and `__image_end__` bound the usable RAM. A
frame allocator can start at `__image_end__` without relinking.

### Scheduler

The per-mode stacks and the frame ABI are the prerequisites for context
switching. A scheduler will need per-task SVC stacks and a timer source; K2
does not pre-allocate task structures.

### Drivers

`board` is the place to add a device table (UART, timer, framebuffer, MMC).
Drivers stay board-agnostic and receive base addresses/configuration through
their init functions.

### Application environment

The SVC vector currently fails stop. A user environment will require MMU
mappings, user stacks, a syscall table and a loader. None of that is
implemented or implied by K2.

## 9. Engineering rules used by this implementation

- Source lists are explicit; there is no wildcard build that silently picks up
  an unrelated file.
- No libc, libgcc or compiler runtime is linked. The link fails on undefined
  helpers, and `tools/elfcheck.py` independently rejects undefined symbols.
- Board facts are centralised and sourced; no peripheral address is copied
  from K0 without verification.
- Every acceptance claim corresponds to a command that was actually run and an
  evidence file that was actually captured.
- Documentation is part of the build: the linker budget, vector layout, boot
  contract, exception ABI and platform boundary are recorded next to the code
  that depends on them.
