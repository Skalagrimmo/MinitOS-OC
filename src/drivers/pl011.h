#ifndef MINITOS_DRIVERS_PL011_H
#define MINITOS_DRIVERS_PL011_H

#include <stdint.h>

/*
 * Minimal polled PL011 UART driver.
 *
 * The driver knows only the PL011 register model. It does not know which
 * board it is on and it does not use interrupts. RX is enabled so that a
 * later console-input module can be added without changing the initialisation
 * sequence, but K1 never reads it.
 */
struct pl011 {
    uintptr_t base;
    uint16_t ibrd;
    uint8_t fbrd;
};

/*
 * Program the UART for 8N1, FIFO enabled, no interrupts, TX+RX enabled.
 * ibrd/fbrd are precomputed by the board layer (see board/integratorcp.h).
 */
void pl011_init(struct pl011 *uart, uintptr_t base, uint16_t ibrd, uint8_t fbrd);

/* Block until the TX FIFO has room, then write one byte. */
void pl011_write_byte(struct pl011 *uart, uint8_t byte);

#endif /* MINITOS_DRIVERS_PL011_H */
