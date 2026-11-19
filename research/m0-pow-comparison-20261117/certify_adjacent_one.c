// Exclude tiny pow gaps for y immediately below or above 1, for whole x binades.
// A floating guess only selects a starting point. All decisions use MPFR bounds.
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <mpfr.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { Precision = 192, LatticeGap = 128, Unknown = 2 };
static const uint64_t Mantissa = UINT64_C(1) << 52;
_Static_assert(ULONG_MAX >= UINT64_MAX, "Use a 64-bit Unix host");

typedef struct {
    int scale;
    double delta;
    mpfr_t x, low, high, turn_low, turn_high, gap;
    uint64_t targets;
} Check;

static void log_at(Check *c, uint64_t a) {
    mpfr_set_ui_2exp(c->x, a, c->scale, MPFR_RNDN);
    mpfr_log(c->low, c->x, MPFR_RNDD);
    mpfr_log(c->high, c->x, MPFR_RNDU);
}

static int turn_side(Check *c, uint64_t a) {
    // The sign of log(x)+log(1+delta)/delta decides which side of the turn a is on.
    log_at(c, a);
    mpfr_add(c->low, c->low, c->turn_low, MPFR_RNDD);
    mpfr_add(c->high, c->high, c->turn_high, MPFR_RNDU);
    return mpfr_sgn(c->low) > 0 ? 1 : (mpfr_sgn(c->high) < 0 ? -1 : 0);
}

static void displacement(Check *c, uint64_t a, int direction) {
    log_at(c, a);
    if (c->delta < 0)
        mpfr_swap(c->low, c->high);
    mpfr_mul_d(c->low, c->low, c->delta, MPFR_RNDD);
    mpfr_mul_d(c->high, c->high, c->delta, MPFR_RNDU);
    mpfr_expm1(c->low, c->low, MPFR_RNDD);
    mpfr_expm1(c->high, c->high, MPFR_RNDU);
    if (direction < 0)
        mpfr_swap(c->low, c->high);
    const long factor = direction*(long)(4*a);
    mpfr_mul_si(c->low, c->low, factor, MPFR_RNDD);
    mpfr_mul_si(c->high, c->high, factor, MPFR_RNDU);
    mpfr_sub(c->low, c->low, c->gap, MPFR_RNDD);
    mpfr_add(c->high, c->high, c->gap, MPFR_RNDU);
}

static int target_side(Check *c, uint64_t a, long target, int direction) {
    displacement(c, a, direction);
    if (mpfr_cmp_si(c->high, target) < 0)
        return -1;
    return mpfr_cmp_si(c->low, target) > 0 ? 1 : Unknown;
}

static uint64_t guess(Check *c, uint64_t first, uint64_t last, long target, int direction) {
    // Binary search in machine double for a proposal. Exact comparisons below
    // repair even an arbitrarily inaccurate result from libm.
    uint64_t lo = first, hi = last;
    while (lo < hi) {
        const uint64_t mid = lo+(hi-lo)/2;
        const double d = 4.0*direction*(double)mid*expm1(c->delta*log(ldexp((double)mid, c->scale)));
        if (d < (double)target)
            lo = mid+1;
        else
            hi = mid;
    }
    return lo;
}

static int excludes_target(Check *c, uint64_t first, uint64_t last, long target, int direction) {
    const uint64_t proposed = guess(c, first, last, target, direction);
    const int order = target_side(c, proposed, target, direction);
    if (order == Unknown)
        return 0;
    uint64_t lo = proposed, hi = proposed;
    // Expand a certified bracket from the guess. An endpoint has no
    // untested points beyond it. Then shrink to consecutive integers.
    for (uint64_t stride = 1; order < 0 ? hi < last : lo > first; stride *= 2) {
        const uint64_t next = order < 0 ? hi + (stride < last-hi ? stride : last-hi)
                                       : lo - (stride < lo-first ? stride : lo-first);
        const int next_order = target_side(c, next, target, direction);
        if (next_order == Unknown)
            return 0;
        if (next_order == order) {
            lo = hi = next;
        } else {
            if (order < 0)
                hi = next;
            else
                lo = next;
            break;
        }
    }
    while (hi-lo > 1) {
        const uint64_t mid = lo+(hi-lo)/2;
        const int mid_order = target_side(c, mid, target, direction);
        if (mid_order == Unknown)
            return 0;
        if (mid_order < 0)
            lo = mid;
        else
            hi = mid;
    }
    return 1;
}

