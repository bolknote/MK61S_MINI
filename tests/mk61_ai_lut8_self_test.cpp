#include "mk61_ai_kernels.h"
#include "../examples/portable-apps/MK61AI/m3_q4_kernels.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>

int main() {
  std::mt19937 rng(0x544d4143);
  unsigned rows=0;
  for(unsigned sample=0;sample<512;++sample) {
    int8_t x[32];
    for(auto &v:x) v=sample<4?int8_t(sample==0?-128:sample==1?127:sample==2?0:1):int8_t(rng());
    mk61ai_lut32 small{};mk61ai_lut8x32 large{};
    uint32_t xp[16];const auto sum=ai_m3_pack_swar_a8_32(x,xp);
    mk61ai_prepare_lut32(x,&small);mk61ai_prepare_lut8x32(x,&large);
    for(unsigned g=0;g<4;++g)for(unsigned mask=0;mask<256;++mask) {
      int expected=0;
      for(unsigned j=0;j<8;++j)if(mask&(1U<<j))expected+=x[8*g+j];
      assert(large.subset[g][mask]==expected);
    }
    assert(small.sum==large.sum);
    for(unsigned row=0;row<32;++row) {
      uint8_t codes[16],planes[16];
      for(auto &v:codes)v=sample<4?uint8_t(row<16?row*17:rng()):uint8_t(rng());
      mk61ai_pack_q4_planes32(codes,planes);
      int64_t expected=0;
      for(unsigned j=0;j<32;++j)expected+=(int((codes[j/2]>>(4*(j&1)))&15)-8)*int(x[j]);
      assert(mk61ai_dot_q4_a8_32(codes,x)==expected);
      assert(mk61ai_dot_lut_q4_a8_32(planes,&small)==expected);
      assert(mk61ai_dot_lut8_q4_a8_32(planes,&large)==expected);
      assert(ai_m3_dot1_a8_32(codes,x)==expected);
      assert(ai_m3_swar_a8_32(codes,xp,sum)==expected);
      uint8_t other[16];for(auto &v:other)v=uint8_t(rng());
      int32_t pair[2];ai_m3_dot2_a8_32(codes,other,x,pair);
      assert(pair[0]==expected && pair[1]==mk61ai_dot_q4_a8_32(other,x));
      ++rows;
    }
  }
  std::printf("LUT8/M3 HOST PASS: %u exact int64 rows; 524288 subset controls; direct1/direct2/SWAR exact; table sizes %zu/%zu bytes\n",
              rows,sizeof(mk61ai_lut32),sizeof(mk61ai_lut8x32));
}
