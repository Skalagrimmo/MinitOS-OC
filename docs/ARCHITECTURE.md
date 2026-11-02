# MinitOS K1 Architecture

## 1. Scope

K1 is the smallest kernel that can prove a real ARMv6 execution path on QEMU:

1. the image is loaded at a known physical address;
2. the CPU starts at the image entry point in ARM state;
3. assembly establishes a controlled C environment;
4. C code initialises a real UART and emits a message;
5. the message is captured from the emulated serial line.

It is not a general-purpose kernel and it does not pretend to be one. Every
module exists because K1 needs it, and each one has an explicit contract for
the next stage.

## 2. Layer map

```text
                 +--------------------------------------+
                 |             kernel/main.c            |
                 |  composition root; prints and idles  |
                 +------------------+-------------------+
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
                 |  vectors, reset, stack, BSS, CP15    |
                 +--------------------------------------+
```

Dependency direction is downward only. `main.c` does not know PL011 register
offsets; the PL011 driver does not know which board it is on; the board layer
does not know how to print. `arch/armv6` is the only layer allowed to contain
ARM assembly and CP15 instructions.

## 3. Boot flow

For the current reference build:

| Step | Address | Action |
|---|---|---|
| 1 | `0x00010000` | QEMU loads the ELF segments and sets PC to `e_entry` |
| 2 | `0x00010000` | vector 0 (`_start`) executes `b reset_handler` |
| 3 | `0x00010020` | `reset_handler` forces SVC mode with IRQ/FIQ masked |
| 4 | `0x00010020` | SP := `__stack_top__` = `0x00014480` |
| 5 | `0x00010020` | BSS `0x00010470..0x00010480` is zeroed |
| 6 | `0x0001004c` | `bl kernel_main` (`0x0001036c`) |
| 7 | C | `board_current()` → `console_init()` → PL011 init |
| 8 | C | banner, board, UART and MIDR diagnostics are written |
| 9 | C | idle loop; the kernel never returns |

QEMU's 32-bit ARM ELF path does **not** insert a Linux bootloader stub: it
loads the ELF at `p_paddr` and jumps to `e_entry`. Therefore `r0`–`r2` are not
a usable boot protocol and K1 ignores them. This is verified in
`docs/PLATFORM_INTEGRATORCP.md`.

## 4. Memory layout

The reference build uses a 64 KiB reservation at the bottom of emulated RAM
and a 16 KiB boot stack:

| Range | Size | Contents |
|---|---|---|
| `0x00000000`–`0x07FFFFFF` | 128 MiB | QEMU Integrator/CP RAM |
| `0x00000000`–`0x0000FFFF` | 64 KiB | deliberately unused by K1 |
| `0x00010000`–`0x00010020` | 32 B | 8-word exception vector table |
| `0x00010020`–`0x000103E8` | 968 B | `.text` |
| `0x000103E8`–`0x0001046D` | 133 B | `.rodata` (banner, board table, format strings) |
| `0x0001046D`–`0x00010470` | 3 B | alignment padding |
| `0x00010470`–`0x00010480` | 16 B | `.bss` (`console_ready`, `console_uart`) |
| `0x00010480`–`0x00014480` | 16 KiB | `.stack` (NOBITS) |
| `0x00014480` | — | `__image_end__` |
| `0x16000000` | 4 KiB | PL011 UART0 (memory-mapped I/O) |

The whole image span is **17,536 bytes** including the stack; the loadable file
is **1,133 bytes** because `.bss` and `.stack` are `SHT_NOBITS`. The linker
script enforces a 64 KiB image budget so accidental growth fails the build
instead of silently colliding with future reservations.

`__image_end__` is the first address a future physical-memory allocator may
use. The 64 KiB at address 0 is intentionally left free for a future low-vector
copy, boot parameters, or a board-specific boot record; K1 does not interpret
it.

## 5. Contracts

### Loader → kernel

