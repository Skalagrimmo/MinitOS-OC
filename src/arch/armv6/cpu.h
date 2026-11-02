#ifndef MINITOS_ARCH_ARMV6_CPU_H
#define MINITOS_ARCH_ARMV6_CPU_H

#include <stdint.h>

#include "minitos/compiler.h"

/* Main ID Register (CP15 c0, c0, 0). */
uint32_t cpu_read_midr(void);

/* System Control Register (CP15 c1, c0, 0). */
uint32_t cpu_read_sctlr(void);
void cpu_write_sctlr(uint32_t value);

/* Instruction/data synchronisation after a CP15 control-register update. */
void cpu_sync(void);

/* Current CPSR, used to prove which mode the handler is actually running in. */
uint32_t cpu_read_cpsr(void);

/* Fault status/address registers, valid in Abort mode. */
uint32_t cpu_read_dfsr(void);
uint32_t cpu_read_dfar(void);

/* Busy-wait hint. ARM1136 has no WFE in the ARMv6 base architecture. */
static inline void cpu_relax(void)
{
    __asm__ volatile ("nop");
}

/* Deterministic terminal halt. */
static inline __attribute__((noreturn)) void cpu_halt(void)
{
    for (;;) {
        cpu_relax();
    }
}

#endif /* MINITOS_ARCH_ARMV6_CPU_H */
