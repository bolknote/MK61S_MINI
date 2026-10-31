/* M4-only: CB(N)Z avoids a separate compare in the bounded unrolled block. */
#if !defined(__ARM_ARCH_7EM__)
#error "DSP search candidates require ARMv7E-M"
#endif
#define MEMCHR_CBNZ 1
#define MEMCHR_FAST_PREFIX 1
#define pair16 dsp16
#define pair64 dsp32
#include "pair-candidates.S"
