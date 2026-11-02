#ifndef MINITOS_IO_H
#define MINITOS_IO_H

#include <stdint.h>

/*
 * 32-bit memory-mapped I/O accessors.
 *
 * K2 runs with the MMU off, so these addresses are physical. The volatile
 * qualifier prevents the compiler from merging or deleting device accesses.
 * No extra barrier is required for the single-core, non-DMA, interrupt-free
 * K2 execution model; this assumption is recorded in the documentation.
 */

static inline uint32_t mmio_read32(uintptr_t address)
{
    return *(const volatile uint32_t *)address;
}

static inline void mmio_write32(uintptr_t address, uint32_t value)
{
    *(volatile uint32_t *)address = value;
}

#endif /* MINITOS_IO_H */
