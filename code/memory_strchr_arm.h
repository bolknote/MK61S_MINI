/* Hardware-selected strchr for ordinary little-endian SRAM/Flash strings.
 * M0+ uses ordered byte reads, unrolled four at a time, and stops exactly at
 * the first match or NUL. The 58-byte body was measured on RP2040/PicoCalc.
 * On M4 the first sixteen bytes use ordered byte reads; the DSP tail reads only
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
#ifndef MK61_STRCHR_ATTRIBUTES
#define MK61_STRCHR_ATTRIBUTES
#endif
#if defined(__GNUC__) && !defined(__clang__) && \
    defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
#if defined(__ARM_ARCH_7EM__)
#define MK61_ARM_STRCHR 1
#if defined(MK61_STRCHR_M4_COMPACT) && MK61_STRCHR_M4_COMPACT
#define MK61_STRCHR_ALIGNMENT 2
#else
#define MK61_STRCHR_ALIGNMENT 16
#endif
__attribute__((naked, noipa, aligned(MK61_STRCHR_ALIGNMENT)))
MK61_STRCHR_ATTRIBUTES
char* MK61_STRCHR_NAME(const char* text __attribute__((unused)),
                      int character __attribute__((unused))) {
  __asm__(
#include "strchr_m4.inc"
  );
}
#undef MK61_STRCHR_ALIGNMENT
#elif defined(__ARM_ARCH_6M__)
#define MK61_ARM_STRCHR 1
__attribute__((naked, noipa, aligned(4)))
MK61_STRCHR_ATTRIBUTES
char* MK61_STRCHR_NAME(const char* text __attribute__((unused)),
                      int character __attribute__((unused))) {
  __asm__(
#include "strchr_m0.inc"
  );
}
#endif
#endif
#endif
