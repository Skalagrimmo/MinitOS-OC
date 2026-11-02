# K2 Exception ABI

This document is the contract between the ARM1136 exception entry stubs in
`src/arch/armv6/exception.S` and the C handlers in
`src/arch/armv6/exception.c`. The C header
`include/minitos/exception.h` enforces the same layout with static assertions,
and `tools/elfcheck.py` re-checks the compiled size and alignment from the ELF.

## 1. Active vector table

`reset_handler` clears `SCTLR.V` (bit 13) and verifies the read-back before any
exception or C code can run. The active table is therefore the low table at
physical address `0x00000000`:

| Offset | Exception | Entry symbol | K2 behaviour |
|---|---|---|---|
| `0x00` | Reset | `reset_handler` | full startup path |
| `0x04` | Undefined Instruction | `undef_entry` | diagnostic handler, halt |
| `0x08` | Supervisor Call | `svc_entry` | unexpected-path diagnostic, halt |
| `0x0C` | Prefetch Abort | `prefetch_entry` | unexpected-path diagnostic, halt |
| `0x10` | Data Abort | `data_abort_entry` | diagnostic handler, halt |
| `0x14` | Reserved | `reserved_entry` | stack-free self-loop |
| `0x18` | IRQ | `irq_entry` | unexpected-path diagnostic, halt |
| `0x1C` | FIQ | `fiq_entry` | unexpected-path diagnostic, halt |

The table is 32 bytes (`0x00`–`0x1F`), executable, allocated, and lives in its
own `PT_LOAD` segment at virtual and physical address 0. The kernel image is a
separate `PT_LOAD` beginning at `0x00010000`. The gap `0x20`–`0xFFFF` contains
no allocated section; the ELF checker fails if one appears.

The old K1 table at `0x00010000` was never an active CPU vector table. K2
removes it from the image entirely; `0x00010000` is only the ELF entry point
and the start of `.text`.

## 2. Startup state

Before the first C call, `reset_handler` establishes:

| State | Value / rule |
|---|---|
| CPSR mode | SVC (`0x13`), ARM state, little-endian (`E=0`) |
| IRQ / FIQ | both masked (`I=1`, `F=1`) |
| `SCTLR.V` | 0 (low vectors), verified by read-back |
| `SCTLR.A` | 0 (alignment faults disabled for the normal run) |
| `SCTLR.U` | 0 (unaligned accesses disabled for the normal run) |
| MMU / caches | left in the QEMU reset state; K2 does not program them |
| SVC SP | `__svc_stack_top__`, 8-byte aligned |
| UND SP | `__und_stack_top__`, 8-byte aligned |
| ABT SP | `__abt_stack_top__`, 8-byte aligned |
| IRQ SP | `__irq_stack_top__`, 8-byte aligned |
| FIQ SP | `__fiq_stack_top__`, 8-byte aligned |
| `.bss` | zeroed by `reset_handler` |

The Data Abort profile deliberately changes `SCTLR.A` and `SCTLR.U` to 1 after
startup, verifies the read-back, and only then executes the unaligned load.

## 3. Stack layout

Each exception mode runs its handler on its own banked stack. The linker
allocates the stacks contiguously after `.bss` and asserts every size:

| Mode | Size | Linker symbols |
|---|---|---|
| SVC | 16 KiB | `__svc_stack_bottom__` / `__svc_stack_top__` |
| UND | 4 KiB | `__und_stack_bottom__` / `__und_stack_top__` |
| ABT | 4 KiB | `__abt_stack_bottom__` / `__abt_stack_top__` |
| IRQ | 2 KiB | `__irq_stack_bottom__` / `__irq_stack_top__` |
| FIQ | 1 KiB | `__fiq_stack_bottom__` / `__fiq_stack_top__` |

Every bottom and top is 8-byte aligned, and adjacent regions touch exactly
(`svc_top == und_bottom`, etc.). The ELF checker verifies both properties.

Handlers do not switch to the SVC stack. Running in the entered mode keeps the
diagnostic independent of the interrupted context's stack, and it means a
future recovery path already has the correct exception-mode SP.

## 4. Saved frame

The entry stubs build this structure on the banked stack:

```c
struct exception_frame {
    uint32_t r0;      /*   0 */
    uint32_t r1;      /*   4 */
    uint32_t r2;      /*   8 */
    uint32_t r3;      /*  12 */
    uint32_t r4;      /*  16 */
    uint32_t r5;      /*  20 */
    uint32_t r6;      /*  24 */
    uint32_t r7;      /*  28 */
    uint32_t r8;      /*  32 */
    uint32_t r9;      /*  36 */
    uint32_t r10;     /*  40 */
    uint32_t r11;     /*  44 */
    uint32_t r12;     /*  48 */
    uint32_t lr;      /*  52: banked LR of the exception mode */
    uint32_t spsr;    /*  56: CPSR of the interrupted context */
    uint32_t vector;  /*  60: vector byte offset: 0x04, 0x10, ... */
    uint32_t dfsr;    /*  64: Data Abort only, otherwise 0 */
    uint32_t dfar;    /*  68: Data Abort only, otherwise 0 */
} __attribute__((aligned(8)));
```

