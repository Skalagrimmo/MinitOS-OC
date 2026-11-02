/*
 * MinitOS K1 link layout for QEMU ARM Integrator/CP.
 *
 * This is NOT a Samsung Galaxy Gio / MSM7227 memory map. The load address
 * 0x00010000 is a deliberate QEMU reference layout: it leaves the first
 * 64 KiB of emulated RAM free for future boot data / low vectors and keeps
 * the image well away from address 0, where the Gio boot chain is unknown.
 *
 * QEMU loads ELF segments at their physical addresses and jumps to e_entry,
 * so no bootloader stub is involved (see docs/PLATFORM_INTEGRATORCP.md).
 */

OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x00010000, LENGTH = 128M
}

__ram_base__  = ORIGIN(RAM);
__ram_end__   = ORIGIN(RAM) + LENGTH(RAM);
__stack_size__ = 16K;

PHDRS
{
    text PT_LOAD FLAGS(5); /* R + X */
    data PT_LOAD FLAGS(6); /* R + W */
}

SECTIONS
{
    . = ORIGIN(RAM);

    .vectors : ALIGN(32)
    {
        __image_start__ = .;
        KEEP(*(.vectors))
    } > RAM :text

    .text : ALIGN(4)
    {
        *(.text.boot)
        *(.text .text.*)
    } > RAM :text

    .rodata : ALIGN(4)
    {
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

    .stack (NOLOAD) : ALIGN(8)
    {
        __stack_bottom__ = .;
        . += __stack_size__;
        __stack_top__ = .;
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

ASSERT(_start == __image_start__,
       "K1 entry point must be the first word of the image")
ASSERT(__image_end__ <= __ram_end__,
       "K1 image does not fit in RAM")
ASSERT(__stack_top__ - __stack_bottom__ == __stack_size__,
       "K1 stack size mismatch")
ASSERT(__image_size__ <= 64K,
       "K1 image (including stack) exceeds the 64 KiB budget")
