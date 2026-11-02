#include "minitos/board.h"
#include "minitos/board/integratorcp.h"

/*
 * K2 has exactly one build-time board. Keeping the table static and const
 * means it lives in .rodata and cannot be mutated by kernel code.
 */
static const struct board integratorcp_board = {
    .name = "integratorcp",
    .ram_base = INTEGRATORCP_RAM_BASE,
    .ram_size = INTEGRATORCP_RAM_SIZE,
    .uart_base = INTEGRATORCP_UART0_BASE,
    .uart_clock_hz = INTEGRATORCP_UART_CLOCK_HZ,
    .uart_baud = INTEGRATORCP_UART_BAUD,
    .uart_ibrd = INTEGRATORCP_UART_IBRD,
    .uart_fbrd = INTEGRATORCP_UART_FBRD,
};

const struct board *board_current(void)
{
    return &integratorcp_board;
}
