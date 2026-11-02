#include "kernel/k2_tests.h"

#include <stdint.h>

#include "arch/armv6/cpu.h"
#include "arch/armv6/exception_test.h"
#include "kernel/console.h"

#define SCTLR_A (1u << 1)   /* alignment fault enable */
#define SCTLR_U (1u << 22)  /* unaligned access enable */

static void test_failed(const char *reason) MINITOS_NORETURN;

static void test_failed(const char *reason)
{
    console_write("K2 TEST FAILED: ");
    console_write_line(reason);
    cpu_halt();
}

void k2_undef_test(void)
{
    /*
     * k2_trigger_undef executes UDF. If execution reaches the next line the
     * CPU did not take the Undefined Instruction exception, so this is a
     * visible failure rather than a false PASS.
     */
    k2_trigger_undef();
    test_failed("undefined instruction did not trap");
}

void k2_data_abort_test(void)
{
    uint32_t before = cpu_read_sctlr();
    uint32_t wanted = before | SCTLR_A | SCTLR_U;
    uint32_t observed;

    cpu_write_sctlr(wanted);
    cpu_sync();
    observed = cpu_read_sctlr();

    console_write("K2 sctlr before: ");
    console_write_hex32(before);
    console_putc('\n');
    console_write("K2 sctlr after: ");
    console_write_hex32(observed);
    console_putc('\n');
    console_write("K2 alignment probe: ");
    console_write_hex32((uint32_t)(uintptr_t)k2_alignment_probe);
    console_putc('\n');

    if ((observed & (SCTLR_A | SCTLR_U)) != (SCTLR_A | SCTLR_U)) {
        test_failed("SCTLR A/U read-back mismatch");
    }

    /*
     * The next call performs a real unaligned word LDR from
     * k2_alignment_probe + 1 while A=1. If it returns, no Data Abort was
     * taken and the profile must fail.
     */
    k2_trigger_data_abort();
    test_failed("unaligned word load did not abort");
}
