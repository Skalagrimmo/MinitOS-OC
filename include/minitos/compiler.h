#ifndef MINITOS_COMPILER_H
#define MINITOS_COMPILER_H

/*
 * Compiler-facing annotations shared by the whole kernel.
 * Keeping them in one header avoids spreading GCC-specific syntax through
 * module interfaces.
 */

#define MINITOS_NORETURN __attribute__((noreturn))
#define MINITOS_UNUSED __attribute__((unused))
#define MINITOS_ALIGNED(n) __attribute__((aligned(n)))
#define MINITOS_SECTION(name) __attribute__((section(name)))
#define MINITOS_USED __attribute__((used))

#define MINITOS_COMPILER_BARRIER() __asm__ volatile ("" ::: "memory")

#endif /* MINITOS_COMPILER_H */
