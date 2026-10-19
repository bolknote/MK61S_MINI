#include "language_value.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include <limits>

using language_vm::Value;

// Keep the original 64-bit algorithm independent of the new 32-bit limbs.
// Compare the wire representation, including signed zero and NaN payloads;
// numeric equality alone would not detect a changed tag or lost negative zero.
static uint64_t reference(uint64_t bits) {
  const uint64_t magnitude=bits&UINT64_C(0x7FFFFFFFFFFFFFFF);
  if(!magnitude)return bits?bits:uint64_t(Value::INTEGER_TAG)<<32;
  const unsigned exponent=unsigned(magnitude>>52);
  if(exponent>=1023 && exponent<=1054) {
    const unsigned shift=1075-exponent;
    const uint64_t mantissa=(magnitude&UINT64_C(0x000FFFFFFFFFFFFF))|(UINT64_C(1)<<52);
    const uint64_t whole=mantissa>>shift;
    if(!(mantissa&((UINT64_C(1)<<shift)-1)) && whole<=((bits>>63)?UINT64_C(2147483648):UINT64_C(2147483647)))
      return (uint64_t(Value::INTEGER_TAG)<<32)|((bits>>63)?uint32_t(0)-uint32_t(whole):uint32_t(whole));
  }
  return uint32_t(bits>>32)==Value::INTEGER_TAG?UINT64_C(0x7FF8000000000000):bits;
}

int main() {
  unsigned cases=0;
  auto check=[&](uint64_t bits) {
    const auto got=Value(mk_math::bit_copy<double>(bits)).representation();
    if(got!=reference(bits)) {
      std::fprintf(stderr,"boxing mismatch %016llx -> %016llx expected %016llx\n",
        (unsigned long long)bits,(unsigned long long)got,(unsigned long long)reference(bits));
      assert(false);
    }
    ++cases;
  };
  uint64_t random=UINT64_C(0xBA61802561F411);
  for(unsigned i=0;i<2000000;++i) {
    random^=random<<13;random^=random>>7;random^=random<<17;check(random);
    if(i<100000) {
      const double d=double(mk_math::bit_copy<int32_t>(uint32_t(random)));
      check(mk_math::bit_copy<uint64_t>(d));
      check(mk_math::bit_copy<uint64_t>(std::nextafter(d,std::numeric_limits<double>::infinity())));
      check(mk_math::bit_copy<uint64_t>(std::nextafter(d,-std::numeric_limits<double>::infinity())));
    }
  }
  for(unsigned exponent=0;exponent<2048;++exponent)for(unsigned sign=0;sign<2;++sign)
    for(uint64_t fraction:{UINT64_C(0),UINT64_C(1),UINT64_C(0x7FFFFFFFFFFFF),UINT64_C(0xFFFFFFFFFFFFF)})
      check((uint64_t(sign)<<63)|(uint64_t(exponent)<<52)|fraction);
  for(unsigned low=0;low<65536;++low)check((uint64_t(Value::INTEGER_TAG)<<32)|low);
  std::printf("Value boxing: %u bit-exact comparisons with original 64-bit algorithm PASS\n",cases);
}
