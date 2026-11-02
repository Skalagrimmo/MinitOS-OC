/*
 * MinitOS K2 link layout for QEMU ARM Integrator/CP.
 *
 * This is NOT a Samsung Galaxy Gio / MSM7227 memory map.
 *
 *   0x00000000  .vectors      32 bytes, the active low-vector table
 *   0x00000020  reserved      remainder of the low 64 KiB
 *   0x00010000  .text ...     kernel image, ELF entry point
 *
 * SCTLR.V is cleared by reset_handler, so the CPU uses the table at address
 * zero. K1's table at 0x00010000 was not an active CPU vector table; it is
 * kept out of the image entirely in K2.
 *
 * QEMU loads ELF segments at their physical addresses and jumps to e_entry.
 * The reset slot at 0 and _start at 0x00010000 enter the same reset_handler.
 */

OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(_start)

MEMORY
{
    VECTORS (rx)  : ORIGIN = 0x00000000, LENGTH = 32
    RAM     (rwx) : ORIGIN = 0x00010000, LENGTH = 64K
}

__ram_base__ = 0x00000000;
__ram_end__  = 0x08000000;       /* QEMU integratorcp: 128 MiB */

__vectors_start__ = ORIGIN(VECTORS);
__vectors_end__   = ORIGIN(VECTORS) + LENGTH(VECTORS);

__svc_stack_size__ = 16K;
__und_stack_size__ = 4K;
__abt_stack_size__ = 4K;
__irq_stack_size__ = 2K;
__fiq_stack_size__ = 1K;
__stack_size__ = __svc_stack_size__;
__stack_total_size__ = __svc_stack_size__ + __und_stack_size__ +
                       __abt_stack_size__ + __irq_stack_size__ +
                       __fiq_stack_size__;

PHDRS
{
    vectors PT_LOAD FLAGS(5); /* R + X */
    text    PT_LOAD FLAGS(5); /* R + X */
    data    PT_LOAD FLAGS(6); /* R + W */
}

SECTIONS
{
    .vectors ORIGIN(VECTORS) : ALIGN(32)
    {
        KEEP(*(.vectors))
        . = ALIGN(32);
    } > VECTORS :vectors

    . = ORIGIN(RAM);

    .text : ALIGN(4)
    {
        __image_start__ = .;
        *(.text.boot)
        *(.text .text.*)
    } > RAM :text

    .rodata : ALIGN(4)
    {
        KEEP(*(.rodata.k2abi))
        *(.rodata .rodata.*)
    } > RAM :text

    .data : ALIGN(4)
    {
        *(.data .data.*)
    } > RAM :data

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start__ = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(8);
        __bss_end__ = .;
    } > RAM :data

    /*
     * Each exception mode gets a statically sized, 8-byte-aligned stack.
     * Handlers run in their exception mode on the matching stack.
     */
    .stack (NOLOAD) : ALIGN(8)
    {
        __svc_stack_bottom__ = .;
        . += __svc_stack_size__;
        __svc_stack_top__ = .;
        . = ALIGN(8);

        __und_stack_bottom__ = .;
        . += __und_stack_size__;
        __und_stack_top__ = .;
        . = ALIGN(8);

        __abt_stack_bottom__ = .;
        . += __abt_stack_size__;
        __abt_stack_top__ = .;
        . = ALIGN(8);

        __irq_stack_bottom__ = .;
        . += __irq_stack_size__;
        __irq_stack_top__ = .;
        . = ALIGN(8);

        __fiq_stack_bottom__ = .;
        . += __fiq_stack_size__;
        __fiq_stack_top__ = .;

        __stack_bottom__ = __svc_stack_bottom__;
        __stack_top__ = __svc_stack_top__;
    } > RAM :data

    __image_end__  = .;
    __image_size__ = __image_end__ - __image_start__;

    /DISCARD/ :
    {
        *(.comment)
        *(.note .note.*)
        *(.eh_frame .eh_frame.*)
        *(.ARM.exidx .ARM.exidx.*)
    }
}

ASSERT(__vectors_start__ == 0x00000000,
       "vector base must be 0x00000000")
ASSERT(__vectors_end__ == 0x00000020,
       "vector table must be exactly 32 bytes")
ASSERT(SIZEOF(.vectors) == 32,
       "vector section must be exactly 32 bytes")
ASSERT(_start == 0x00010000,
       "K2 entry point must be 0x00010000")
ASSERT(reset_handler == _start,
       "reset vector and ELF entry point must share reset_handler")
ASSERT(__image_start__ == 0x00010000,
       "kernel image must start at 0x00010000")
ASSERT(__image_start__ >= __vectors_end__,
       "kernel image must not overlap the vector table")
ASSERT(__bss_end__ <= __stack_bottom__,
       "BSS must precede the stack area")
ASSERT(__stack_top__ - __stack_bottom__ == __svc_stack_size__,
       "SVC stack size mismatch")
ASSERT(__und_stack_top__ - __und_stack_bottom__ == __und_stack_size__,
       "UND stack size mismatch")
ASSERT(__abt_stack_top__ - __abt_stack_bottom__ == __abt_stack_size__,
       "ABT stack size mismatch")
ASSERT(__irq_stack_top__ - __irq_stack_bottom__ == __irq_stack_size__,
       "IRQ stack size mismatch")
ASSERT(__fiq_stack_top__ - __fiq_stack_bottom__ == __fiq_stack_size__,
       "FIQ stack size mismatch")
ASSERT(__image_end__ == __fiq_stack_top__,
       "image must end at the top of the FIQ stack")
ASSERT(__image_size__ <= 64K,
       "K2 image (including all stacks) exceeds the 64 KiB budget")
ASSERT(__image_end__ <= __ram_end__,
       "K2 image does not fit in emulated RAM")
