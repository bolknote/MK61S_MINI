// Check a diagonal in the pow chart e=1022, f=1023 by monotone inversion.
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <mpfr.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

_Static_assert(ULONG_MAX >= UINT64_MAX, "a 64-bit host is required");
static const uint64_t Q = UINT64_C(1) << 52;
enum { E = 1022, PRECISION = 192, GAP = 128 };

typedef struct {
    mpfr_t ln2_lo, ln2_hi, center_lo, center_hi, lo, hi, arg, term, guard;
    uint64_t d, r;
} Check;

static void exponent(Check *s, uint64_t r) {
    s->r = r;
    long b = (long)(E*r) - (long)Q;
    mpfr_mul_si(s->center_lo, b < 0 ? s->ln2_hi : s->ln2_lo, b, MPFR_RNDD);
    mpfr_mul_si(s->center_hi, b < 0 ? s->ln2_lo : s->ln2_hi, b, MPFR_RNDU);
}

// q*Delta = (e*r-q)*ln(2) + r*log(a/q) - q*log(1+(2*d+1)/(2*a)).
// Return 0 when the directed interval cannot exclude [-2^-128,2^-128].
static int side(Check *s, uint64_t a) {
    mpfr_set_ui_2exp(s->arg, a-Q, -52, MPFR_RNDN);
    mpfr_log1p(s->lo, s->arg, MPFR_RNDD);
    mpfr_log1p(s->hi, s->arg, MPFR_RNDU);
    mpfr_mul_ui(s->lo, s->lo, s->r, MPFR_RNDD);
    mpfr_mul_ui(s->hi, s->hi, s->r, MPFR_RNDU);
    mpfr_add(s->lo, s->lo, s->center_lo, MPFR_RNDD);
    mpfr_add(s->hi, s->hi, s->center_hi, MPFR_RNDU);

    mpfr_set_ui(s->arg, 2*s->d+1, MPFR_RNDN);
    mpfr_div_ui(s->term, s->arg, 2*a, MPFR_RNDU);
    mpfr_log1p(s->term, s->term, MPFR_RNDU);
    mpfr_mul_2ui(s->term, s->term, 52, MPFR_RNDU);
    mpfr_sub(s->lo, s->lo, s->term, MPFR_RNDD);
    if (mpfr_cmp(s->lo, s->guard) > 0)
        return 1;
    mpfr_div_ui(s->term, s->arg, 2*a, MPFR_RNDD);
    mpfr_log1p(s->term, s->term, MPFR_RNDD);
    mpfr_mul_2ui(s->term, s->term, 52, MPFR_RNDD);
    mpfr_sub(s->hi, s->hi, s->term, MPFR_RNDU);
    mpfr_add(s->hi, s->hi, s->guard, MPFR_RNDU);
    return mpfr_sgn(s->hi) < 0 ? -1 : 0;
}

static int verify_exponent(Check *s, uint64_t last) {
    // For r >= 0 and d >= 0, q*Delta increases strictly with a.
    // The guess supplies one query. The sign enclosures alone certify the result.
    const long diff = (long)Q - (long)(E*s->r);
    const double root = (double)Q*exp((double)diff*0x1.62e42fefa39efp-1/s->r)
                        + ((double)Q/s->r)*(s->d+.5);
    uint64_t a = root <= Q ? Q : root >= last ? last : (uint64_t)root;
    const int order = side(s,a);
    if (order == 0)
        return 0;
    uint64_t lo = a, hi = a;
    for (uint64_t step = 1; order < 0 ? hi < last : lo > Q; step *= 2) {
        const uint64_t next = order < 0 ? hi+(step < last-hi ? step : last-hi)
                                        : lo-(step < lo-Q ? step : lo-Q);
        const int next_order = side(s,next);
        if (next_order == 0)
            return 0;
        if (next_order == order) {
            lo = hi = next;
        } else {
            if (order < 0) hi = next;
            else lo = next;
            break;
        }
    }
    while (hi-lo > 1) {
        const uint64_t mid = lo+(hi-lo)/2;
        const int mid_order = side(s,mid);
        if (mid_order == 0) return 0;
        if (mid_order < 0) lo = mid;
        else hi = mid;
    }
    return 1;
}

static uint64_t limit(Check *s, uint64_t a, int strict) {
    // q*Delta increases strictly with r. The lower cut retains overlap
    // with the guard, and every point at and above the upper cut is positive.
    uint64_t lo = 0, hi = Q;
    while (hi-lo > 1) {
        const uint64_t mid = lo+(hi-lo)/2;
        exponent(s,mid);
        if (side(s,a) >= strict) hi = mid;
        else lo = mid;
    }
    return hi;
}

int main(int argc, char **argv) {
    if (argc != 5) return 64;
    const uint64_t width = strtoul(argv[1],NULL,10), d = strtoul(argv[2],NULL,10);
    const uint64_t shard = strtoul(argv[3],NULL,10), shards = strtoul(argv[4],NULL,10);
    if (width < 1 || width > 51 || d > (1U << 24) || shards < 1 || shards > 140 || shard >= shards)
        return 64;
    const uint64_t last = Q+(UINT64_C(1)<<width)-1;
    Check s = {.d=d, .r=0};
    mpfr_inits2(PRECISION,s.ln2_lo,s.ln2_hi,s.center_lo,s.center_hi,s.lo,s.hi,s.arg,s.term,s.guard,(mpfr_ptr)0);
    mpfr_const_log2(s.ln2_lo,MPFR_RNDD);
    mpfr_const_log2(s.ln2_hi,MPFR_RNDU);
    mpfr_set_ui_2exp(s.guard,1,-GAP,MPFR_RNDN);
    exponent(&s,0);
    if (side(&s,Q) != -1 || side(&s,last) != -1) return 1;
    exponent(&s,Q);
    if (side(&s,Q) != 1 || side(&s,last) != 1) return 1;
    const uint64_t first = limit(&s,last,0), stop = limit(&s,Q,1);
    if (first > stop) return 1;
    const uint64_t a = first+(stop-first)*shard/shards, b = first+(stop-first)*(shard+1)/shards;
    for (uint64_t r = a; r < b; ++r) {
        exponent(&s,r);
        if (!verify_exponent(&s,last)) {
            fprintf(stderr,"OPEN at r=%" PRIu64 "\n",r);
            return 2;
        }
    }
    printf("VERIFIED %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
           width,d,first,stop,a,b);
    mpfr_clears(s.ln2_lo,s.ln2_hi,s.center_lo,s.center_hi,s.lo,s.hi,s.arg,s.term,s.guard,(mpfr_ptr)0);
    return 0;
}
