/* Speed-selected memcpy lives in SRAM, like the standalone APP implementation.
 * No BootROM lookup or Flash trampoline is needed on each call. */
#if defined(PICO_ON_DEVICE)
#define MK61_MEMCPY_NAME __wrap_memcpy
#define MK61_MEMCPY_ATTRIBUTES __attribute__((section(".time_critical.memcpy")))
#include "memory_copy_arm.h"
/* EABI permits clobbering r0; retaining ISO C's destination return is harmless.
 * These are true aliases, so aligned compiler copies pay no extra branch. */
void* __wrap___aeabi_memcpy(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
void* __wrap___aeabi_memcpy4(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
void* __wrap___aeabi_memcpy8(void*,const void*,size_t) __attribute__((alias("__wrap_memcpy")));
#endif
