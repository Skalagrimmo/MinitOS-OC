#include "drivers/pl011.h"
#include "minitos/io.h"

/* PL011 register offsets (ARM PrimeCell UART, 32-bit registers). */
#define PL011_DR    0x000u /* Data register                    */
#define PL011_FR    0x018u /* Flag register                    */
#define PL011_IBRD  0x024u /* Integer baud rate divisor        */
#define PL011_FBRD  0x028u /* Fractional baud rate divisor     */
#define PL011_LCR_H 0x02Cu /* Line control register            */
#define PL011_CR    0x030u /* Control register                 */
#define PL011_IFLS  0x034u /* Interrupt FIFO level select      */
#define PL011_IMSC  0x038u /* Interrupt mask set/clear         */
#define PL011_ICR   0x044u /* Interrupt clear register         */

/* Flag register bits. */
#define PL011_FR_TXFF (1u << 5) /* Transmit FIFO full */

/* Line control bits: 8 data bits, FIFO enable. */
#define PL011_LCR_WLEN_8 (3u << 5)
#define PL011_LCR_FEN    (1u << 4)

/* Control register bits. */
#define PL011_CR_UARTEN (1u << 0)
#define PL011_CR_TXE    (1u << 8)
#define PL011_CR_RXE    (1u << 9)

void pl011_init(struct pl011 *uart, uintptr_t base, uint16_t ibrd, uint8_t fbrd)
{
    uart->base = base;
    uart->ibrd = ibrd;
    uart->fbrd = fbrd;

    /* Disable the UART while its configuration is changed. */
    mmio_write32(base + PL011_CR, 0);

    /* Clear any pending interrupt state; K1 does not use UART interrupts. */
    mmio_write32(base + PL011_ICR, 0x7FFu);

    mmio_write32(base + PL011_IBRD, (uint32_t)ibrd);
    mmio_write32(base + PL011_FBRD, (uint32_t)fbrd & 0x3Fu);

    mmio_write32(base + PL011_LCR_H, PL011_LCR_FEN | PL011_LCR_WLEN_8);

    /* Trigger at 1/8 FIFO level; irrelevant while IMSC is zero. */
    mmio_write32(base + PL011_IFLS, 0);
    mmio_write32(base + PL011_IMSC, 0);

    mmio_write32(base + PL011_CR,
                 PL011_CR_UARTEN | PL011_CR_TXE | PL011_CR_RXE);
}

void pl011_write_byte(struct pl011 *uart, uint8_t byte)
{
    /*
     * Polled transmit. On QEMU this loop is effectively a single test.
     * On real hardware it provides back-pressure instead of dropping bytes.
     * K1 deliberately has no timeout: a missing UART must be a visible hang,
     * not silent data loss, while the platform is being brought up.
     */
    while ((mmio_read32(uart->base + PL011_FR) & PL011_FR_TXFF) != 0) {
        /* wait for TX FIFO space */
    }

    mmio_write32(uart->base + PL011_DR, (uint32_t)byte);
}
