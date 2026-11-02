# K0 Analysis

## 1. Input

The starting point was `minitos-k0.zip`. It was extracted to a temporary
analysis directory; the original archive and the extracted K0 tree were not
modified. K1 lives in a separate repository.

K0 contains:

```text
Makefile
README.md
linker/qemu-integratorcp.ld
src/arch/armv6/entry.S
src/kernel/main.c
tools/verify_elf.py
docs/K0_TOOLCHAIN_PROOF.md
build/  (prebuilt ELF, BIN, map, disassembly, build log, SHA256SUMS)
```

## 2. What K0 actually builds

Inspecting the supplied `build/minitos-k0.elf` with GNU readelf gives:

| Property | K0 value |
|---|---|
| Class / data / machine | ELF32, little-endian, `EM_ARM` |
| Type | `ET_EXEC` |
| EABI flags | `0x05000200` (EABI5, soft-float) |
| Entry point | `0x00010000` |
| Program headers | 5 (`LOAD` × 3, `GNU_STACK`, `ARM_EXIDX`) |
| `.text` | `0x00010000`, 76 bytes |
| `.data` | `0x0001005c`, 4 bytes (`minitos_k0_marker`) |
| `.bss` | `0x00010060`, size 0 |
| `_start` | `0x00010000`, size 36, `FUNC GLOBAL` |
| `kernel_main` | `0x00010030`, `FUNC GLOBAL` |
| Stack symbols | `0x00010060` … `0x00014060` (16 KiB) |
| ELF SHA-256 | `573d5d557be9850e4535c9cbe16ea818bdfd4e9fb6d94f86b8125ca2fb74efc8` |

So K0 genuinely produced an ELF32 ARM executable with the expected reference
entry point. That is a useful toolchain proof.

## 3. What K0's verification actually proves

`tools/verify_elf.py` checks:

- ELF magic;
- `ELFCLASS32`;
- little-endian data encoding;
- `EM_ARM`;
- `e_type` is 2 or 3;
- `e_entry != 0`;
- file is larger than 256 bytes.

It does **not** check:

- that `e_entry` equals `_start` or the link address;
- that `_start` is the first word of a vector table;
- program-header physical addresses, permissions or RAM bounds;
- required symbols or section layout;
- absence of undefined libc/libgcc symbols;
- that the flat binary matches the ELF load image;
- that the code executed.

The K0 build log ends with `K0 VERIFY: PASS` for these static checks. The K0
README and `docs/K0_TOOLCHAIN_PROOF.md` explicitly state that QEMU was not
available and runtime execution was not performed. K1 does not treat that
`PASS` as runtime evidence.

## 4. What K0's source does

### `src/arch/armv6/entry.S`

- sets `SP = __stack_top__`;
- clears BSS with a word loop;
- calls `kernel_main`;
- loops forever if it returns.

It does **not** define an exception vector table, force a known CPSR mode, or
initialise any device.

### `src/kernel/main.c`

- defines a `volatile uint32_t minitos_k0_marker`;
- increments it once;
- loops with `nop`.

There is no console, no UART, no board description and no runtime diagnostic.

### `linker/qemu-integratorcp.ld`

- `ENTRY(_start)`;
- RAM at `0x00010000`, length 16 MiB;
- stack 16 KiB after BSS;
- discards `.comment`, `.note*`, `.eh_frame*`.

The 16 MiB length is not a verified QEMU Integrator/CP fact: the live machine
has 128 MiB at address 0. The 16 MiB subset happens to contain the image, so
the layout is not immediately fatal on QEMU, but it is an assumption rather
than a measurement.

### `Makefile`

- Clang targeting `arm-none-eabi`;
- `-mcpu=arm1136jf-s -marm -mfloat-abi=soft`;
- `-Os`, freestanding flags, `-fno-pic -fno-pie`;
- links with LLD and `-nostdlib`;
- verification depends on GNU `readelf`, `llvm-objdump`, `llvm-objcopy` and
  `python3` being present under those exact names.

The reference environment for K1 did not have Clang, LLVM binutils, GNU
readelf, `python3` or Make. K1 therefore chose and pinned a complete GNU Arm
toolchain instead of assuming K0's environment.

## 5. Gaps that K1 addresses

| Area | K0 | K1 |
|---|---|---|
| Runtime execution | not performed | QEMU run captured and asserted |
| Observable output | none | PL011 UART banner |
| Board facts | reference address only | live QMP memory map, explicit board descriptor |
| Entry validation | non-zero only | `e_entry == _start == image base`, vector target, segment checks |
| Vector table | absent | 8-word table at image base; reserved exception slots |
| CPU mode | inherited from loader | SVC + IRQ/FIQ masked explicitly |
| BSS / stack | symbols only | NOBITS sections, 8-byte alignment, 16 KiB checked |
| libc/libgcc | not explicitly checked | `--no-undefined` plus independent ELF symbol check |
| Toolchain | Clang assumed | GCC 15.2.1 pinned, version and hash recorded |
| Reproducibility | same-toolchain expectation in prose | two clean builds compared by SHA-256 |
| Documentation | toolchain proof only | architecture, platform, decisions, assumptions, acceptance evidence |
| Gio boundary | warning present | explicit non-assumption and separate board layer |

## 6. What K1 deliberately keeps

- A **64 KiB low reservation** with the image based at `0x00010000`, because
  it is a practical QEMU reference layout and leaves low memory free. This is
  not inherited as a Gio fact.
- `-mcpu=arm1136jf-s`, ARM state, soft-float ABI.
- Freestanding C, no libc, no host runtime.
- Producing both ELF and flat binary, plus map and disassembly artifacts.
- A 16 KiB boot stack. K1 makes it an explicit NOLOAD section, checks its size
  and alignment, and records measured static stack usage (24 bytes maximum in
  the current build).

## 7. What K1 explicitly rejects

- `0x00010000` as a Galaxy Gio load address.
- The K0 linker's 16 MiB RAM length as a target-board fact.
- Compile/link `PASS` as evidence of execution.
- Any implied QEMU UART address (K0 had none; K1 measured `0x16000000`).
- The assumption that K0's tool names or host tools are available.
- The assumption that a bootloader will leave a particular CPU mode or
  register state; K1 establishes the mode itself.

K0 was useful as a toolchain proof and as a starting question. It was not
treated as an architecture to copy.
