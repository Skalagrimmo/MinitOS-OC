#ifndef MINITOS_EXCEPTION_H
#define MINITOS_EXCEPTION_H

#include <stddef.h>
#include <stdint.h>

#include "minitos/compiler.h"

/*
 * K2 exception frame.
 *
 * The assembly entry stubs build this structure on the banked stack of the
 * mode the CPU entered. The field order and offsets are part of the
 * assembly/C ABI and must not be changed without changing exception.S.
 *
 * The frame is 18 words (72 bytes) and is 8-byte aligned. The size being a
 * multiple of 8 keeps the banked SP 8-byte aligned at the C call boundary.
 */
struct exception_frame {
    uint32_t r0;
    uint32_t r1;
    uint32_t r2;
    uint32_t r3;
    uint32_t r4;
    uint32_t r5;
    uint32_t r6;
    uint32_t r7;
    uint32_t r8;
    uint32_t r9;
    uint32_t r10;
    uint32_t r11;
    uint32_t r12;
    uint32_t lr;     /* banked LR of the exception mode */
    uint32_t spsr;   /* CPSR of the interrupted context */
    uint32_t vector; /* vector byte offset: 0x04, 0x10, ... */
    uint32_t dfsr;   /* Data Abort only, otherwise 0 */
    uint32_t dfar;   /* Data Abort only, otherwise 0 */
} MINITOS_ALIGNED(8);

_Static_assert(sizeof(struct exception_frame) == 72,
               "exception frame must be exactly 18 words");
_Static_assert(_Alignof(struct exception_frame) == 8,
               "exception frame must be 8-byte aligned");
_Static_assert(sizeof(struct exception_frame) % 8 == 0,
               "exception frame size must preserve 8-byte stack alignment");

_Static_assert(offsetof(struct exception_frame, r0) == 0,
               "exception frame r0 offset changed");
_Static_assert(offsetof(struct exception_frame, r12) == 48,
               "exception frame r12 offset changed");
_Static_assert(offsetof(struct exception_frame, lr) == 52,
               "exception frame lr offset changed");
_Static_assert(offsetof(struct exception_frame, spsr) == 56,
               "exception frame spsr offset changed");
_Static_assert(offsetof(struct exception_frame, vector) == 60,
               "exception frame vector offset changed");
_Static_assert(offsetof(struct exception_frame, dfsr) == 64,
               "exception frame dfsr offset changed");
_Static_assert(offsetof(struct exception_frame, dfar) == 68,
               "exception frame dfar offset changed");

/* Called from the UND and ABT assembly stubs; never returns. */
void exception_dispatch(const struct exception_frame *frame) MINITOS_NORETURN;

/* Called from the SVC/prefetch/reserved/IRQ/FIQ stubs; never returns. */
void exception_unexpected(const struct exception_frame *frame) MINITOS_NORETURN;

#endif /* MINITOS_EXCEPTION_H */