- ELF32, little-endian, `EM_ARM`, EABI5, soft-float flags.
- All loadable segments have `p_vaddr == p_paddr`.
- The first segment starts at `0x00010000`.
- Execution starts at `e_entry`, which equals `_start` and the first word of
  `.vectors`.
- The loader may leave arbitrary values in `r0`–`r2`; K1 does not read them.
- Code and data are loaded; BSS is zeroed by `reset_handler`, not assumed to be
  zero by the loader.

### Entry → C

- ARM state, 32-bit, little-endian.
- SVC mode with IRQ and FIQ masked (enforced by `reset_handler`).
- Stack pointer is 8-byte aligned per AAPCS.
- BSS is zero before `kernel_main` is called.
- MMU and caches are assumed to be in reset state (off). K1 does not configure
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
- `pl011_write_byte()` blocks while `FR.TXFF` is set. There is no timeout in
  K1: a missing UART must be a visible hang during bring-up, not silent loss.
- RX is enabled for future use but never read.

### Board

- `board_current()` returns a pointer to an immutable, statically allocated
  descriptor.
- Addresses in the descriptor must have a recorded provenance. The current
  values come from QEMU's live `info mtree` output and are not Gio facts.

## 6. Failure behaviour

- Undefined instruction, SVC, prefetch abort, data abort, reserved, IRQ and
  FIQ vectors are separate self-loop traps. A fault is therefore visible as a
  hung PC at a distinct vector address under a debugger.
- There is no recovery, no fault decoding and no panic console yet. A fault
  after UART initialisation could be reported later by adding a handler that
  uses the already-initialised console.
- `kernel_main()` never returns; the return path after `bl kernel_main` is a
  defensive self-loop.

## 7. Extension points

The current structure is deliberately compatible with the following stages
without claiming they exist:

### Exceptions and interrupts

The 8-word vector table is already at the image entry. Replacing the self-loop
slots with branches to real handlers does not move the entry point. A future
stage needs:

- per-mode stacks (IRQ, FIQ, abort, undefined, SVC) selected on entry;
- a trap frame layout saved on the appropriate stack;
- Integrator/CP PIC at `0x14000000` and PIT at `0x13000000`;
- an IRQ dispatch table and a timer tick;
- SVC as the future syscall gate.

### Physical memory management

`board.ram_base`, `board.ram_size` and `__image_end__` bound the usable RAM.
A frame allocator can start at `__image_end__` without relinking. The 64 KiB
low reservation remains free for boot metadata.

### Scheduler

The boot stack is a single SVC stack. A scheduler will need per-task stacks,
a context-switch primitive and a timer source. K1 intentionally does not
pre-allocate task structures that would constrain those decisions.

### Drivers

`board` is the place to add a device table (UART, timer, framebuffer, MMC).
Drivers stay board-agnostic and receive base addresses/configuration through
their init functions. The console facade can gain multiple sinks (UART,
framebuffer, in-memory log) without changing callers.

### Framebuffer

QEMU's Integrator/CP exposes a PL110 at `0xC0000000` (see the platform map).
A future framebuffer driver belongs in `src/drivers/`; the current console
interface is the natural insertion point for a second output backend.

### Application environment

The SVC vector is reserved. A user environment will require MMU mappings, user
stacks, a syscall table and a loader. None of that is implemented or implied
by K1.

## 8. Engineering rules used by this implementation

- Source lists are explicit; there is no wildcard build that silently picks up
  an unrelated file.
- No libc, libgcc or compiler runtime is linked. The link fails on undefined
  helpers, and `tools/elfcheck.py` independently rejects undefined symbols.
- Board facts are centralised and sourced; no peripheral address is copied
  from K0 without verification.
- Every acceptance claim corresponds to a command that was actually run and
  an evidence file that was actually captured.
- Documentation is part of the build: the linker budget, the boot contract and
  the platform boundary are recorded next to the code that depends on them.
