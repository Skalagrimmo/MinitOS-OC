#ifndef MINITOS_BOARD_H
#define MINITOS_BOARD_H

#include <stdint.h>

/*
 * Immutable board description.
 *
 * The kernel core receives board facts through this structure instead of
 * including a board header directly. A future port adds another constructor
 * of this structure (or a runtime-selected table) without touching the
 * console or the driver.
 */
struct board {
    const char *name;
    uintptr_t ram_base;
    uint32_t ram_size;
    uintptr_t uart_base;
    uint32_t uart_clock_hz;
    uint32_t uart_baud;
    uint16_t uart_ibrd;
    uint8_t uart_fbrd;
};

/* The board selected at build time for this kernel image. */
const struct board *board_current(void);

#endif /* MINITOS_BOARD_H */
