#ifndef MK_MATH_HPP
#define MK_MATH_HPP

// Math facade for the FOCAL/TinyBASIC interpreters.
//
// Two selectable backends provide the transcendental functions:
//   MK61_MATH_BACKEND == MK61_MATH_BACKEND_LIBM  -> thin wrappers over <math.h>
//   MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE  -> evaluated on the MK-61 core
//
// The CORE backend reuses the calculator engine that is already linked into the
// firmware, so dropping <math.h> from this facade removes libm from the image.
//
// The "pure helpers" below (fabs/floor/ceil/frac/round/pow10_int/log10_floor and
// the number parser) never call libm: the number formatters rely on them so the
// image links without libm regardless of the chosen backend.

#include <stdint.h>
#include <float.h>

#ifndef MK61_MATH_BACKEND_LIBM
  #define MK61_MATH_BACKEND_LIBM 0
#endif
#ifndef MK61_MATH_BACKEND_CORE
  #define MK61_MATH_BACKEND_CORE 1
#endif
#ifndef MK61_MATH_BACKEND
  #define MK61_MATH_BACKEND MK61_MATH_BACKEND_LIBM
#endif

namespace mk_math {

// ---- libm-free predicates -------------------------------------------------

inline bool is_nan(double x) { return x != x; }
inline bool is_inf(double x) { return x > DBL_MAX || x < -DBL_MAX; }
inline bool is_finite(double x) { return !is_nan(x) && !is_inf(x); }

// ---- libm-free rounding helpers -------------------------------------------

inline double fabs(double x) { return x < 0.0 ? -x : x; }

inline double trunc(double x) {
  if(!is_finite(x)) return x;
  // Doubles with magnitude >= 2^53 are already integral.
  if(x >= 9007199254740992.0 || x <= -9007199254740992.0) return x;
  return (double) (long long) x;
}

inline double floor(double x) {
  const double t = trunc(x);
  return (t > x) ? t - 1.0 : t;
}

inline double ceil(double x) {
  const double t = trunc(x);
  return (t < x) ? t + 1.0 : t;
}

// Fractional part in [0, 1), matching the interpreters' historical `a-floor(a)`.
inline double frac(double x) { return x - floor(x); }

// Symmetric round-half-away-from-zero (FOCAL ROUND semantics).
inline double round_half(double x) {
  return (x >= 0.0) ? floor(x + 0.5) : ceil(x - 0.5);
}

// ---- libm-free base-10 helpers used by the number formatters ---------------

inline double pow10_int(int e) {
  const bool negative = e < 0;
  unsigned int n = negative ? 0u - (unsigned int) e : (unsigned int) e;
  if((!negative && n > 308u) || (negative && n > 324u))
    return negative ? 0.0 : __builtin_huge_val();

  double result = 1.0;
  double factor = negative ? 0.1 : 10.0;
  while(n != 0) {
    if((n & 1u) != 0) result *= factor;
    n >>= 1;
    if(n != 0) factor *= factor;
  }
  return result;
}

// floor(log10(x)) for x > 0, exact over the calculator's exponent range.
inline int log10_floor(double x) {
  if(!(x > 0.0) || !is_finite(x)) return 0;
  int e = 0;
  if(x >= 1.0) {
    while(x >= 10.0) { x /= 10.0; e++; }
  } else {
    while(x < 1.0) { x *= 10.0; e--; }
  }
  return e;
}

// ---- bounded libm-free decimal parser --------------------------------------

inline double strtod(const char* s, const char** endptr) {
  const char* p = s;
  while(*p == ' ' || *p == '\t') p++;

  bool neg = false;
  if(*p == '+' || *p == '-') { neg = (*p == '-'); p++; }

  bool any = false;
  bool significant = false;
  unsigned long long mant = 0;
  int significant_digits = 0;
  int dropped_integer_digits = 0;
  static constexpr int MAX_SIGNIFICANT_DIGITS = 18;
  while(*p >= '0' && *p <= '9') {
    any = true;
    const unsigned digit = (unsigned) (*p - '0');
    if(!significant && digit != 0) significant = true;
    if(significant) {
      if(significant_digits < MAX_SIGNIFICANT_DIGITS) {
        mant = mant * 10ULL + digit;
        significant_digits++;
      } else {
        dropped_integer_digits++;
      }
    }
    p++;
  }
  int fractional_position = 0;
  int fractional_scale = 0;
  if(*p == '.') {
    p++;
    while(*p >= '0' && *p <= '9') {
      any = true;
      fractional_position++;
      const unsigned digit = (unsigned) (*p - '0');
      if(!significant && digit != 0) significant = true;
      if(significant && significant_digits < MAX_SIGNIFICANT_DIGITS) {
        mant = mant * 10ULL + digit;
        significant_digits++;
        fractional_scale = fractional_position;
      }
      p++;
    }
  }
  if(!any) { if(endptr) *endptr = s; return 0.0; }

  int exp10 = 0;
  if(*p == 'e' || *p == 'E') {
    const char* save = p;
    p++;
    bool eneg = false;
    if(*p == '+' || *p == '-') { eneg = (*p == '-'); p++; }
    if(*p >= '0' && *p <= '9') {
      int e = 0;
      while(*p >= '0' && *p <= '9') {
        const int digit = *p - '0';
        if(e < 100000) e = e > 9999 ? 100000 : e * 10 + digit;
        p++;
      }
      exp10 = eneg ? -e : e;
    } else {
      p = save; // lone 'e' is not part of the number
    }
  }

  long long total_exp = (long long) exp10 + dropped_integer_digits - fractional_scale;
  if(total_exp > 100000) total_exp = 100000;
  if(total_exp < -100000) total_exp = -100000;
  int effective_exp = (int) total_exp;
  double value = (double) mant;
  while(effective_exp > 0 && value != 0.0 && is_finite(value)) {
    const int step = effective_exp > 308 ? 308 : effective_exp;
    value *= pow10_int(step);
    effective_exp -= step;
  }
  while(effective_exp < 0 && value != 0.0) {
    const int step = effective_exp < -308 ? -308 : effective_exp;
    value *= pow10_int(step);
    effective_exp -= step;
  }
  if(neg) value = -value;
  if(endptr) *endptr = p;
  return value;
}

inline double atof(const char* s) { return strtod(s, nullptr); }

// ---- transcendental backend ------------------------------------------------

#if MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE

// Implemented in mk_math_core.cpp, driving the MK-61 core (8-digit precision).
double sin(double x);
double cos(double x);
double tan(double x);
double asin(double x);
double acos(double x);
double atan(double x);
double ln(double x);
double log10(double x);
double exp(double x);
double sqrt(double x);
double pow(double base, double exponent);

#else // MK61_MATH_BACKEND_LIBM

} // namespace mk_math
#include <math.h>
namespace mk_math {

inline double sin(double x)   { return ::sin(x); }
inline double cos(double x)   { return ::cos(x); }
inline double tan(double x)   { return ::tan(x); }
inline double asin(double x)  { return ::asin(x); }
inline double acos(double x)  { return ::acos(x); }
inline double atan(double x)  { return ::atan(x); }
inline double ln(double x)    { return ::log(x); }
inline double log10(double x) { return ::log10(x); }
inline double exp(double x)   { return ::exp(x); }
inline double sqrt(double x)  { return ::sqrt(x); }
inline double pow(double base, double exponent) { return ::pow(base, exponent); }

#endif

} // namespace mk_math

#endif
