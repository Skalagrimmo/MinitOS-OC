/*
 * MinitOS K1 ARMv6 entry and exception vector table.
 *
 * Contract with the loader:
 *   - ARM state, 32-bit, little-endian.
 *   - MMU and caches are off (reset state; K1 does not touch CP15 MMU/cache).
 *   - Execution starts at _start, the first word of the image.
 *   - r0-r2 may contain loader-specific values; K1 ignores them.
 *
 * _start is both the image entry point and the ARM reset vector. Entries
 * 1..7 currently trap the CPU in a visible self-loop. Real exception
 * handling is deliberately deferred, but the vector layout is already in
 * place so adding it later does not move the entry point.
 */

.syntax unified
.arch armv6
.arm

.section .vectors, "ax", %progbits
.global _start
.type _start, %function
_start:
    b   reset_handler

undefined_handler:
    b   undefined_handler

svc_handler:
    b   svc_handler

prefetch_abort_handler:
    b   prefetch_abort_handler

data_abort_handler:
    b   data_abort_handler

reserved_handler:
    b   reserved_handler

irq_handler:
    b   irq_handler

fiq_handler:
    b   fiq_handler
.size _start, . - _start

.section .text.boot, "ax", %progbits
.type reset_handler, %function
reset_handler:
    /*
     * Force Supervisor mode with IRQ and FIQ masked. QEMU already starts in
     * this state, but a bootloader on real hardware is an unknown contract;
     * do not depend on it.
     */
    mrs     r0, cpsr
    bic     r0, r0, #0x1f
    orr     r0, r0, #0xd3          /* SVC mode, I=1, F=1 */
    msr     cpsr_c, r0

    /* Private boot stack, 8-byte aligned by the linker script. */
    ldr     sp, =__stack_top__

    /* Zero .bss. The linker aligns start and end to 8 bytes. */
    ldr     r0, =__bss_start__
    ldr     r1, =__bss_end__
    mov     r2, #0
1:
    cmp     r0, r1
    strlo   r2, [r0], #4
    blo     1b

    bl      kernel_main

    /* kernel_main is noreturn; this is a defensive trap. */
2:
    b       2b

.ltorg
.size reset_handler, . - reset_handler
