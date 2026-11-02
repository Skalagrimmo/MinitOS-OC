#ifndef MINITOS_ARCH_ARMV6_CPU_H
#define MINITOS_ARCH_ARMV6_CPU_H

#include <stdint.h>

/* Main ID Register (CP15 c0, c0, 0). */
uint32_t cpu_read_midr(void);

/* Busy-wait hint. ARM1136 has no WFE in the ARMv6 base architecture. */
static inline void cpu_relax(void)
{
    __asm__ volatile ("nop");
}

#endif /* MINITOS_ARCH_ARMV6_CPU_H */
