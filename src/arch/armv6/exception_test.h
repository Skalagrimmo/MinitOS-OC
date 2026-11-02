#ifndef MINITOS_ARCH_ARMV6_EXCEPTION_TEST_H
#define MINITOS_ARCH_ARMV6_EXCEPTION_TEST_H

#include <stdint.h>

/*
 * Deliberate fault generators used only by the K2 test profiles.
 *
 * k2_trigger_undef executes a real ARM-state UDF instruction. It clobbers
 * r0, r1 and r12 with sentinels so the handler frame can be checked.
 *
 * k2_trigger_data_abort performs a real unaligned word LDR from the
 * 16-byte-aligned k2_alignment_probe array. It requires SCTLR.A=1 and
 * SCTLR.U=1; k2_data_abort_test() programs those bits before calling it.
 */
extern volatile uint32_t k2_alignment_probe[4];

void k2_trigger_undef(void);
void k2_trigger_data_abort(void);

#endif /* MINITOS_ARCH_ARMV6_EXCEPTION_TEST_H */
