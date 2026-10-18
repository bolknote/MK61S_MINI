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
// Integer square root used only as compact_math's binary32 seed on M0+.
MK61_SOFT_PCS float mk61_m0_sqrtf(float);
}
#endif
