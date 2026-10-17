#include "math_probe.hpp"
#include "compact_math.hpp"
#include "mk_math.hpp"

namespace picocalc {
// Exercise the project's binary64 kernels with the Pico SDK's ARMv6-M EABI
// helpers. No Cortex-M4 assembler or hard-float calling convention is linked.
// The functions do not borrow or change the running calculator's state.
unsigned math_self_test() {
    namespace math = compact_math;
    unsigned failures = 0;
    const auto check = [&](double actual, double expected, double tolerance = 2e-14) {
        if(!mk_math::is_finite(actual) || mk_math::fabs(actual - expected) > tolerance) ++failures;
    };
    check(math::sin(0.523598775598298873), 0.5);
    check(math::cos(1.047197551196597746), 0.5);
    check(math::tan(0.7853981633974483096), 1.0);
    check(math::asin(0.5), 0.523598775598298873);
    check(math::acos(0.5), 1.047197551196597746);
    check(math::atan(1.0), 0.7853981633974483096);
    check(math::ln(2.718281828459045235), 1.0);
    check(math::log10(100.0), 2.0);
    check(math::exp(1.0), 2.718281828459045235);
    check(math::pow(2.0, 10.0), 1024.0, 1e-11);
    if(mk_math::binary64_bits(math::sqrt(2.0)) != UINT64_C(0x3FF6A09E667F3BCD)) ++failures;
    if(mk_math::binary64_bits(math::sqrt(-0.0)) != UINT64_C(0x8000000000000000)) ++failures;
    return failures;
}
} // namespace picocalc
