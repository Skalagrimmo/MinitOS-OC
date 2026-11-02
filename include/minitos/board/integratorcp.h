#ifndef MINITOS_BOARD_INTEGRATORCP_H
#define MINITOS_BOARD_INTEGRATORCP_H

/*
 * ARM Integrator/CP constants for the QEMU reference machine.
 *
 * Provenance:
 *   - QEMU 11.1.0, `-M integratorcp -cpu arm1136`
 *   - QMP `info mtree` (see docs/evidence/qemu-mtree.txt)
 *   - QEMU source hw/arm/integratorcp.c
 *
 * These addresses describe the emulated Integrator/CP. They are NOT the
 * Samsung Galaxy Gio GT-S5660 / MSM7227 memory map.
 */

#define INTEGRATORCP_RAM_BASE      0x00000000u
#define INTEGRATORCP_RAM_SIZE      (128u * 1024u * 1024u)

#define INTEGRATORCP_UART0_BASE    0x16000000u
#define INTEGRATORCP_UART1_BASE    0x17000000u

/*
 * UARTCLK is an Integrator/CP board assumption, not a value measured on
 * hardware. QEMU does not enforce the PL011 baud rate for output.
 *
 * PL011 divisor: UARTCLK / (16 * baud) = IBRD + FBRD/64
 *                 7,372,800 / (16 * 115,200) = 4.0
 *                 => IBRD = 4, FBRD = 0
 *
 * The divisors are precomputed here so the kernel does not need a runtime
 * division helper from libgcc.
 */
#define INTEGRATORCP_UART_CLOCK_HZ 7372800u
#define INTEGRATORCP_UART_BAUD     115200u
#define INTEGRATORCP_UART_IBRD     4u
#define INTEGRATORCP_UART_FBRD     0u

#endif /* MINITOS_BOARD_INTEGRATORCP_H */
