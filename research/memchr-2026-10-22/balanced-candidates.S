/* One-byte exhaustion plus the original long-span alignment and pair loop. */
#define MEMCHR_BALANCED_PREFIX 1
#define pair16 balanced16
#define pair64 balanced64
#include "pair-candidates.S"
