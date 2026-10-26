// Correctly rounded fallback functions. CORE-MATH MIT notices and exact
// upstream/port hashes are in third_party/core_math/. Only ARMv6-M uses this
// translation unit; the M4 kernels and compilation path are independent.
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && (defined(__arm__) || defined(__thumb__))
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <fenv.h>
#include <errno.h>
#include "native_eabi_m0.hpp"
#include "native_eabi_m0_uint128.hpp"
#include "native_eabi_m0_cr_shim.inc"

#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-value"
#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wliteral-suffix"
#pragma GCC diagnostic ignored "-Wnarrowing"

#include "native_eabi_m0_cr_types.hpp"

namespace core_sin {
#include "../third_party/core_math/sin/sin.c"
}
extern "C" double mk61_m0_cr_sin(double x) { return core_sin::cr_sin(x); }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" __attribute__((optimize("Os"),noinline,cold,section(".m0_trig_large")))
const uint64_t* mk61_m0_trig_inverse_table() {return core_sin::T;}
#endif

#undef CH
#undef CL

namespace core_cos {
#include "../third_party/core_math/cos/cos.c"
}
extern "C" double mk61_m0_cr_cos(double x) { return core_cos::cr_cos(x); }
#undef CH
#undef CL

namespace core_tan {
#include "../third_party/core_math/tan/tan.c"
}
extern "C" double mk61_m0_cr_tan(double x) { return core_tan::cr_tan(x); }
#undef CH
#undef CL

namespace core_atan {
#include "../third_party/core_math/atan/atan.c"
}
extern "C" double mk61_m0_cr_atan(double x) { return core_atan::cr_atan(x); }

namespace core_asin {
#include "../third_party/core_math/asin/asin.c"
}
extern "C" double mk61_m0_cr_asin(double x) { return core_asin::cr_asin(x); }
#undef MAGIC
#undef roundeven_finite

namespace core_acos {
#include "../third_party/core_math/acos/acos.c"
}
extern "C" double mk61_m0_cr_acos(double x) { return core_acos::cr_acos(x); }
#undef MAGIC
#undef roundeven_finite

namespace core_log {
#include "../third_party/core_math/log/log.c"
}
extern "C" double mk61_m0_cr_ln(double x) { return core_log::cr_log(x); }
#undef DINT_H
#undef OFFSET
#undef UINT128_T

namespace core_log10 {
#include "../third_party/core_math/log10/log10.c"
}
extern "C" double mk61_m0_cr_log10(double x) { return core_log10::cr_log10(x); }
#undef DINT_H
#undef OFFSET
#undef ONE_OVER_LOG10_H
#undef ONE_OVER_LOG10_L
#undef UINT128_T

namespace core_exp {
#include "../third_party/core_math/exp/exp.c"
}
extern "C" double mk61_m0_cr_exp(double x) { return core_exp::cr_exp(x); }
#undef roundeven_finite

#include "native_eabi_m0_pow_interval.inc"
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_pow_exact.inc"
#endif
// Reached only after CORE-MATH's final 256-bit rounding test failed. The
// directed integer passes do not change any successful earlier result.
extern "C" __attribute__((optimize("Os"),noinline,cold))
double mk61_m0_pow_rescue(double x,double y,double sign) {
  uint64_t a,b,s,result;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  result=UINT64_C(0x7FF0000000000000); // Unknown initial rounding hint.
#endif
  __builtin_memcpy(&a,&x,8);__builtin_memcpy(&b,&y,8);__builtin_memcpy(&s,&sign,8);
  if(m0_pow_interval::Fixed<512>::evaluate(a,b,result) ||
     m0_pow_interval::Fixed<1024>::evaluate(a,b,result)
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
     || mk61_m0_pow_exact_small(a&UINT64_C(0x7FFFFFFFFFFFFFFF),b,&result)
#endif
     ) {
    result|=s&UINT64_C(0x8000000000000000);
    double rounded;__builtin_memcpy(&rounded,&result,8);return rounded;
  }
  // Do not return an approximation if the final enclosure is undecided.
  // A universal precision bound for binary64 pow is still not established.
  __builtin_trap();
}
#undef exit
#define exit(n) return mk61_m0_pow_rescue(x,y,s)
namespace core_pow {
#include "../third_party/core_math/pow/pow.c"
}
#undef exit
#define exit(n) __builtin_trap()
extern "C" double mk61_m0_cr_pow(double x,double y) { return core_pow::cr_pow(x,y); }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Internal precondition: positive finite normal x != 1, finite y, and
// |y*log(x)| < 700, already checked by pow_refine_checked's Q94 stage.
extern "C" double mk61_m0_cr_pow_refined(double x,double y) {
  return core_pow::pow_accurate(x,y,1.0,x,core_pow::is_exact(x,y));
}
#endif
#undef CORE_MATH_POW
#undef CR_POW_H
#undef DINT_H
#undef ENABLE_EXACT
#undef ENABLE_FP
#undef ENABLE_ZIV2
#undef ENABLE_ZIV3
#undef ERR_BND_2
#undef ERR_BND_3
#undef FLAG_T
#undef INVLOG2
#undef LOG2H
#undef LOG2L
#undef LOG2_H
#undef LOG2_L
#undef POW_ITERATION
#undef QINT_H
#undef RHO0
#undef RHO1
#undef RHO2
#undef RHO3
#undef UINT128_T
#undef roundeven_finite

#endif
