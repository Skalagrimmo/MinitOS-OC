#include "minitos/board.h"
#include "minitos/exception.h"
#include "minitos/kernel.h"
#include "minitos/test_profile.h"

#include "arch/armv6/cpu.h"
#include "kernel/console.h"
#include "kernel/k2_tests.h"

/* Linker-provided stack bounds. */
extern uint8_t __svc_stack_bottom__[];
extern uint8_t __svc_stack_top__[];
extern uint8_t __und_stack_bottom__[];
extern uint8_t __und_stack_top__[];
extern uint8_t __abt_stack_bottom__[];
extern uint8_t __abt_stack_top__[];
extern uint8_t __irq_stack_bottom__[];
extern uint8_t __irq_stack_top__[];
extern uint8_t __fiq_stack_bottom__[];
extern uint8_t __fiq_stack_top__[];

/* Written by reset_handler after the SCTLR read-back. */
extern uint32_t __k2_sctlr_boot;

/* Compiled frame ABI values, also checked by tools/elfcheck.py. */
extern const uint32_t k2_exception_frame_size;
extern const uint32_t k2_exception_frame_align;

static void write_stack(const char *name, const uint8_t *bottom,
                        const uint8_t *top)
{
    console_write("K2 stack ");
    console_write(name);
    console_write(": ");
    console_write_hex32((uint32_t)(uintptr_t)bottom);
    console_write(" - ");
    console_write_hex32((uint32_t)(uintptr_t)top);
    console_putc('\n');
}

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

    console_write_line("K2 vectors: low @ 0x00000000");
    console_write("K2 sctlr: ");
    console_write_hex32(__k2_sctlr_boot);
    console_putc('\n');
    console_write("K2 cpsr: ");
    console_write_hex32(cpu_read_cpsr());
    console_putc('\n');
    console_write("K2 frame bytes: ");
    console_write_hex32(k2_exception_frame_size);
    console_putc('\n');
    console_write("K2 frame align: ");
    console_write_hex32(k2_exception_frame_align);
    console_putc('\n');

    write_stack("svc", __svc_stack_bottom__, __svc_stack_top__);
    write_stack("und", __und_stack_bottom__, __und_stack_top__);
    write_stack("abt", __abt_stack_bottom__, __abt_stack_top__);
    write_stack("irq", __irq_stack_bottom__, __irq_stack_top__);
    write_stack("fiq", __fiq_stack_bottom__, __fiq_stack_top__);

#if MINITOS_TEST_MODE == MINITOS_TEST_UNDEF
    console_write_line("K2 test: undefined");
    k2_undef_test();

#elif MINITOS_TEST_MODE == MINITOS_TEST_DATA_ABORT
    console_write_line("K2 test: data-abort");
    k2_data_abort_test();

#else
    console_write_line("K2 test: normal");
    console_write_line("K2 IDLE");

    /*
     * No scheduler and no interrupt controller in K2. This is the deliberate
     * controlled idle state for the normal profile.
     */
    for (;;) {
        cpu_relax();
    }
#endif
}
