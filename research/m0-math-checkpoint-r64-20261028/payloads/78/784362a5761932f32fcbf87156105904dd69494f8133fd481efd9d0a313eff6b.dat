/* Bounded M0 memory bodies execute in Flash to preserve the large APP heap.
 * Direct entries and EABI aliases retain their existing runtime slots. */
#if defined(PICO_ON_DEVICE)
#define MK61_MEMCPY_NAME __wrap_memcpy
#include "memory_copy_arm.h"
/* EABI permits clobbering r0; retaining ISO C's destination return is harmless.
 * These are true aliases, so aligned compiler copies pay no extra branch. */
void* __wrap___aeabi_memcpy(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
void* __wrap___aeabi_memcpy4(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
void* __wrap___aeabi_memcpy8(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
#define MK61_MEMMOVE_NAME __wrap_memmove
#include "memory_move_arm.h"
void* __wrap___aeabi_memmove(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
void* __wrap___aeabi_memmove4(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
void* __wrap___aeabi_memmove8(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
#define MK61_MEMCMP_NAME __wrap_memcmp
#include "memory_compare_arm.h"
#endif
