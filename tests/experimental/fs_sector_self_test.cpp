#include "fs_sector_candidates.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
namespace c=fs_sector_candidates;
static void check(const uint8_t* a,const uint8_t* b,size_t n) {
  const int reference=std::memcmp(a,b,n);
  const bool same=reference==0;
  const auto sign=[](int value){return (value>0)-(value<0);};
  assert(sign(c::compare_scalar(a,b,n))==sign(reference));
  assert(sign(c::compare_word(a,b,n))==sign(reference));
  assert(sign(c::compare_dsp(a,b,n))==sign(reference));
  assert(c::equal_scalar(a,b,n)==same);
  assert(c::equal_word_early(a,b,n)==same);
  assert(c::equal_word_full(a,b,n)==same);
  assert(c::equal_dsp_early(a,b,n)==same);
  assert(c::equal_dsp_full(a,b,n)==same);
}
int main() {
  uint32_t random=0x61F411;
  for(unsigned aa=0;aa<4;++aa) for(unsigned ba=0;ba<4;++ba) {
    for(size_t n=0;n<=513;++n) {
      std::vector<uint8_t> a(n+aa+!n),b(n+ba+!n),out(n+ba+!n);
      uint8_t* left=a.data()+aa;uint8_t* right=b.data()+ba;uint8_t* dest=out.data()+ba;
      for(size_t i=0;i<n;++i) {
        random^=random<<13;random^=random>>17;random^=random<<5;
        left[i]=(uint8_t)random;right[i]=left[i];
      }
      check(left,right,n);
      for(size_t at=0;at<n;++at) {
        right[at]^=1;check(left,right,n);right[at]^=1;
      }
      c::copy_scalar(dest,left,n);assert(std::memcmp(dest,left,n)==0);
      std::memset(dest,0xA5,n);c::copy_word(dest,left,n);assert(std::memcmp(dest,left,n)==0);
      std::memset(dest,0xA5,n);c::copy_word_unrolled(dest,left,n);assert(std::memcmp(dest,left,n)==0);
    }
  }
  // Exercise maximum lane differences and the DSP accumulation bound.
  std::vector<uint8_t> a(1024,0),b(1024,255);
  for(size_t n:{size_t(4),size_t(511),size_t(512),size_t(513),size_t(1024)}) check(a.data(),b.data(),n);
  std::puts("Sector kernels: all alignments, mismatch positions and exact tails PASS");
}
