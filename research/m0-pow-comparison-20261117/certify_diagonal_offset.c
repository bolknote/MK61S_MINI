// Check diagonals in the pow chart e=1022, f=1023 by monotone inversion.
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <mpfr.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(ULONG_MAX >= UINT64_MAX, "a 64-bit host is required");
static const uint64_t Q = UINT64_C(1) << 52;
enum { E = 1022, PRECISION = 192, GAP = 128, FIXED = 60 };
typedef __int128 Wide;

typedef struct {
    mpfr_t ln2_lo, ln2_hi, center_lo, center_hi, lo, hi, arg, term, guard;
    uint64_t r, queries, groups, splits, affine_groups;
} Check;

typedef struct {
    uint64_t first, stop;
} Range;

typedef struct {
    uint64_t integer_origin;
    int64_t origin_lo, origin_hi, slope_lo, slope_hi, curvature_lo, curvature_hi;
} Inverse;

typedef struct {
    Wide lower, upper, step;
} Affine;

enum Crossing { BELOW, ABOVE, BRACKETED, OPEN };

static void exponent(Check *s, uint64_t r) {
    s->r = r;
    long b = (long)(E*r) - (long)Q;
    mpfr_mul_si(s->center_lo, b < 0 ? s->ln2_hi : s->ln2_lo, b, MPFR_RNDD);
    mpfr_mul_si(s->center_hi, b < 0 ? s->ln2_lo : s->ln2_hi, b, MPFR_RNDU);
}

