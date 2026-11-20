#include <float.h>
#include <math.h>
#include <mpfr.h>
#include <stdio.h>
#include <stdlib.h>

#if !defined(__i386__) && !defined(__x86_64__)
#error An x86 target with x87 is required
#endif
_Static_assert(DBL_MANT_DIG == 53 && LDBL_MANT_DIG == 64, "binary64 and x87 extended precision");

static long double log_product(double x, double y, int fused) {
    const double factor = fused ? y : 1.0;
    long double result;
    if (0.75 <= x && x <= 1.25) {
        const double delta = x - 1.0;
        __asm__ volatile("fldl %[factor]\n\t"
                         "fldl %[delta]\n\t"
                         "fyl2xp1\n\t"
                         "fstpt %[result]"
                         : [result] "=m"(result)
                         : [factor] "m"(factor), [delta] "m"(delta)
                         : "st", "st(1)");
    } else {
        __asm__ volatile("fldl %[factor]\n\t"
                         "fldl %[x]\n\t"
                         "fyl2x\n\t"
                         "fstpt %[result]"
                         : [result] "=m"(result)
                         : [factor] "m"(factor), [x] "m"(x)
                         : "st", "st(1)");
    }
    return fused ? result : result*y;
}

static double exp2_to_binary64(long double t) {
    double result;
    // After FRNDINT, keep n in ST(1) and compute 2**(t-n) in ST(0).
    __asm__ volatile("fldt %[t]\n\t"
                     "fld %%st(0)\n\t"
                     "frndint\n\t"
                     "fxch %%st(1)\n\t"
                     "fsub %%st(1), %%st(0)\n\t"
                     "f2xm1\n\t"
                     "fld1\n\t"
                     "faddp\n\t"
                     "fscale\n\t"
                     "fstp %%st(1)\n\t"
                     "fstpl %[result]"
                     : [result] "=m"(result)
                     : [t] "m"(t)
                     : "st", "st(1)", "st(2)");
    return result;
}

static void record(const char *mode, double actual, double expected,
                   double x, double y, unsigned long *mismatches) {
    if (actual == expected)
        return;
    ++*mismatches;
    if (*mismatches == 1)
        printf("%s x=%a y=%a got=%a rne=%a\n", mode, x, y, actual, expected);
}

int main(void) {
    unsigned short saved_cw;
    __asm__ volatile("fnstcw %0" : "=m"(saved_cw));
    const unsigned short nearest_extended = (saved_cw & ~0x0f00u) | 0x033fu;
    __asm__ volatile("fldcw %0" : : "m"(nearest_extended));

    mpfr_t base, power, lo, hi, extended;
    mpfr_inits2(256, base, power, lo, hi, (mpfr_ptr)0);
    mpfr_init2(extended, 64);
    unsigned long checked = 0, overlap = 0, separate = 0, fused = 0, double_round = 0;
    char line[512];
    while (fgets(line, sizeof line, stdin)) {
        char *separator, *end;
        const double x = strtod(line, &separator);
        if (separator == line || *separator != ',')
            continue;
        const double y = strtod(separator+1, &end);
        if (end == separator+1 || !(x > 0) || !isfinite(x) || !isfinite(y) || trunc(y) == y)
            continue;
        mpfr_set_d(base, x, MPFR_RNDN);
        mpfr_set_d(power, y, MPFR_RNDN);
        mpfr_pow(lo, base, power, MPFR_RNDD);
        mpfr_pow(hi, base, power, MPFR_RNDU);
        const double expected = mpfr_get_d(lo, MPFR_RNDN);
        if (expected != mpfr_get_d(hi, MPFR_RNDN)) {
            ++overlap;
            continue;
        }
        if (!isnormal(expected))
            continue;
        ++checked;
        mpfr_pow(extended, base, power, MPFR_RNDN);
        record("separate-x87", exp2_to_binary64(log_product(x, y, 0)), expected, x, y, &separate);
        record("fused-x87", exp2_to_binary64(log_product(x, y, 1)), expected, x, y, &fused);
        record("ideal-64-to-53", mpfr_get_d(extended, MPFR_RNDN), expected, x, y, &double_round);
    }
    printf("mpfr=%s checked=%lu overlap=%lu separate=%lu fused=%lu ideal_64_to_53=%lu\n",
           mpfr_get_version(), checked, overlap, separate, fused, double_round);
    mpfr_clears(base, power, lo, hi, extended, (mpfr_ptr)0);
    __asm__ volatile("fldcw %0" : : "m"(saved_cw));
    return ferror(stdin) || checked == 0 || overlap != 0;
}
