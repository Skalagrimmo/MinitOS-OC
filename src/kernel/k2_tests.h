#ifndef MINITOS_KERNEL_K2_TESTS_H
#define MINITOS_KERNEL_K2_TESTS_H

#include "minitos/compiler.h"

/* Fail-stop K2 fault scenarios. Each returns only if the fault did not fire. */
void k2_undef_test(void) MINITOS_NORETURN;
void k2_data_abort_test(void) MINITOS_NORETURN;

#endif /* MINITOS_KERNEL_K2_TESTS_H */
