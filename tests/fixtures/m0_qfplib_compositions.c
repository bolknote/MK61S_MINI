/* Diagnostic baselines for operations without a Qfplib-M0-full entry point.
 * All arithmetic explicitly calls Qfplib. These are compositions, and their
 * results are checked against MPFR rather than assumed correctly rounded.
 * Keep code and literal pools outside the production math layout.
 */
#include <stdint.h>

extern double qfp_dadd(double, double);
extern double qfp_dsub(double, double);
extern double qfp_dmul(double, double);
extern double qfp_ddiv(double, double);
extern double qfp_dsqrt(double);
extern double qfp_datan2(double y, double x);
extern double qfp_dln(double);
extern double qfp_dexp(double);

#define REFERENCE __attribute__((section(".m0_qfplib"), noinline))

REFERENCE double qfp_composed_asin(double x) {
    double a = qfp_dsub(1.0, x);
    double b = qfp_dadd(1.0, x);
    return qfp_datan2(x, qfp_dsqrt(qfp_dmul(a, b)));
}

REFERENCE double qfp_composed_acos(double x) {
    double a = qfp_dsub(1.0, x);
    double b = qfp_dadd(1.0, x);
    return qfp_datan2(qfp_dsqrt(qfp_dmul(a, b)), x);
}

REFERENCE double qfp_composed_log10(double x) {
    return qfp_dmul(qfp_dln(x), 0x1.bcb7b1526e50ep-2);
}

/* This baseline is defined only for positive finite x and finite y. */
REFERENCE double qfp_composed_pow(double x, double y) {
    return qfp_dexp(qfp_dmul(y, qfp_dln(x)));
}

typedef union { double number;uint64_t bits;uint32_t word[2]; } Bits;

/* Negative finite x and finite integer y. Match common exact-exponent
 * shortcuts using Qfplib arithmetic before the general composition. */
REFERENCE double qfp_composed_pow_integer(double x, double y) {
    Bits exponent={.number=y};
    if(!exponent.word[0]) {
        switch(exponent.word[1]) {
        case 0:case 0x80000000U:return 1.0;
        case 0x3FF00000U:return x;
        case 0xBFF00000U:return qfp_ddiv(1.0,x);
        case 0x40000000U:return qfp_dmul(x,x);
        }
    }
    Bits magnitude={.number=x};magnitude.bits&=UINT64_C(0x7FFFFFFFFFFFFFFF);
    Bits result={.number=qfp_composed_pow(magnitude.number,y)};
    int e=(int)((exponent.word[1]>>20)&2047U)-1023;
    uint32_t odd=0;
    if(e>=0 && e<=52) {
        if(e<=20) odd=(((exponent.word[1]&0xFFFFFU)|0x100000U)>>(20-e))&1U;
        else odd=(exponent.word[0]>>(52-e))&1U;
    }
    if(odd) result.bits^=UINT64_C(0x8000000000000000);
    return result.number;
}

/* Positive finite x. Include the same algebraic shortcuts as a consumer
 * of Qfplib could use; inverse sqrt remains a rounded composition. */
REFERENCE double qfp_composed_pow_exact(double x, double y) {
    Bits exponent={.number=y};
    if(!exponent.word[0]) {
        switch(exponent.word[1]) {
        case 0x3FF00000U:return x;
        case 0xBFF00000U:return qfp_ddiv(1.0,x);
        case 0x40000000U:return qfp_dmul(x,x);
        case 0x3FE00000U:return qfp_dsqrt(x);
        case 0xBFE00000U:return qfp_ddiv(1.0,qfp_dsqrt(x));
        }
    }
    return qfp_composed_pow(x,y);
}
