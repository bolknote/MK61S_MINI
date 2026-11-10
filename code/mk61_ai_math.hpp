#ifndef MK61_AI_MATH_HPP
#define MK61_AI_MATH_HPP
#include <cmath>
#ifndef MK61_AI_FAST_MATH
#define MK61_AI_FAST_MATH 0
#endif
namespace mk61ai::math {
#if MK61_AI_FAST_MATH && defined(PICO_ON_DEVICE)
void initialize();
float add(float,float);
float sub(float,float);
float mul(float,float);
float div(float,float);
float sqrt(float);
float exp(float);
#else
inline void initialize() {}
inline float add(float a,float b){return a+b;}
inline float sub(float a,float b){return a-b;}
inline float mul(float a,float b){return a*b;}
inline float div(float a,float b){return a/b;}
inline float sqrt(float a){return std::sqrt(a);}
inline float exp(float a){
#if defined(MK61_AI_MATH_TEST_HOOK)
  extern float intercepted_exp(float);
  return intercepted_exp(a);
#elif MK61_AI_FAST_MATH
  return float(std::exp(double(a)));
#else
  return std::exp(a);
#endif
}
#endif
inline float round(float a){return std::round(a);}
}
#endif
