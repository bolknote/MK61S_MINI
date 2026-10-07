#include "mk_math.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
static double original_trunc(double x) {
  if(x!=x || x>DBL_MAX || x<-DBL_MAX) return x;
  if(x>=9007199254740992.0 || x<=-9007199254740992.0) return x;
  return (double)(long long)x;
}
static double original_floor(double x) {
  const double t=original_trunc(x);return t>x?t-1.0:t;
}
static uint64_t bits(double x) {uint64_t b;memcpy(&b,&x,sizeof(b));return b;}
static void check(double x) {
  assert(mk_math::is_finite(x)==(x==x && x<=DBL_MAX && x>=-DBL_MAX));
  assert(bits(mk_math::trunc(x))==bits(original_trunc(x)));
  assert(bits(mk_math::floor(x))==bits(original_floor(x)));
  const double t=original_trunc(x);
  assert(bits(mk_math::ceil(x))==bits(t<x?t+1.0:t));
}
int main() {
  uint64_t random=0x61B451C987ULL;
  for(unsigned i=0;i<100000;++i) {
    random^=random<<13;random^=random>>7;random^=random<<17;
    double x;memcpy(&x,&random,sizeof(x));check(x);
  }
  for(int i=-32768;i<32768;++i) for(double fraction:{0.0,.125,.5,.875}) check(i+fraction);
  for(uint64_t b:{UINT64_C(0),UINT64_C(0x8000000000000000),UINT64_C(1),
      UINT64_C(0x8000000000000001),UINT64_C(0x7FF0000000000000),
      UINT64_C(0xFFF0000000000000),UINT64_C(0x7FF8000000000001),
      UINT64_C(0xFFF0000000000001)}) {
    double x;memcpy(&x,&b,sizeof(x));check(x);
  }
  for(int exponent=0;exponent<2048;++exponent) {
    uint64_t b=(uint64_t)exponent<<52;
    for(uint64_t fraction:{UINT64_C(0),UINT64_C(1),UINT64_C(0xFFFFFFFFFFFFF)})
      for(uint64_t sign:{UINT64_C(0),UINT64_C(0x8000000000000000)}) {
        const uint64_t raw=b|fraction|sign;double x;memcpy(&x,&raw,sizeof(x));check(x);
      }
  }
  puts("math helpers: original finite/trunc/floor/ceil bit results, signed zero, subnormal, NaN/Inf and all exponents PASS");
}
