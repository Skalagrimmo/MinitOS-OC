# Platform: QEMU ARM Integrator/CP

## 1. Identification

Reference environment:

- QEMU **11.1.0** (`v11.1.0-12130-ge470268ff4`)
- machine `integratorcp`
- CPU model `arm1136`
- RAM explicitly pinned with `-m 128M`

Commands used to verify the platform rather than trusting K0:

```sh
qemu-system-arm -M help
qemu-system-arm -M integratorcp -cpu help
python tools/verify_platform.py
```

`tools/verify_platform.py` also asks the live machine for its memory map via
QMP `human-monitor-command: info mtree`. The captured output is
[`docs/evidence/qemu-mtree.txt`](evidence/qemu-mtree.txt).

## 2. Verified memory map

From the live QEMU 11.1.0 instance (`-M integratorcp -cpu arm1136 -m 128M`):

| Start | End | Device | Notes |
|---|---|---|---|
| `0x00000000` | `0x07FFFFFF` | `integrator.ram` | 128 MiB main RAM |
| `0x10000000` | `0x107FFFFF` | `integratorcm` | system controller |
| `0x13000000` | `0x13000FFF` | `icp_pit` | programmable interrupt timer |
| `0x14000000` | `0x147FFFFF` | `icp-pic` | interrupt controller |
| `0x15000000` | `0x15000FFF` | `pl031` | RTC |
| `0x16000000` | `0x16000FFF` | `pl011` | **UART0, used by K1** |
| `0x17000000` | `0x17000FFF` | `pl011` | UART1 |
| `0x18000000` | `0x18000FFF` | `pl050` | keyboard |
| `0x19000000` | `0x19000FFF` | `pl050` | mouse |
| `0x1A000000` | `0x1AFFFFFF` | `dbg-leds` | debug LEDs |
| `0x1C000000` | `0x1C000FFF` | `pl181` | MMC |
| `0x1D000000` | `0x1D000FFF` | `pl041` | audio |
| `0x80000000` | `0x87FFFFFF` | RAM alias | alias of main RAM |
| `0xC0000000` | `0xC0000FFF` | `pl110` | LCD controller |
| `0xC8000000` | `0xC800000F` | `smc91c111` | Ethernet |
| `0xCA000000` | `0xCA7FFFFF` | `icp-pic` | secondary PIC |
| `0xCB000000` | `0xCB7FFFFF` | `icp_ctrl_regs` | CP control registers |

K1 uses only RAM at `0x00000000` and PL011 UART0 at `0x16000000`. Everything
else in the table is recorded so later drivers do not have to guess.

## 3. Boot and load contract

QEMU's Integrator/CP board model sets:

```c
bootinfo.loader_start = 0x0;
bootinfo.board_id     = 0x113;
bootinfo.ram_size     = machine->ram_size;
```

and calls `arm_load_kernel()`. For a 32-bit ARM **ELF** image, QEMU:

1. loads each `PT_LOAD` segment at its physical address (`p_paddr`);
2. sets the initial PC to the ELF entry point (`e_entry`);
3. does **not** write the Linux bootloader stub and does **not** provide a
   Linux `r0/r1/r2` boot protocol.

This was confirmed by inspecting QEMU's `hw/arm/integratorcp.c` and
`hw/arm/boot.c`, and by observing the actual K1 execution:
`e_entry = 0x00010000`, first instruction `b reset_handler`, UART output
present.

Consequences for K1:

- `r0`–`r2` are treated as unspecified and ignored.
- No ATAG/DTB pointer is expected.
- The image must be an ELF with correct `p_paddr`; a raw binary would take
  QEMU's Linux-image path and a different load address.
- K1 still forces CPSR to SVC with IRQ/FIQ masked instead of relying on the
  loader's CPU state.

## 4. CPU configuration

Build flags:

```text
--target arm-none-eabi
-mcpu=arm1136jf-s
-marm
-mfloat-abi=soft
```

QEMU:

```text
-M integratorcp -cpu arm1136
```

QEMU's `-M integratorcp -cpu help` lists `arm1136` (and `arm1136-r2`). K1
passes `-cpu arm1136` explicitly because the machine's default is ARM926.

