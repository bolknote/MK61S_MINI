/* Pair variant with a common one-byte exhaustion path, for physical timing. */
#define MEMCHR_FAST_PREFIX 1
#define pair16 fast16
#define pair64 fast64
#include "pair-candidates.S"