// q*Delta = (e*r-q)*ln(2) + r*log(a/q) - q*log(1+(2*d+1)/(2*a)).
// Return 0 when the directed interval cannot exclude [-2^-128,2^-128].
static int side(Check *s, uint64_t a, uint64_t d) {
    ++s->queries;
    mpfr_set_si_2exp(s->arg, (long)a-(long)Q, -52, MPFR_RNDN);
    mpfr_log1p(s->lo, s->arg, MPFR_RNDD);
    mpfr_log1p(s->hi, s->arg, MPFR_RNDU);
    mpfr_mul_ui(s->lo, s->lo, s->r, MPFR_RNDD);
    mpfr_mul_ui(s->hi, s->hi, s->r, MPFR_RNDU);
    mpfr_add(s->lo, s->lo, s->center_lo, MPFR_RNDD);
    mpfr_add(s->hi, s->hi, s->center_hi, MPFR_RNDU);

    mpfr_set_ui(s->arg, 2*d+1, MPFR_RNDN);
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

static enum Crossing locate(Check *s, uint64_t last, uint64_t d, uint64_t *left) {
    // For r >= 0 and d >= 0, q*Delta increases strictly with a.
    // The guess supplies one query. The sign enclosures alone certify the result.
    const long diff = (long)Q - (long)(E*s->r);
    const double root = (double)Q*exp((double)diff*0x1.62e42fefa39efp-1/s->r)
                        + ((double)Q/s->r)*(d+.5);
    uint64_t a = root <= Q ? Q : root >= last ? last : (uint64_t)root;
    const int order = side(s,a,d);
    if (order == 0)
        return OPEN;
    uint64_t lo = a, hi = a;
    for (uint64_t step = 1; order < 0 ? hi < last : lo > Q; step *= 2) {
        const uint64_t next = order < 0 ? hi+(step < last-hi ? step : last-hi)
                                        : lo-(step < lo-Q ? step : lo-Q);
        const int next_order = side(s,next,d);
        if (next_order == 0)
            return OPEN;
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
        const int mid_order = side(s,mid,d);
        if (mid_order == 0) return OPEN;
        if (mid_order < 0) lo = mid;
        else hi = mid;
    }
    if (lo == hi)
        return order < 0 ? BELOW : ABOVE;
    *left = lo;
    return BRACKETED;
}

static int line_side(Check *s, int64_t c, uint64_t first, uint64_t last, int want) {
    const int64_t a = c+(int64_t)(E*first);
    const int64_t b = c+(int64_t)(E*last);
    if (a <= 0)
        return 0;
    if (want < 0)
        // The only possible stationary point is a minimum.
        return side(s,a,first) < 0 && (first == last || side(s,b,last) < 0);

    // Along a=c+E*d, the derivative has the sign of this affine numerator.
    // Its positive slope lets us find the minimum over integer d exactly.
    const Wide slope = (Wide)2*E*(E+1)*s->r;
    const Wide value = 2*((Wide)E*s->r-Q)*a+(Wide)E*(Q+s->r)*(2*first+1);
    if (value >= 0)
        return side(s,a,first) > 0;
    if (value+slope*(last-first) <= 0)
        return side(s,b,last) > 0;
    const uint64_t offset = (uint64_t)(-value/slope);
    const uint64_t d = first+offset, x = (uint64_t)a+E*offset;
    return side(s,x,d) > 0 && side(s,x+E,d+1) > 0;
}

static int verify_group(Check *s, uint64_t last, Range d) {
    const uint64_t mid = d.first+(d.stop-d.first-1)/2;
    uint64_t left = 0;
    const enum Crossing crossing = locate(s,last,mid,&left);
    if (crossing == OPEN) {
        fprintf(stderr,"OPEN at r=%" PRIu64 " d=%" PRIu64 "\n",s->r,mid);
        return 0;
    }
    if (d.stop-d.first == 1) {
        ++s->groups;
        return 1;
    }

    // In the exterior cases Delta decreases with d at fixed a.
    const int64_t c = (int64_t)left-(int64_t)(E*mid);
    if ((crossing == BELOW && side(s,last,d.first) < 0)
        || (crossing == ABOVE && side(s,Q,d.stop-1) > 0)
        || (crossing == BRACKETED && line_side(s,c,d.first,d.stop-1,-1)
            && line_side(s,c+1,d.first,d.stop-1,1))) {
        ++s->groups;
        return 1;
    }
    ++s->splits;
    return verify_group(s,last,(Range){d.first,mid+1}) && verify_group(s,last,(Range){mid+1,d.stop});
}

static Wide floor_divide(Wide n, Wide divisor) {
    return n/divisor-(n%divisor < 0);
}

static Wide floor_sum(uint64_t count, Wide modulus, Wide step, Wide origin) {
    Wide sum = 0;
    for (;;) {
        const Wide a = floor_divide(step,modulus), b = floor_divide(origin,modulus);
        sum += a*count*(count-1)/2+b*count;
        step -= a*modulus;
        origin -= b*modulus;
        const Wide end = step*count+origin;
        if (end < modulus) return sum;
        count = (uint64_t)(end/modulus);
        origin = end%modulus;
        const Wide old_modulus = modulus;
        modulus = step;
        step = old_modulus;
    }
}

static long inverse_curvature(Check *s, mpfr_srcptr a0, mpfr_rnd_t round) {
    // The fixed-point enclosure of (1+t)/(2*t^2*a0), with t=r/q.
    mpfr_set_ui(s->term,Q+s->r,MPFR_RNDN);
    mpfr_mul_ui(s->term,s->term,Q,round);
    mpfr_div_ui(s->term,s->term,s->r,round);
    mpfr_div_ui(s->term,s->term,s->r,round);
    mpfr_div(s->term,s->term,a0,round);
    mpfr_mul_2ui(s->term,s->term,FIXED-1,round);
    return mpfr_get_si(s->term,round);
}

static int inverse_model(Check *s, Inverse *model) {
    // 1016 <= q/r <= 1024 keeps the fixed-point residual q/r-E in int64_t.
    if (s->r < (Q>>10) || s->r*1016 > Q)
        return 0;
    // a0 = q*exp(-(e*r-q)*ln(2)/r). Work modulo its integer part.
    mpfr_neg(s->lo,s->center_hi,MPFR_RNDD);
    mpfr_neg(s->hi,s->center_lo,MPFR_RNDU);
    mpfr_div_ui(s->lo,s->lo,s->r,MPFR_RNDD);
    mpfr_div_ui(s->hi,s->hi,s->r,MPFR_RNDU);
    mpfr_exp(s->lo,s->lo,MPFR_RNDD);
    mpfr_exp(s->hi,s->hi,MPFR_RNDU);
    mpfr_mul_2ui(s->lo,s->lo,52,MPFR_RNDD);
    mpfr_mul_2ui(s->hi,s->hi,52,MPFR_RNDU);
    if (mpfr_cmp_ui(s->lo,7*(Q/8)) < 0 || mpfr_cmp_ui(s->hi,2*Q) >= 0)
        return 0;
    model->curvature_lo = inverse_curvature(s,s->hi,MPFR_RNDD);
    model->curvature_hi = inverse_curvature(s,s->lo,MPFR_RNDU);
    const unsigned long integer = mpfr_get_ui(s->lo,MPFR_RNDD);
    model->integer_origin = integer;
    mpfr_sub_ui(s->lo,s->lo,integer,MPFR_RNDD);
    mpfr_sub_ui(s->hi,s->hi,integer,MPFR_RNDU);
    mpfr_mul_2ui(s->lo,s->lo,FIXED,MPFR_RNDD);
    mpfr_mul_2ui(s->hi,s->hi,FIXED,MPFR_RNDU);
    model->origin_lo = mpfr_get_si(s->lo,MPFR_RNDD);
    model->origin_hi = mpfr_get_si(s->hi,MPFR_RNDU);
    const Wide numerator = ((Wide)Q-E*(Wide)s->r)*((Wide)1<<FIXED);
    model->slope_lo = (int64_t)floor_divide(numerator,s->r);
    model->slope_hi = (int64_t)-floor_divide(-numerator,s->r);
    return 1;
}

static Affine affine_bounds(const Inverse *m, Range d) {
    // For u=d+1/2, the inverse root is a0+u/t-c*u^2+R.
    // Subtract the integral reference for a0 and E*d+E/2.
    // Enclose the quadratic by parallel lines centered at the interval midpoint.
    const int64_t mid = (d.first+d.stop-1)/2;
    const Wide center = 2*mid+1;
    const Wide radius = (d.stop-d.first)/2;
    const Wide step_lo = 4*((Wide)m->slope_lo-m->curvature_hi*center);
    const Wide step_hi = 4*((Wide)m->slope_hi-m->curvature_lo*center);
    const Wide low = 4*(Wide)m->origin_lo+2*center*m->slope_lo-m->curvature_hi*center*center;
    const Wide high = 4*(Wide)m->origin_hi+2*center*m->slope_hi-m->curvature_lo*center*center;
    const Wide slope_pad = (step_hi-step_lo)*radius;
    // 0 <= R <= u^3*2^-74 and the log guard moves a root by <2^-73.
    // At scale 2^(FIXED+2) the guard needs at most one fixed-point unit.
    const Wide tail_scale = (Wide)1<<(74-FIXED-2);
    const Wide rem = ((Wide)d.stop*d.stop*d.stop+tail_scale-1)/tail_scale;
    const Wide advance = step_lo*((Wide)d.first-mid);
    const Wide lower = low+advance-slope_pad-4*m->curvature_hi*radius*radius-1;
    const Wide upper = high+advance+slope_pad+rem+1;
    return (Affine){lower,upper,step_lo};
}

static int verify_candidates(Check *s, uint64_t last, Range d, const Inverse *model, Affine shape) {
    const Wide unit = (Wide)1<<(FIXED+2);
    for (uint64_t offset = d.first; offset < d.stop; ++offset) {
        const uint64_t origin = model->integer_origin+E*offset+E/2;
        Wide first = origin+floor_divide(shape.lower-1,unit)+1;
        Wide stop = origin+floor_divide(shape.upper,unit)+1;
        if (first < Q) first = Q;
        if (stop > last+1) stop = last+1;
        for (Wide a = first; a < stop; ++a) {
            if (!side(s,(uint64_t)a,offset)) {
                fprintf(stderr,"OPEN at r=%" PRIu64 " d=%" PRIu64 " a=%" PRIu64 "\n",
                        s->r,offset,(uint64_t)a);
                return 0;
            }
        }
        shape.lower += shape.step;
        shape.upper += shape.step;
    }
    ++s->groups;
    return 1;
}

static int verify_affine(Check *s, uint64_t last, Range d, const Inverse *model) {
    const Affine shape = affine_bounds(model,d);
    const uint64_t count = d.stop-d.first;
    const Wide unit = (Wide)1<<(FIXED+2);
    if (floor_sum(count,unit,shape.step,shape.lower-1) == floor_sum(count,unit,shape.step,shape.upper)) {
        ++s->groups;
        ++s->affine_groups;
        return 1;
    }
    if (count <= 16)
        return verify_candidates(s,last,d,model,shape);
    ++s->splits;
    const uint64_t mid = d.first+(d.stop-d.first)/2;
    return verify_affine(s,last,(Range){d.first,mid},model)
        && verify_affine(s,last,(Range){mid,d.stop},model);
}

static uint64_t limit(Check *s, uint64_t a, uint64_t d, int strict) {
    // q*Delta increases strictly with r. The lower cut retains overlap
    // with the guard, and every point at and above the upper cut is positive.
    uint64_t lo = 0, hi = Q;
    while (hi-lo > 1) {
        const uint64_t mid = lo+(hi-lo)/2;
        exponent(s,mid);
        if (side(s,a,d) >= strict) hi = mid;
        else lo = mid;
    }
    return hi;
}

static uint64_t read_number(const char *arg) {
    if (*arg < '0' || *arg > '9')
        return UINT64_MAX;
    char *end;
    errno = 0;
    const unsigned long number = strtoul(arg,&end,10);
    return errno || *end ? UINT64_MAX : number;
}

int main(int argc, char **argv) {
    const int affine = argc == 7 && strcmp(argv[1],"--affine-band") == 0;
    const int band = affine || (argc == 7 && strcmp(argv[1],"--band") == 0);
    if (argc != 5 && !band) return 64;
    const uint64_t width = read_number(argv[1+band]), d_first = read_number(argv[2+band]);
    const uint64_t shard = read_number(argv[3+2*band]), shards = read_number(argv[4+2*band]);
    if (width < 1 || width > 51 || d_first >= Q || shards < 1 || shards > 140 || shard >= shards)
        return 64;
    const uint64_t last = Q+(UINT64_C(1)<<width)-1;
    const Range d = {d_first,band ? read_number(argv[4]) : d_first+1};
    if (d.first >= d.stop || d.stop > 2*Q-last)
        return 64;
    Check s = {0};
    mpfr_inits2(PRECISION,s.ln2_lo,s.ln2_hi,s.center_lo,s.center_hi,s.lo,s.hi,s.arg,s.term,s.guard,(mpfr_ptr)0);
    mpfr_const_log2(s.ln2_lo,MPFR_RNDD);
    mpfr_const_log2(s.ln2_hi,MPFR_RNDU);
    mpfr_set_ui_2exp(s.guard,1,-GAP,MPFR_RNDN);
    exponent(&s,0);
    if (side(&s,last,d.first) != -1) return 1;
    exponent(&s,Q);
    if (side(&s,Q,d.stop-1) != 1) return 1;
    const uint64_t first = limit(&s,last,d.first,0), stop = limit(&s,Q,d.stop-1,1);
    if (first > stop) return 1;
    const uint64_t a = first+(stop-first)*shard/shards, b = first+(stop-first)*(shard+1)/shards;
    for (uint64_t r = a; r < b; ++r) {
        exponent(&s,r);
        Inverse model;
        const int model_available = affine && d.stop <= (1U<<20) && inverse_model(&s,&model);
        if (!(model_available ? verify_affine(&s,last,d,&model) : verify_group(&s,last,d)))
            return 2;
    }
    if (band) {
        printf("%s %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64
               " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64,
               affine ? "VERIFIED_AFFINE" : "VERIFIED_BAND",
               width,d.first,d.stop,first,stop,a,b,s.groups,s.splits,s.queries);
        if (affine)
            printf(" %" PRIu64,s.affine_groups);
        putchar('\n');
    } else {
        printf("VERIFIED %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
               width,d.first,first,stop,a,b);
    }
    mpfr_clears(s.ln2_lo,s.ln2_hi,s.center_lo,s.center_hi,s.lo,s.hi,s.arg,s.term,s.guard,(mpfr_ptr)0);
    return 0;
}
