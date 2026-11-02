/*
 * MinitOS K2 exception entry stubs and fault generators.
 *
 * Each diagnostic stub runs in the mode the CPU entered, on that mode's
 * banked stack. It constructs struct exception_frame exactly as declared in
 * include/minitos/exception.h and calls C while the stack is 8-byte aligned.
 *
 * The frame layout is an assembly/C ABI and is duplicated here deliberately:
 * the C side enforces the same size and offsets with static assertions.
 */

.syntax unified
.arch armv6
.arm

.equ FRAME_LR,     52
.equ FRAME_SPSR,   56
.equ FRAME_VECTOR, 60
.equ FRAME_DFSR,   64
.equ FRAME_DFAR,   68
.equ FRAME_SIZE,   72

/*
 * Save r0-r12, the banked LR and SPSR, the vector offset and (for Abort
 * mode) DFSR/DFAR. The caller's SP is already 8-byte aligned, and 72 is a
 * multiple of 8, so the C call boundary remains 8-byte aligned.
 */
.macro SAVE_FRAME vector_offset, is_abort=0
    cpsid   if
    sub     sp, sp, #FRAME_SIZE
    stmia   sp, {r0-r12}
    str     lr, [sp, #FRAME_LR]
    mrs     r0, spsr
    str     r0, [sp, #FRAME_SPSR]
    mov     r0, #\vector_offset
    str     r0, [sp, #FRAME_VECTOR]
    .if \is_abort
        mrc p15, 0, r0, c5, c0, 0
        str r0, [sp, #FRAME_DFSR]
        mrc p15, 0, r0, c6, c0, 0
        str r0, [sp, #FRAME_DFAR]
    .else
        mov r0, #0
        str r0, [sp, #FRAME_DFSR]
        str r0, [sp, #FRAME_DFAR]
    .endif
    mov     r0, sp
.endm

.section .text.exception, "ax", %progbits

/* 0x04: Undefined Instruction. */
.global undef_entry
.type undef_entry, %function
undef_entry:
    SAVE_FRAME 4, 0
    bl      exception_dispatch
1:
    b       1b
.size undef_entry, . - undef_entry

/* 0x10: Data Abort. DFSR/DFAR are valid in Abort mode. */
.global data_abort_entry
.type data_abort_entry, %function
data_abort_entry:
    SAVE_FRAME 16, 1
    bl      exception_dispatch
1:
    b       1b
.size data_abort_entry, . - data_abort_entry

/*
 * Unexpected but defined exception entries. K2 does not implement recovery;
 * these paths identify the vector and stop deterministically rather than
 * executing undefined memory.
 */
.macro UNEXPECTED_ENTRY name, vector_offset
.global \name
.type \name, %function
\name:
    SAVE_FRAME \vector_offset, 0
    bl      exception_unexpected
1:
    b       1b
.size \name, . - \name
.endm

UNEXPECTED_ENTRY svc_entry,        8
UNEXPECTED_ENTRY prefetch_entry,   12
UNEXPECTED_ENTRY irq_entry,        24
UNEXPECTED_ENTRY fiq_entry,        28

/*
 * 0x14: reserved vector. ARM1136 does not generate it. It is a documented
 * fail-stop stub with no stack or device access, so even an unexpected entry
 * cannot corrupt state.
 */
.global reserved_entry
.type reserved_entry, %function
reserved_entry:
    b       reserved_entry
.size reserved_entry, . - reserved_entry

/*
 * K2 fault generators. These are real instructions, not calls to a fake
 * handler. They are assembled in a separate section so --gc-sections can
 * drop them from profiles that do not use them.
 */
.section .text.k2test, "ax", %progbits

.global k2_trigger_undef
.type k2_trigger_undef, %function
k2_trigger_undef:
    ldr     r0, =0x4b2d0001
    ldr     r1, =0x4b2d0002
    ldr     r12, =0x4b2d000c
    udf     #0
    bx      lr
.size k2_trigger_undef, . - k2_trigger_undef
.ltorg

/*
 * The probe array is 16-byte aligned. Adding one produces an address that is
 * guaranteed not to be word aligned; the following LDR is a real unaligned
 * word access, not a byte-load sequence.
 */
.global k2_trigger_data_abort
.type k2_trigger_data_abort, %function
k2_trigger_data_abort:
    ldr     r0, =k2_alignment_probe
    ldr     r1, =0x4b2d0002
    ldr     r2, =0x4b2d0003
    ldr     r12, =0x4b2d000c
    add     r0, r0, #1
    ldr     r1, [r0]
    bx      lr
.size k2_trigger_data_abort, . - k2_trigger_data_abort
.ltorg

.section .data.k2test, "aw", %progbits
.balign 16
.global k2_alignment_probe
.type k2_alignment_probe, %object
k2_alignment_probe:
    .word   0x11223344
    .word   0x55667788
    .word   0x99aabbcc
    .word   0xddeeff00
.size k2_alignment_probe, . - k2_alignment_probe
