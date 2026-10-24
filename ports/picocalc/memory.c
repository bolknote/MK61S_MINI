/* Speed-selected memcpy/memmove/memchr live in SRAM, like standalone APPs.
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
#define MK61_MEMMOVE_NAME __wrap_memmove
#define MK61_MEMMOVE_ATTRIBUTES __attribute__((section(".time_critical.memmove")))
#include "memory_move_arm.h"
void* __wrap___aeabi_memmove(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
void* __wrap___aeabi_memmove4(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
void* __wrap___aeabi_memmove8(void*,const void*,size_t) __attribute__((alias("__wrap_memmove")));
#define MK61_MEMCHR_NAME __wrap_memchr
#define MK61_MEMCHR_ATTRIBUTES __attribute__((section(".time_critical.memchr")))
#include "memory_search_arm.h"
#endif
