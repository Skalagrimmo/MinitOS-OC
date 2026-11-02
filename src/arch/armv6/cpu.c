#include "arch/armv6/cpu.h"

/*
 * MIDR fields:
 *   [31:24] implementer      0x41 = ARM
 *   [23:20] variant
 *   [19:16] architecture     0x7  = ARMv6
 *   [15:4]  primary part     0xB36 = ARM1136
 *   [3:0]   revision
 *
 * K1 prints the raw value at runtime so the QEMU CPU model is observable
 * instead of being inferred from the command line.
 */
uint32_t cpu_read_midr(void)
{
    uint32_t midr;

    __asm__ volatile ("mrc p15, 0, %0, c0, c0, 0" : "=r" (midr));
    return midr;
}
