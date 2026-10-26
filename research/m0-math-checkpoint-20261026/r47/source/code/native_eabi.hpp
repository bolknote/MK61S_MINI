#ifndef MK61_NATIVE_EABI_HPP
#define MK61_NATIVE_EABI_HPP
#include <stdint.h>
#ifndef MK61_USE_NATIVE_EABI
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
#define MK61_USE_NATIVE_EABI 1
#else
#define MK61_USE_NATIVE_EABI 0
#endif
#endif
#if defined(__arm__) || defined(__thumb__)
#define MK61_SOFT_PCS __attribute__((pcs("aapcs")))
#else
#define MK61_SOFT_PCS
#endif
extern "C" {
MK61_SOFT_PCS double __aeabi_dadd(double, double);
MK61_SOFT_PCS double __aeabi_dsub(double, double);
MK61_SOFT_PCS double __aeabi_drsub(double, double);
MK61_SOFT_PCS double __aeabi_dmul(double, double);
MK61_SOFT_PCS double __aeabi_ddiv(double, double);
MK61_SOFT_PCS int __aeabi_dcmpeq(double, double);
MK61_SOFT_PCS int __aeabi_dcmplt(double, double);
MK61_SOFT_PCS int __aeabi_dcmple(double, double);
MK61_SOFT_PCS int __aeabi_dcmpge(double, double);
MK61_SOFT_PCS int __aeabi_dcmpgt(double, double);
MK61_SOFT_PCS int32_t __aeabi_d2iz(double);
MK61_SOFT_PCS uint32_t __aeabi_d2uiz(double);
MK61_SOFT_PCS int64_t __aeabi_d2lz(double);
MK61_SOFT_PCS uint64_t __aeabi_d2ulz(double);
MK61_SOFT_PCS double __aeabi_i2d(int32_t);
MK61_SOFT_PCS double __aeabi_ui2d(uint32_t);
MK61_SOFT_PCS double __aeabi_l2d(int64_t);
MK61_SOFT_PCS double __aeabi_ul2d(uint64_t);
MK61_SOFT_PCS float __aeabi_d2f(double);
MK61_SOFT_PCS double __aeabi_f2d(float);
struct mk61_eabi_divmod { uint64_t quotient, remainder; };
void mk61_eabi_divmod64(uint64_t, uint64_t, mk61_eabi_divmod*);
}
#endif
