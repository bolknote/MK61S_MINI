// Screen binary64 pow pairs for a midpoint within the production log-side gap.
// Input: hexadecimal encodings of x and y. Output: surviving x, y, lower encodings.
#include <inttypes.h>
#include <limits.h>
#include <mpfr.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { Precision = 224, GapBits = 16300 };
static const uint64_t Infinity = UINT64_C(0x7ff0000000000000);
static const uint64_t One = UINT64_C(0x3ff0000000000000);
static const uint64_t Abs = UINT64_C(0x7fffffffffffffff);
static const uint64_t Fraction = (UINT64_C(1) << 52)-1;
_Static_assert(ULONG_MAX >= UINT64_MAX, "Use a 64-bit Unix host");
_Static_assert(sizeof(double) == sizeof(uint64_t), "Use IEEE binary64 doubles");

static double real(uint64_t bits) {
    double value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static uint64_t encoding(double value) {
    uint64_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void midpoint(mpfr_t out, uint64_t lower) {
    const unsigned field = (unsigned)(lower >> 52);
    const uint64_t significand = (lower & Fraction)+(field ? UINT64_C(1) << 52 : 0);
    // At overflow the virtual upper neighbor is 2^1024. The same
    // upward spacing formula still gives its midpoint with max finite.
    mpfr_set_ui_2exp(out, 2*significand+1, (field ? (int)field : 1)-1076, MPFR_RNDN);
}

static void power_log(mpfr_t low, mpfr_t high, mpfr_srcptr x, mpfr_srcptr y) {
    mpfr_log(low, x, MPFR_RNDD);
    mpfr_log(high, x, MPFR_RNDU);
    if (mpfr_sgn(y) < 0)
        mpfr_swap(low, high);
    mpfr_mul(low, low, y, MPFR_RNDD);
    mpfr_mul(high, high, y, MPFR_RNDU);
}

int main(void) {
    mpfr_t x, y, low, high, m, xlog_lo, xlog_hi, gap, closest, difference;
    mpfr_inits2(Precision, x, y, low, high, m, xlog_lo, xlog_hi, gap, closest,
                difference, (mpfr_ptr)NULL);
    mpfr_set_ui_2exp(gap, 1, -GapBits, MPFR_RNDN);
    mpfr_set_inf(closest, 1);
    uint64_t xb, yb, count = 0, active = 0, compared = 0, remaining = 0;
    uint64_t closest_x = 0, closest_y = 0, closest_lower = 0;
    int read;
    while ((read = scanf("%" SCNx64 " %" SCNx64, &xb, &yb)) == 2) {
        ++count;
        const uint64_t magnitude = yb & Abs;
        xb &= Abs;
        // The production front end resolves all these cases earlier. For
        // a negative base which does enter rescue, it uses this magnitude.
        if (!xb || xb == One || xb >= Infinity || magnitude < UINT64_C(0x3bf0000000000000)
            || magnitude >= UINT64_C(0x43e0000000000000))
            continue;
        ++active;
        mpfr_set_d(x, real(xb), MPFR_RNDN);
        mpfr_set_d(y, real(yb), MPFR_RNDN);
        mpfr_pow(low, x, y, MPFR_RNDD);
        mpfr_pow(high, x, y, MPFR_RNDU);
        const uint64_t first = encoding(mpfr_get_d(low, MPFR_RNDD));
        const uint64_t last = encoding(mpfr_get_d(high, MPFR_RNDU));
        if (first > last || last > Infinity || last-first > 2) {
            fprintf(stderr, "Unexpected output enclosure for %016" PRIx64 " %016" PRIx64 "\n", xb, yb);
            return 1;
        }

        // All other midpoints are at least one full midpoint spacing
        // from the exact power. Keep the outer neighbor at either end.
        const uint64_t start = first ? first-1 : 0;
        const uint64_t stop = last < Infinity ? last+1 : Infinity;
        power_log(xlog_lo, xlog_hi, x, y);
        for (uint64_t lower = start; lower < stop; ++lower) {
            ++compared;
            midpoint(m, lower);
            mpfr_log(high, m, MPFR_RNDU);
            mpfr_sub(difference, xlog_lo, high, MPFR_RNDD);
            if (mpfr_cmp(difference, gap) <= 0) {
                mpfr_log(low, m, MPFR_RNDD);
                mpfr_sub(difference, low, xlog_hi, MPFR_RNDD);
            }
            if (mpfr_cmp(difference, gap) <= 0) {
                ++remaining;
                printf("%016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n", xb, yb, lower);
            } else if (mpfr_cmp(difference, closest) < 0) {
                mpfr_set(closest, difference, MPFR_RNDN);
                closest_x = xb;
                closest_y = yb;
                closest_lower = lower;
            }
        }
    }
    if (read != EOF || ferror(stdin) || !count || mpfr_inf_p(closest))
        return 1;
    fprintf(stderr, "MPFR %s, %" PRIu64 " pairs, %" PRIu64 " active, %" PRIu64
            " midpoint comparisons, %" PRIu64 " intervals include the gap\n",
            mpfr_get_version(), count, active, compared, remaining);
    fprintf(stderr, "Minimum separated gap >= 2^%ld at %016" PRIx64 " %016" PRIx64
            " %016" PRIx64 "\n", (long)mpfr_get_exp(closest)-1, closest_x, closest_y, closest_lower);
    mpfr_clears(x, y, low, high, m, xlog_lo, xlog_hi, gap, closest, difference, (mpfr_ptr)NULL);
    return 0;
}
