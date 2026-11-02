#ifndef MINITOS_TEST_PROFILE_H
#define MINITOS_TEST_PROFILE_H

/*
 * K2 build profiles.
 *
 * The exception handlers are fail-stop, so each fault scenario needs its own
 * image and its own QEMU process. The build driver passes exactly one of
 * these values as -DMINITOS_TEST_MODE=<n>.
 */

#define MINITOS_TEST_NORMAL      0
#define MINITOS_TEST_UNDEF       1
#define MINITOS_TEST_DATA_ABORT  2

#ifndef MINITOS_TEST_MODE
#define MINITOS_TEST_MODE MINITOS_TEST_NORMAL
#endif

#if (MINITOS_TEST_MODE != MINITOS_TEST_NORMAL) && \
    (MINITOS_TEST_MODE != MINITOS_TEST_UNDEF) && \
    (MINITOS_TEST_MODE != MINITOS_TEST_DATA_ABORT)
#error "unknown MINITOS_TEST_MODE"
#endif

#endif /* MINITOS_TEST_PROFILE_H */
