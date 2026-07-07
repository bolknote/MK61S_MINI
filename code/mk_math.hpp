#ifndef MK_MATH_HPP
#define MK_MATH_HPP

// Math facade for the FOCAL/BASIC/TinyBASIC interpreters.
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

// ---- libm-free rounding helpers -------------------------------------------

inline double fabs(double x) { return x < 0.0 ? -x : x; }

inline double trunc(double x) {
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
  double r = 1.0;
  int n = e < 0 ? -e : e;
  while(n-- > 0) r *= 10.0;
  return e < 0 ? 1.0 / r : r;
}

// floor(log10(x)) for x > 0, exact over the calculator's exponent range.
inline int log10_floor(double x) {
  int e = 0;
  if(x >= 1.0) {
    while(x >= 10.0) { x /= 10.0; e++; }
  } else {
    while(x < 1.0) { x *= 10.0; e--; }
  }
  return e;
}

// ---- libm-free number parser (drop-in for strtod) --------------------------

inline double strtod(const char* s, const char** endptr) {
  const char* p = s;
  while(*p == ' ' || *p == '\t') p++;

  bool neg = false;
  if(*p == '+' || *p == '-') { neg = (*p == '-'); p++; }

  bool any = false;
  unsigned long long mant = 0;
  int frac_digits = 0;
  const unsigned long long MANT_LIMIT = 1000000000000000000ULL;
  while(*p >= '0' && *p <= '9') {
    any = true;
    if(mant < MANT_LIMIT) mant = mant * 10 + (unsigned) (*p - '0');
    p++;
  }
  if(*p == '.') {
    p++;
    while(*p >= '0' && *p <= '9') {
      any = true;
      if(mant < MANT_LIMIT) { mant = mant * 10 + (unsigned) (*p - '0'); frac_digits++; }
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
      while(*p >= '0' && *p <= '9') { e = e * 10 + (*p - '0'); p++; }
      exp10 = eneg ? -e : e;
    } else {
      p = save; // lone 'e' is not part of the number
    }
  }

  double value = (double) mant * pow10_int(exp10 - frac_digits);
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
