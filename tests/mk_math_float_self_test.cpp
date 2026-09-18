#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>

#include "mk_math.hpp"

namespace {

void check(const char* name, double actual, double expected,
           double relative_tolerance = 2.0e-6) {
  const double scale = std::fmax(1.0, std::fabs(expected));
  if(std::isnan(actual) != std::isnan(expected) ||
     (!std::isnan(expected) && std::fabs(actual - expected) >
                                  relative_tolerance * scale)) {
    std::fprintf(stderr, "%s: got %.17g, expected %.17g\n",
                 name, actual, expected);
    std::exit(1);
  }
}

} // namespace

int main() {
  static_assert(MK61_MATH_BACKEND == MK61_MATH_BACKEND_FLOAT,
                "test must use FLOAT math");

  check("sin", mk_math::sin(0.7), std::sin(0.7));
  check("cos", mk_math::cos(-1.2), std::cos(-1.2));
  check("tan", mk_math::tan(0.3), std::tan(0.3));
  check("asin", mk_math::asin(0.4), std::asin(0.4));
  check("acos", mk_math::acos(-0.4), std::acos(-0.4));
  check("atan", mk_math::atan(3.0), std::atan(3.0));
  check("ln", mk_math::ln(12.5), std::log(12.5));
  check("log10", mk_math::log10(1234.0), std::log10(1234.0));
  check("exp", mk_math::exp(2.25), std::exp(2.25));
  check("sqrt", mk_math::sqrt(17.0), std::sqrt(17.0));
  check("pow", mk_math::pow(3.5, 2.25), std::pow(3.5, 2.25));

  check("sqrt domain", mk_math::sqrt(-1.0),
        std::numeric_limits<double>::quiet_NaN());
  std::puts("mk_math FLOAT self-test passed");
  return 0;
}
