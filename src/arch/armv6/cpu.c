#include "arch/armv6/cpu.h"

/*
 * Written by reset_handler after the low-vector read-back and before the C
 * entry point. It lives in .bss so the normal BSS clear is already complete.
 */
uint32_t __k2_sctlr_boot;

/*
 * MIDR fields:
 *   [31:24] implementer      0x41 = ARM
 *   [23:20] variant
 *   [19:16] architecture     0x7  = ARMv6
 *   [15:4]  primary part     0xB36 = ARM1136
 *   [3:0]   revision
 *
 * K2 prints the raw value at runtime so the QEMU CPU model is observable
 * instead of being inferred from the command line.
 */
uint32_t cpu_read_midr(void)
{
    uint32_t midr;

    __asm__ volatile ("mrc p15, 0, %0, c0, c0, 0" : "=r" (midr));
    return midr;
}

/*
 * SCTLR is used for two K2 facts only:
 *   - bit 13 (V) selects low vectors (0) or high vectors at 0xFFFF0000 (1);
 *   - bits 22 (U) and 1 (A) control unaligned-access/alignment-fault policy.
 *
 * The startup code performs the initial read-modify-write and verifies V=0
 * before any C code runs. These helpers are used for later diagnostics and
 * for the Data Abort test.
 */
uint32_t cpu_read_sctlr(void)
{
    uint32_t value;

    __asm__ volatile ("mrc p15, 0, %0, c1, c0, 0" : "=r" (value) : : "memory");
    return value;
}

void cpu_write_sctlr(uint32_t value)
{
    __asm__ volatile ("mcr p15, 0, %0, c1, c0, 0" : : "r" (value) : "memory");
}

void cpu_sync(void)
{
    /*
     * ARM1136 TRM: after changing CP15 control state, drain the write buffer
     * and flush the prefetch pipeline before relying on the new behaviour.
     * ARMv6 has no named ISB/DSB instructions; these CP15 operations are the
     * architectural equivalents used by the ARM1136.
     */
    __asm__ volatile ("mcr p15, 0, %0, c7, c5, 4" : : "r" (0u) : "memory");
    __asm__ volatile ("mcr p15, 0, %0, c7, c10, 5" : : "r" (0u) : "memory");
}

uint32_t cpu_read_cpsr(void)
{
    uint32_t value;

    __asm__ volatile ("mrs %0, cpsr" : "=r" (value));
    return value;
}

uint32_t cpu_read_dfsr(void)
{
    uint32_t value;

    __asm__ volatile ("mrc p15, 0, %0, c5, c0, 0" : "=r" (value) : : "memory");
    return value;
}

uint32_t cpu_read_dfar(void)
{
    uint32_t value;

    __asm__ volatile ("mrc p15, 0, %0, c6, c0, 0" : "=r" (value) : : "memory");
    return value;
}
