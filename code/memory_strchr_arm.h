/* M4 strchr for ordinary little-endian SRAM/Flash strings.
 * The first sixteen bytes use ordered byte reads; the DSP tail reads only
 * aligned containing words, never before the supplied pointer. The final
 * word may include up to three bytes past the first match or NUL.
 * F401 graphics can select the 18-byte byte loop for the Flash budget.
 * Other targets keep the caller's portable fallback.
 */
#ifndef MK61_MEMORY_STRCHR_ARM_H
#define MK61_MEMORY_STRCHR_ARM_H
#ifndef MK61_STRCHR_NAME
#define MK61_STRCHR_NAME strchr
#endif
#if defined(__GNUC__) && !defined(__clang__) && defined(__ARM_ARCH_7EM__) && \
    defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
#define MK61_ARM_STRCHR 1
#if defined(MK61_STRCHR_M4_COMPACT) && MK61_STRCHR_M4_COMPACT
#define MK61_STRCHR_ALIGNMENT 2
#else
#define MK61_STRCHR_ALIGNMENT 16
#endif
__attribute__((naked, noipa, aligned(MK61_STRCHR_ALIGNMENT)))
char* MK61_STRCHR_NAME(const char* text __attribute__((unused)),
                      int character __attribute__((unused))) {
  __asm__(
#include "strchr_m4.inc"
  );
}
#undef MK61_STRCHR_ALIGNMENT
#endif
#endif