static int excludes_range(Check *c, uint64_t first, uint64_t last, int turn) {
    const int direction = c->delta > 0 ? turn : -turn;
    displacement(c, first, direction);
    const long from = mpfr_get_si(c->low, MPFR_RNDU);
    displacement(c, last, direction);
    const long to = mpfr_get_si(c->high, MPFR_RNDD);
    for (long target = from; target <= to; ++target) {
        if (!target)
            continue;
        ++c->targets;
        if (!excludes_target(c, first, last, target, direction)) {
            fprintf(stderr, "OPEN range [%" PRIu64 ",%" PRIu64 "] * 2^%d, displacement %ld\n",
                    first, last, c->scale, direction*target);
            return 0;
        }
    }
    return 1;
}

static int excludes_binade(Check *c, int field) {
    c->scale = (field ? field : 1)-1075;
    const uint64_t first = field ? Mantissa : 1;
    const uint64_t last = (field ? 2*Mantissa : Mantissa)-1;
    const int l = turn_side(c, first), r = turn_side(c, last);
    if (l == r && l)
        return excludes_range(c, first, last, l);
    if (l != -1 || r != 1)
        return 0;
    uint64_t lo = first, hi = last;
    while (hi-lo > 1) {
        const uint64_t mid = lo+(hi-lo)/2;
        const int side = turn_side(c, mid);
        if (!side)
            return 0;
        if (side < 0)
            lo = mid;
        else
            hi = mid;
    }
    return excludes_range(c, first, lo, -1) && excludes_range(c, hi, last, 1);
}

int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[1], "above") && strcmp(argv[1], "below")))
        return 2;
    char *end;
    const long first = strtol(argv[2], &end, 10);
    if (end == argv[2] || *end)
        return 2;
    const long stop = strtol(argv[3], &end, 10);
    if (end == argv[3] || *end || first < 0 || stop > 2047 || first >= stop)
        return 2;
    Check c = {.delta = !strcmp(argv[1], "above") ? 0x1p-52 : -0x1p-53};
    mpfr_inits2(Precision, c.x, c.low, c.high, c.turn_low, c.turn_high, c.gap, (mpfr_ptr)NULL);
    mpfr_set_ui_2exp(c.gap, 1, -LatticeGap, MPFR_RNDN);
    mpfr_set_d(c.x, c.delta, MPFR_RNDN);
    const int positive = c.delta > 0;
    mpfr_log1p(c.turn_low, c.x, positive ? MPFR_RNDD : MPFR_RNDU);
    mpfr_log1p(c.turn_high, c.x, positive ? MPFR_RNDU : MPFR_RNDD);
    mpfr_div_d(c.turn_low, c.turn_low, c.delta, MPFR_RNDD);
    mpfr_div_d(c.turn_high, c.turn_high, c.delta, MPFR_RNDU);
    for (int field = (int)first; field < stop; ++field) {
        if (!excludes_binade(&c, field)) {
            fprintf(stderr, "Incomplete field %d for y %s 1\n", field, argv[1]);
            return 1;
        }
    }
    printf("%s %s %ld %ld %" PRIu64 "\n", mpfr_get_version(), argv[1], first, stop, c.targets);
    mpfr_clears(c.x, c.low, c.high, c.turn_low, c.turn_high, c.gap, (mpfr_ptr)NULL);
    return 0;
}
