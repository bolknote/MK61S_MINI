// Directed check of log2(midpoint) against the 2^-116 lattice.
#include <inttypes.h>
#include <limits.h>
#include <mpfr.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

enum { Precision = 192, LatticeBits = 116, FractionBits = 60 };
_Static_assert(ULONG_MAX >= UINT64_MAX, "Use a 64-bit Unix host for this certificate");
_Static_assert(Precision > LatticeBits + FractionBits, "Need less than one fractional unit");

int main(int argc, char **argv) {
    if (argc != 4 || (argv[1][0] != '-' && argv[1][0] != '+') || argv[1][1])
        return 2;
    const int below = argv[1][0] == '-';
    const uint64_t first = strtoull(argv[2], NULL, 10), stop = strtoull(argv[3], NULL, 10);
    const unsigned denominator = below ? 54 : 53;
    const uint64_t unit = UINT64_C(1) << FractionBits;
    if (first >= stop || stop > (UINT64_C(1) << (denominator - 3)))
        return 2;

    mpfr_t midpoint, logarithm;
    mpfr_inits2(Precision, midpoint, logarithm, (mpfr_ptr) NULL);
    uint64_t minimum = unit, closest = first;
    for (uint64_t index = first; index < stop; ++index) {
        const uint64_t one = UINT64_C(1) << denominator, delta = 2*index + 1;
        mpfr_set_ui(midpoint, below ? one - delta : one + delta, MPFR_RNDN);
        mpfr_div_2ui(midpoint, midpoint, denominator, MPFR_RNDN);
        mpfr_log2(logarithm, midpoint, below ? MPFR_RNDU : MPFR_RNDD);
        if (below)
            mpfr_neg(logarithm, logarithm, MPFR_RNDN);
        // |log2(midpoint)| < 1. Downward rounding loses at most 2^-192.
        // Scaling and taking the fractional part of this dyadic is exact.
        mpfr_mul_2ui(logarithm, logarithm, LatticeBits, MPFR_RNDN);
        mpfr_frac(logarithm, logarithm, MPFR_RNDN);
        mpfr_mul_2ui(logarithm, logarithm, FractionBits, MPFR_RNDN);
        const uint64_t low = mpfr_get_ui(logarithm, MPFR_RNDD);
        // Less than one unit from mpfr_get_ui and less than one from log2.
        const uint64_t upper_gap = low < unit - 2 ? unit - low - 2 : 0;
        const uint64_t gap = low < upper_gap ? low : upper_gap;
        if (gap < minimum) {
            minimum = gap;
            closest = index;
        }
    }
    mpfr_clears(midpoint, logarithm, (mpfr_ptr) NULL);
    printf("%s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
           mpfr_get_version(), first, stop, minimum, closest);
    return 0;
}
