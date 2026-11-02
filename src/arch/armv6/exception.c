#include "minitos/exception.h"

#include "arch/armv6/cpu.h"
#include "kernel/console.h"

/*
 * Kept in a dedicated .rodata subsection so the ELF checker can verify the
 * compiled ABI values as well as the static assertions in exception.h.
 */
const uint32_t k2_exception_frame_size
    MINITOS_SECTION(".rodata.k2abi") MINITOS_USED =
        (uint32_t)sizeof(struct exception_frame);
const uint32_t k2_exception_frame_align
    MINITOS_SECTION(".rodata.k2abi") MINITOS_USED =
        (uint32_t)_Alignof(struct exception_frame);

static const char *mode_name(uint32_t cpsr)
{
    switch (cpsr & 0x1Fu) {
    case 0x10u: return "USR";
    case 0x11u: return "FIQ";
    case 0x12u: return "IRQ";
    case 0x13u: return "SVC";
    case 0x17u: return "ABT";
    case 0x1Bu: return "UND";
    case 0x1Fu: return "SYS";
    default:    return "UNKNOWN";
    }
}

static void write_hex_field(const char *label, uint32_t value)
{
    console_write(label);
    console_write_hex32(value);
    console_putc('\n');
}

static void write_common_fields(const struct exception_frame *frame)
{
    uint32_t cpsr = cpu_read_cpsr();

    write_hex_field("vector: ", frame->vector);
    console_write("mode: ");
    console_write_line(mode_name(cpsr));
    write_hex_field("handler_cpsr: ", cpsr);
    write_hex_field("lr: ", frame->lr);
    write_hex_field("spsr: ", frame->spsr);
    console_write("spsr_mode: ");
    console_write_line(mode_name(frame->spsr));
}

static void write_sentinel_registers(const struct exception_frame *frame)
{
    write_hex_field("r0: ", frame->r0);
    write_hex_field("r1: ", frame->r1);
    write_hex_field("r2: ", frame->r2);
    write_hex_field("r12: ", frame->r12);
}

void exception_dispatch(const struct exception_frame *frame)
{
    if (frame->vector == 4u) {
        console_write_line("EXCEPTION: UNDEFINED INSTRUCTION");
        write_common_fields(frame);
        /* ARM1136 stores LR_und = faulting instruction + 4. */
        write_hex_field("fault_pc: ", frame->lr - 4u);
        write_sentinel_registers(frame);
    } else if (frame->vector == 16u) {
        console_write_line("EXCEPTION: DATA ABORT");
        write_common_fields(frame);
        write_hex_field("dfsr: ", frame->dfsr);
        write_hex_field("dfar: ", frame->dfar);
        /* ARM1136 stores LR_abt = faulting instruction + 8. */
        write_hex_field("fault_pc: ", frame->lr - 8u);
        write_sentinel_registers(frame);
    } else {
        exception_unexpected(frame);
    }

    console_write_line("K2 EXCEPTION CAPTURED");
    cpu_halt();
}

void exception_unexpected(const struct exception_frame *frame)
{
    const char *name;

    switch (frame->vector) {
    case 8u:  name = "SVC"; break;
    case 12u: name = "PREFETCH ABORT"; break;
    case 20u: name = "RESERVED"; break;
    case 24u: name = "IRQ"; break;
    case 28u: name = "FIQ"; break;
    default:  name = "UNKNOWN"; break;
    }

    console_write("EXCEPTION: UNEXPECTED ");
    console_write_line(name);
    write_common_fields(frame);
    write_hex_field("r0: ", frame->r0);
    write_hex_field("r12: ", frame->r12);
    console_write_line("K2 EXCEPTION CAPTURED");
    cpu_halt();
}
