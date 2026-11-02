#include "minitos/board.h"
#include "minitos/kernel.h"

#include "arch/armv6/cpu.h"
#include "kernel/console.h"

void kernel_main(void)
{
    const struct board *board = board_current();

    console_init(board);

    console_write_line("MINITOS KERNEL STARTED");
    console_write("board: ");
    console_write_line(board->name);
    console_write("uart: pl011 @ ");
    console_write_hex32(board->uart_base);
    console_putc('\n');
    console_write("cpu midr: ");
    console_write_hex32(cpu_read_midr());
    console_putc('\n');
    console_write_line("idle");

    /*
     * K1 has no scheduler and no interrupts. Staying here is intentional:
     * the image must not attempt to return to reset_handler or execute
     * whatever follows in memory.
     */
    for (;;) {
        cpu_relax();
    }
}