Properties enforced at build time:

- size is exactly **72 bytes** (18 words);
- alignment is exactly **8 bytes**;
- `sizeof(frame) % 8 == 0`, so the banked SP remains 8-byte aligned at the C
  call boundary;
- the offsets of `r0`, `r12`, `lr`, `spsr`, `vector`, `dfsr` and `dfar` are
  static assertions in the header.

The assembly constants and the C structure are two independent declarations of
the same ABI. `exception.c` exports the compiled `sizeof` and `_Alignof` values
in `.rodata.k2abi`; `tools/elfcheck.py` reads them and additionally verifies
the ABI from the ELF, so a mismatch cannot silently pass.

## 5. Entry stub algorithm

For every diagnostic entry:

```text
cpsid if                      ; make the handler non-preemptible
sub sp, sp, #72               ; frame is a multiple of 8
stmia sp, {r0-r12}            ; save the caller-visible general registers
str lr, [sp, #52]             ; banked LR of this exception mode
mrs r0, spsr
str r0, [sp, #56]             ; interrupted CPSR
mov r0, #<vector offset>
str r0, [sp, #60]
# Data Abort only:
mrc p15, 0, r0, c5, c0, 0     ; DFSR
str r0, [sp, #64]
mrc p15, 0, r0, c6, c0, 0     ; DFAR
str r0, [sp, #68]
# all other entries:
str zero, [sp, #64]
str zero, [sp, #68]
mov r0, sp                    ; first argument: const struct exception_frame *
bl exception_dispatch         ; or exception_unexpected
1: b 1b                       ; defensive halt if C ever returns
```

`reserved_entry` is intentionally different: it is a bare `b reserved_entry`
with no stack or device access, so it is safe even if the vector is entered
before any stack exists.

## 6. Fault PC reconstruction

The ARM1136 exception model gives different return offsets:

| Exception | Link register value | Faulting instruction |
|---|---|---|
| Undefined Instruction | `LR_und = faulting PC + 4` | `LR_und - 4` |
| Data Abort | `LR_abt = faulting PC + 8` | `LR_abt - 8` |

The handlers print both `lr` and `fault_pc`, and the runtime harness asserts the
difference (4 for UND, 8 for ABT) as well as the fault PC falling inside the
loaded kernel image. The observed values are:

```text
undef:      lr=0x00010240  fault_pc=0x0001023c  (the udf #0 instruction)
data-abort: lr=0x0001026c  fault_pc=0x00010264  (the unaligned ldr)
```

## 7. DFSR / DFAR

For Data Abort the stub reads:

- **DFSR** — CP15 c5, c0, 0 — Data Fault Status Register;
- **DFAR** — CP15 c6, c0, 0 — Data Fault Address Register.

The test expects the alignment-fault status (`DFSR[3:0] == 0b0001`) and a DFAR
equal to the unaligned probe address (`probe + 1`). The runtime evidence shows
`dfsr=0x00000001` and `dfar=0x00010e41` for probe `0x00010e40`.

DFSR and DFAR are only architecturally valid in Abort mode, which is why the
stub reads them there rather than after returning to SVC.

## 8. Mode and sentinel diagnostics

The handler prints:

- `vector` — byte offset from the frame;
- `mode` — decoded from the handler's own CPSR, proving the CPU is in UND/ABT;
- `handler_cpsr` — raw CPSR in the handler;
- `lr`, `spsr`, `spsr_mode` — interrupted context;
- `fault_pc` — reconstructed as above;
- `r0`, `r1`, `r2`, `r12` — sentinels written by the fault generator.

The UND test writes `r0=0x4B2D0001`, `r1=0x4B2D0002`,
`r12=0x4B2D000C`. The Data Abort test writes `r1=0x4B2D0002`,
`r2=0x4B2D0003`, `r12=0x4B2D000C` and leaves `r0` as the unaligned address.
The harness requires these exact values, so a handler that prints a canned
message without saving the real frame cannot pass.

## 9. Termination rule

K2 is fail-stop. After the diagnostic:

- `exception_dispatch()` prints `K2 EXCEPTION CAPTURED` and calls `cpu_halt()`;
- `exception_unexpected()` prints `EXCEPTION: UNEXPECTED <name>`, the common
  fields and `K2 EXCEPTION CAPTURED`, then halts;
- the assembly stub keeps a self-loop immediately after the `bl` as a second
  line of defence.

No K2 handler modifies the saved context, advances the PC or returns. Recovery
is explicitly future work.

## 10. Verification points

The ABI is checked at four independent levels:

| Level | Check |
|---|---|
| C compiler | `_Static_assert` on size, alignment and every named offset |
| Assembly | fixed `.equ` constants matching the header |
| Build | linker script asserts vector base/size, image base and stack sizes |
| ELF | `tools/elfcheck.py` decodes all 8 vector branches, reads the compiled frame size/alignment, and checks the fault instruction sequences |
| Runtime | QEMU UART evidence for vector, mode, SPSR, LR, DFSR/DFAR and sentinels |
