/* Hardware-selected strlen for ordinary little-endian SRAM/Flash strings.
 * M4 uses measured DSP32, with DSP8 for the native F401 graphics Flash budget.
 * Each aligned eight-byte group is checked
 * before loading the next one; the containing group can extend past NUL.
 * Unsupported targets keep the caller's byte fallback.
 */
#ifndef MK61_MEMORY_LENGTH_ARM_H
#define MK61_MEMORY_LENGTH_ARM_H
#include <stddef.h>
#ifndef MK61_STRLEN_NAME
#define MK61_STRLEN_NAME strlen
#endif
#ifndef MK61_STRLEN_ATTRIBUTES
#define MK61_STRLEN_ATTRIBUTES
#endif
#if defined(__GNUC__) && !defined(__clang__) && defined(__ARM_ARCH_7EM__)
#define MK61_ARM_STRLEN 1
__attribute__((naked, noipa, aligned(16))) MK61_STRLEN_ATTRIBUTES
size_t MK61_STRLEN_NAME(const char* text __attribute__((unused))) {
  __asm__(
#include "strlen_m4.inc"
  );
}
#endif
#endif
