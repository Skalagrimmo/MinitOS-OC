#include "kernel/console.h"

#include "drivers/pl011.h"

static struct pl011 console_uart;
static int console_ready;

void console_init(const struct board *board)
{
    pl011_init(&console_uart,
               board->uart_base,
               board->uart_ibrd,
               board->uart_fbrd);
    console_ready = 1;
}

void console_putc(char c)
{
    if (!console_ready) {
        return;
    }

    if (c == '\n') {
        pl011_write_byte(&console_uart, (uint8_t)'\r');
    }
    pl011_write_byte(&console_uart, (uint8_t)c);
}

void console_write(const char *text)
{
    while (*text != '\0') {
        console_putc(*text);
        text++;
    }
}

void console_write_line(const char *text)
{
    console_write(text);
    console_putc('\n');
}

void console_write_hex32(uint32_t value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;

    console_write("0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        console_putc(digits[(value >> (unsigned int)shift) & 0xFu]);
    }
}
