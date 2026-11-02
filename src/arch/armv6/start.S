/*
 * MinitOS K2 ARMv6 reset entry and low exception vector table.
 *
 * The CPU exception table is at physical address 0x00000000 because SCTLR.V
 * is cleared below. K1's table at 0x00010000 was never the active table; the
 * kernel image itself still starts at 0x00010000, which is QEMU's ELF entry
 * point. The reset slot at 0x00 and _start at 0x00010000 both enter the same
 * reset_handler.
 *
 * Startup contract before the first C call:
 *   - ARM state, little-endian, SVC mode, IRQ and FIQ masked;
 *   - SCTLR.V=0 verified by read-back; SCTLR.A=0 and SCTLR.U=0 for a known
 *     normal-run alignment policy;
 *   - SVC/UND/ABT/IRQ/FIQ banked stack pointers set from linker symbols;
 *   - .bss cleared;
 *   - SP 8-byte aligned at the kernel_main call.
 *
 * MMU and caches are left in the QEMU reset state (off/disabled). K2 does not
 * program them.
 */

.syntax unified
.arch armv6
.arm

.section .vectors, "ax", %progbits
.global _vectors
.type _vectors, %function
_vectors:
    b   reset_handler          @ 0x00 Reset
    b   undef_entry            @ 0x04 Undefined Instruction
    b   svc_entry              @ 0x08 SVC
    b   prefetch_entry         @ 0x0c Prefetch Abort
    b   data_abort_entry       @ 0x10 Data Abort
    b   reserved_entry         @ 0x14 Reserved
    b   irq_entry              @ 0x18 IRQ
    b   fiq_entry              @ 0x1c FIQ
.size _vectors, . - _vectors

.section .text.boot, "ax", %progbits
.global _start
.global reset_handler
.type _start, %function
.type reset_handler, %function
_start:
reset_handler:
    /*
     * Refuse an unprivileged entry: User mode cannot be elevated by writing
     * CPSR. QEMU enters in SVC mode; on a different loader an explicit
     * failure is safer than a partially initialised kernel.
     */
    mrs     r0, cpsr
    and     r1, r0, #0x1f
    cmp     r1, #0x10          /* User mode */
    beq     .Lreset_fail

    /* Force ARM state, little-endian, SVC mode, IRQ/FIQ masked. */
    bic     r0, r0, #0x3f      /* clear mode bits and T */
    orr     r0, r0, #0xd3      /* SVC, I=1, F=1 */
    bic     r0, r0, #(1 << 9)  /* E=0: little-endian */
    msr     cpsr_c, r0

    /*
     * Select low vectors and a known normal alignment policy.
     * Preserve every other SCTLR bit, then verify the read-back before any
     * exception or C code can run.
     */
    mrc     p15, 0, r0, c1, c0, 0
    bic     r0, r0, #(1 << 13) /* V=0: vectors at 0x00000000 */
    bic     r0, r0, #(1 << 22) /* U=0: unaligned accesses not enabled */
    bic     r0, r0, #(1 << 1)  /* A=0: alignment faults off for normal run */
    mcr     p15, 0, r0, c1, c0, 0
    mrc     p15, 0, r0, c1, c0, 0

    tst     r0, #(1 << 13)
    bne     .Lreset_fail
    tst     r0, #(1 << 22)
    bne     .Lreset_fail
    tst     r0, #(1 << 1)
    bne     .Lreset_fail

    /* Ensure the new control state is visible to subsequent instructions. */
    mov     r0, #0
    mcr     p15, 0, r0, c7, c5, 4
    mcr     p15, 0, r0, c7, c10, 5

    /*
     * Install every banked stack pointer before a handler can be entered.
     * The MSR values explicitly keep IRQ/FIQ masked in each mode.
     */
    ldr     sp, =__svc_stack_top__
    msr     cpsr_c, #0xdb      /* UND, I=1, F=1 */
    ldr     sp, =__und_stack_top__
    msr     cpsr_c, #0xd7      /* ABT, I=1, F=1 */
    ldr     sp, =__abt_stack_top__
    msr     cpsr_c, #0xd2      /* IRQ, I=1, F=1 */
    ldr     sp, =__irq_stack_top__
    msr     cpsr_c, #0xd1      /* FIQ, I=1, F=1 */
    ldr     sp, =__fiq_stack_top__
    msr     cpsr_c, #0xd3      /* back to SVC, I=1, F=1 */
    ldr     sp, =__svc_stack_top__

    /* Zero .bss. The linker aligns start and end to 8 bytes. */
    ldr     r0, =__bss_start__
    ldr     r1, =__bss_end__
    mov     r2, #0
1:
    cmp     r0, r1
    strlo   r2, [r0], #4
    blo     1b

    /* Record the verified boot SCTLR for the C diagnostics. */
    mrc     p15, 0, r0, c1, c0, 0
    ldr     r1, =__k2_sctlr_boot
    str     r0, [r1]

    bl      kernel_main
2:
    b       2b

.Lreset_fail:
    b       .Lreset_fail

.ltorg
.size reset_handler, . - reset_handler
.size _start, . - _start
