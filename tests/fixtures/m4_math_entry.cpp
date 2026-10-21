#include "compact_math.hpp"
extern "C" __attribute__((used,noinline,externally_visible))
double mk61_m4_math(unsigned operation,double x,double y) {
  switch(operation) {
    case 0:return compact_math::sin(x);
    case 1:return compact_math::cos(x);
    case 2:return compact_math::tan(x);
    case 3:return compact_math::asin(x);
    case 4:return compact_math::acos(x);
    case 5:return compact_math::atan(x);
    case 6:return compact_math::ln(x);
    case 7:return compact_math::log10(x);
    case 8:return compact_math::exp(x);
    case 9:return compact_math::sqrt(x);
    case 10:return compact_math::pow(x,y);
    default:return x;
  }
}
