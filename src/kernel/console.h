#ifndef MINITOS_KERNEL_CONSOLE_H
#define MINITOS_KERNEL_CONSOLE_H

#include <stdint.h>

#include "minitos/board.h"

/*
 * Kernel console facade.
 *
 * Callers depend on this interface, not on the UART driver. The current
 * backend is a polled PL011; replacing it later (framebuffer console,
 * buffered log, multiple sinks) does not change callers.
 *
 * All functions are synchronous. '\n' is translated to CRLF so the output is
 * readable both in a terminal and in a raw serial capture.
 */

void console_init(const struct board *board);

void console_putc(char c);
void console_write(const char *text);
void console_write_line(const char *text);

/* Writes "0x" followed by exactly eight lowercase hexadecimal digits. */
void console_write_hex32(uint32_t value);

#endif /* MINITOS_KERNEL_CONSOLE_H */
