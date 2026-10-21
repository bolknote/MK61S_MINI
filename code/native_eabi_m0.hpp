#ifndef MK61_NATIVE_EABI_M0_HPP
#define MK61_NATIVE_EABI_M0_HPP
#include "native_eabi.hpp"

// ARMv6-M software arithmetic. These are also callable by the host oracle;
// their implementations use integer bits, never host floating arithmetic.
extern "C" {
MK61_SOFT_PCS float __aeabi_fadd(float, float);
MK61_SOFT_PCS float __aeabi_fsub(float, float);
MK61_SOFT_PCS float __aeabi_frsub(float, float);
MK61_SOFT_PCS float __aeabi_fmul(float, float);
MK61_SOFT_PCS float __aeabi_fdiv(float, float);
MK61_SOFT_PCS int __aeabi_fcmpeq(float, float);
MK61_SOFT_PCS int __aeabi_fcmplt(float, float);
MK61_SOFT_PCS int __aeabi_fcmple(float, float);
MK61_SOFT_PCS int __aeabi_fcmpge(float, float);
MK61_SOFT_PCS int __aeabi_fcmpgt(float, float);
MK61_SOFT_PCS int __aeabi_fcmpun(float, float);
MK61_SOFT_PCS int __aeabi_dcmpun(double, double);
MK61_SOFT_PCS int32_t __aeabi_f2iz(float);
MK61_SOFT_PCS uint32_t __aeabi_f2uiz(float);
MK61_SOFT_PCS float __aeabi_i2f(int32_t);
MK61_SOFT_PCS float __aeabi_ui2f(uint32_t);
MK61_SOFT_PCS uint64_t __aeabi_lmul(uint64_t, uint64_t);
int __clzsi2(uint32_t);
int __clzdi2(uint64_t);
void mk61_m0_divmod64(uint64_t, uint64_t, mk61_eabi_divmod*);
// Correctly rounded integer kernels; float arithmetic is not needed by sqrt.
MK61_SOFT_PCS float mk61_m0_sqrtf(float);
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
MK61_SOFT_PCS double mk61_m0_sqrt(double);
MK61_SOFT_PCS double mk61_m0_fma(double,double,double);
// Correctly rounded fallback (RNE), also used for ambiguous fast intervals.
MK61_SOFT_PCS double mk61_m0_cr_sin(double);
MK61_SOFT_PCS double mk61_m0_cr_cos(double);
MK61_SOFT_PCS double mk61_m0_cr_tan(double);
MK61_SOFT_PCS double mk61_m0_cr_atan(double);
MK61_SOFT_PCS double mk61_m0_atan(double);
MK61_SOFT_PCS double mk61_m0_trig(double,unsigned);
MK61_SOFT_PCS double mk61_m0_cr_asin(double);
MK61_SOFT_PCS double mk61_m0_asin(double);
MK61_SOFT_PCS double mk61_m0_acos(double);
MK61_SOFT_PCS double mk61_m0_cr_acos(double);
MK61_SOFT_PCS double mk61_m0_cr_ln(double);
MK61_SOFT_PCS double mk61_m0_cr_log10(double);
MK61_SOFT_PCS double mk61_m0_cr_exp(double);
MK61_SOFT_PCS double mk61_m0_cr_pow(double,double);
MK61_SOFT_PCS double mk61_m0_pow_fast(double,double);
MK61_SOFT_PCS double mk61_m0_exp(double);
uint64_t mk61_m0_mul_q62(uint64_t,uint64_t);
uint32_t mk61_m0_math_udiv32(uint32_t,uint32_t);
void mk61_m0_sincos_small(double,double,double*,unsigned);
MK61_SOFT_PCS double mk61_m0_tan_small(double,double);
uint64_t mk61_m0_atan_reduced(double,int*);
MK61_SOFT_PCS double mk61_m0_ln(double);
MK61_SOFT_PCS double mk61_m0_log10(double);
// Reduced input |x+tail| <= pi/4, |x| >= 1/64; mask 1=sin, 2=cos.
void mk61_m0_sincos_reduced(double,double,double*,unsigned);
MK61_SOFT_PCS double mk61_m0_trig_pack(uint64_t,uint64_t);
int mk61_m0_reduce_pio2(double,double*);
// 1: completed result in out[0]; 0: use the shared reducer.
// Caller supplies pi/4 < |x| < 2^20.
int mk61_m0_trig_medium(double,double*,unsigned);
#endif
}
#endif
