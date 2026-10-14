#include "vm_scan_candidates.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <vector>

namespace c = vm_scan_candidates;
static void check(const uint8_t* p, const uint8_t* q, size_t n) {
  assert(c::line_scalar(p,n) == c::line_word(p,n));
  assert(c::line_scalar(p,n) == c::line_dsp(p,n));
  assert(c::spaces_scalar(p,n) == c::spaces_word(p,n));
  assert(c::spaces_scalar(p,n) == c::spaces_dsp(p,n));
  assert(c::alpha_scalar(p,n) == c::alpha_word(p,n));
  assert(c::alpha_scalar(p,n) == c::alpha_dsp(p,n));
  assert(c::upper_equal_scalar(p,q,n) == c::upper_equal_word(p,q,n));
  assert(c::upper_equal_scalar(p,q,n) == c::upper_equal_dsp(p,q,n));
  assert(c::equal_scalar(p,q,n) == c::equal_word(p,q,n));
  assert(c::equal_scalar(p,q,n) == c::equal_dsp(p,q,n));
}
int main() {
  // Every adjacent byte pair in every lane catches borrow/carry mistakes,
  // including high M8 bytes and bytes next to spaces, CR, LF and ASCII letters.
  for(unsigned a=0;a<256;++a) for(unsigned b=0;b<256;++b) {
    for(unsigned lane=0;lane<4;++lane) {
      std::array<uint8_t,8> p{' ','\t','\r','\n','a','Z',0x80,0xFF}, q{};
      p[lane]=(uint8_t)a; p[lane+1]=(uint8_t)b;
      for(unsigned i=0;i<p.size();++i) q[i]=c::upper(p[i]);
      check(p.data(),q.data(),p.size());
      const uint32_t word=c::load(p.data());
      uint32_t zero=0,alpha=0;
      for(unsigned i=0;i<4;++i) {
        if(!p[i]) zero |= 0x80U<<(i*8);
        if(c::alpha(p[i])) alpha |= 0x80U<<(i*8);
      }
      assert(c::zero_mask(word)==zero);
      assert(c::alpha_mask_word(word)==alpha);
      assert((c::alpha_mask_dsp(word)&0x80808080U)==alpha);
    }
  }
  uint32_t random=0x61F411;
  for(unsigned alignment=0;alignment<4;++alignment) {
    for(size_t n=0;n<=260;++n) {
      std::vector<uint8_t> p(n+alignment+(n==0));
      for(unsigned q_alignment=0;q_alignment<4;++q_alignment) {
        std::vector<uint8_t> q(n+q_alignment+(n==0));
        for(unsigned mode=0;mode<7;++mode) {
          for(size_t i=0;i<n;++i) {
            random^=random<<13;random^=random>>17;random^=random<<5;
            const uint8_t value=mode==0 ? ' ' : mode==1 ? '\t' : mode==2 ? 'a' :
              mode==3 ? 'Z' : mode==4 ? '\r' : mode==5 ? '\n' : (uint8_t)random;
            p[alignment+i]=value;q[q_alignment+i]=c::upper(value);
          }
          check(p.data()+alignment,q.data()+q_alignment,n);
          for(size_t at=0;at<n;++at) {
            const uint8_t old=p[alignment+at];
            p[alignment+at]=(uint8_t)(old^1);
            check(p.data()+alignment,q.data()+q_alignment,n);
            p[alignment+at]=old;
          }
        }
      }
    }
  }
  std::puts("VM scans: exhaustive byte-pair masks, all alignments and exact allocation tails PASS");
}
