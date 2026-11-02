#ifndef MINITOS_KERNEL_H
#define MINITOS_KERNEL_H

#include "minitos/compiler.h"

/*
 * C entry point called by reset_handler after the boot stack and BSS are
 * ready. It must never return.
 */
void kernel_main(void) MINITOS_NORETURN;

#endif /* MINITOS_KERNEL_H */