Runtime proof comes from CP15 MIDR (`mrc p15, 0, r0, c0, c0, 0`):

```text
cpu midr: 0x4117b363
```

Decoded:

| Field | Value | Meaning |
|---|---|---|
| implementer `[31:24]` | `0x41` | ARM |
| variant `[23:20]` | `0x1` | model variant |
| architecture `[19:16]` | `0x7` | ARMv6 |
| primary part `[15:4]` | `0xB36` | ARM1136 |
| revision `[3:0]` | `0x3` | model revision |

The QEMU ARM1136 model is not a claim that a specific MSM7227 revision has the
same MIDR or errata. It proves the emulated core is an ARM1136 and that the
built code executes on it.

## 5. PL011 UART programming model used by K1

UART0 base: `0x16000000`.

Registers used (32-bit, little-endian):

| Offset | Register | K1 use |
|---|---|---|
| `0x000` | `UARTDR` | write one byte |
| `0x018` | `UARTFR` | poll `TXFF` bit 5 |
| `0x024` | `UARTIBRD` | integer baud divisor |
| `0x028` | `UARTFBRD` | fractional baud divisor |
| `0x02C` | `UARTLCR_H` | `FEN | WLEN_8` = `0x70` |
| `0x030` | `UARTCR` | `UARTEN | TXE | RXE` = `0x301` |
| `0x034` | `UARTIFLS` | set to 0 (unused) |
| `0x038` | `UARTIMSC` | set to 0 (no interrupts) |
| `0x044` | `UARTICR` | clear pending interrupts = `0x7FF` |

Initialisation sequence:

1. write `CR = 0` to disable the UART while reconfiguring;
2. clear pending interrupts with `ICR = 0x7FF`;
3. program `IBRD` and `FBRD`;
4. program `LCR_H = 0x70` (FIFO enabled, 8 data bits, no parity, one stop);
5. set `IFLS = 0`, `IMSC = 0`;
6. write `CR = 0x301` (UART enabled, TX and RX enabled).

QEMU-specific finding: if `UARTEN` is not set, writes to `UARTDR` are dropped
and QEMU logs a guest error (once). K1 therefore explicitly enables the UART;
the acceptance harness runs with `-d guest_errors` and requires an empty log.

Transmit is polled:

```c
while ((mmio_read32(base + UARTFR) & UARTFR_TXFF) != 0) { }
mmio_write32(base + UARTDR, byte);
```

No interrupts, no FIFO threshold handling and no RX path are used in K1.

### Baud rate

The PL011 divisor formula is:

```text
UARTCLK / (16 * baud) = IBRD + FBRD / 64
```

K1 uses the Integrator/CP reference clock assumption `UARTCLK = 7,372,800 Hz`
and `baud = 115,200`:

```text
7,372,800 / (16 * 115,200) = 4.0  =>  IBRD = 4, FBRD = 0
```

The divisors are precomputed in `include/minitos/board/integratorcp.h` so the
kernel does not call a libgcc division helper. **QEMU does not enforce baud
timing for output**, so this value is not proven by the QEMU run. It is a board
assumption for future hardware and is listed as unverified in
`ASSUMPTIONS_AND_LIMITATIONS.md`.

## 6. What this platform does not model

- MSM7227 / Galaxy Gio SoC, SDRAM controller, boot ROM or bootloader.
- Real UART clock accuracy, baud timing or electrical behaviour.
- Cache and MMU behaviour of a real ARM1136 implementation.
- Instruction and memory timing.
- The Gio's physical memory map or peripheral addresses.

Passing on `integratorcp` proves the ARMv6 code path, the ELF contract, the
PL011 driver logic and the build/verification pipeline. It does not prove the
Gio port.

## 7. Evidence

- `docs/evidence/qemu-mtree.txt` — live QMP memory map.
- `docs/evidence/qemu-platform.txt` — machine/CPU/map checks.
- `docs/evidence/qemu-serial.txt` — raw UART capture.
- `docs/evidence/runtime-evidence.txt` — runtime checks and exact command.
