#include "m8_conversion_candidates.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>
namespace old=m8_conversion_reference;
namespace fast=m8_conversion_candidates;
using Convert=bool(*)(const void*,usize,void*,usize,usize&);
#define WRAP(name,ns) \
static bool name##_to8(const void* p,usize n,void* q,usize c,usize& w){return ns::to_utf8((const u8*)p,n,(u8*)q,c,w);} \
static bool name##_from8(const void* p,usize n,void* q,usize c,usize& w){return ns::from_utf8((const u8*)p,n,(u8*)q,c,w);} \
static bool name##_to16(const void* p,usize n,void* q,usize c,usize& w){return ns::to_utf16((const u8*)p,n,(u16*)q,c,w);} \
static bool name##_from16(const void* p,usize n,void* q,usize c,usize& w){return ns::from_utf16((const u16*)p,n,(u8*)q,c,w);}
WRAP(legacy,old)
WRAP(mapped,mk8)
namespace words {
inline bool to_utf8(const u8* p,usize n,u8* q,usize c,usize& w){return fast::to_utf8<false>(p,n,q,c,w);}
inline bool from_utf8(const u8* p,usize n,u8* q,usize c,usize& w){return fast::from_utf8<false>(p,n,q,c,w);}
inline bool to_utf16(const u8* p,usize n,u16* q,usize c,usize& w){return fast::to_utf16<false>(p,n,q,c,w);}
inline bool from_utf16(const u16* p,usize n,u8* q,usize c,usize& w){return fast::from_utf16<false>(p,n,q,c,w);}
}
WRAP(word,words)
static const Convert kernels[][3]={{legacy_to8,mapped_to8,word_to8},{legacy_from8,mapped_from8,word_from8},
 {legacy_to16,mapped_to16,word_to16},{legacy_from16,mapped_from16,word_from16}};
static void compare(unsigned family,const void* input,usize n,usize capacity,unsigned align=0) {
  std::array<u16,2048> expected,actual;
  std::memset(expected.data(),0xA7,sizeof(expected));
  const unsigned offset=family==2?align*2:align;
  usize ew=123;
  const bool result=kernels[family][0](input,n,(u8*)expected.data()+offset,capacity,ew);
  for(unsigned v=1;v<3;++v) {
    std::memset(actual.data(),0xA7,sizeof(actual));usize aw=123;
    const bool r=kernels[family][v](input,n,(u8*)actual.data()+offset,capacity,aw);
    assert(r==result&&aw==ew&&std::memcmp(actual.data(),expected.data(),sizeof(actual))==0);
  }
}
int main() {
  for(u32 cp=0;cp<=0x110000;++cp) {
    u8 a=0x5A,b=0x5A;assert(old::from_codepoint(cp,a)==mk8::from_codepoint(cp,b));assert(a==b);
  }
  for(u32 cp:{0xFFFFFFFFU,0xFFFFFFFEU,0x110001U}) {
    u8 a=0x5A,b=0x5A;assert(old::from_codepoint(cp,a)==mk8::from_codepoint(cp,b)&&a==b);
  }
  for(unsigned family=0;family<4;++family)for(unsigned n:{0U,1U})for(unsigned c:{0U,1U})compare(family,nullptr,n,c);
  std::vector<u8> valid;
  for(unsigned byte=0;byte<256;++byte)if(old::valid_byte((u8)byte))valid.push_back((u8)byte);
  for(unsigned n=0;n<=513;++n)for(unsigned pattern=0;pattern<5;++pattern) {
    std::vector<u8> m8(n+8),encoded(n*3+8);std::vector<u16> wide(n+4);
    for(unsigned i=0;i<n;++i)m8[i]=pattern==0?(u8)(' '+i%95):pattern==1?(u8)(0xC0+i%64):
      pattern==2?valid[i%valid.size()]:pattern==3?(u8)(i%4?'A':0xA8):
      (u8)(i%3?0xC0+i%64:old::BYTE_RIGHT_ARROW);
    usize encoded_size=0,wide_size=0;
    assert(old::to_utf8(m8.data(),n,encoded.data(),(usize)encoded.size(),encoded_size));
    assert(old::to_utf16(m8.data(),n,wide.data(),(usize)wide.size(),wide_size));
    for(unsigned align=0;align<4;++align) {
      std::vector<u8> shifted(n+align+4),utf8(encoded_size+align+4);
      if(n)std::memcpy(shifted.data()+align,m8.data(),n);
      if(encoded_size)std::memcpy(utf8.data()+align,encoded.data(),encoded_size);
      for(usize capacity:{0U,1U,2U,3U,n/2,n,n+1,n*3}) {
        compare(0,shifted.data()+align,n,capacity,align);
        compare(1,utf8.data()+align,encoded_size,capacity,align);
        compare(2,shifted.data()+align,n,capacity,align%2);
        compare(3,wide.data(),n,capacity,align);
      }
    }
    if(n<=32)for(unsigned at=0;at<n;++at)for(u8 bad:{(u8)0,(u8)1,(u8)0x7F,(u8)0x98}) {
      const u8 saved=m8[at];m8[at]=bad;compare(0,m8.data(),n,n*3);compare(2,m8.data(),n,n);m8[at]=saved;
    }
  }
  // Exhaustive BMP and byte-pair inputs cover unsupported Unicode, controls,
  // surrogate rejection, overlong sequences and output-prefix semantics.
  for(unsigned cp=0;cp<65536;++cp) {
    u16 v=(u16)cp;compare(3,&v,1,1);
    for(unsigned at=0;at<4;++at) {
      u16 block[]={0x0410,0x042F,0x0430,0x044F};block[at]=v;compare(3,block,4,4);
    }
  }
  for(unsigned pair=0;pair<65536;++pair) {
    const u8 data[]={(u8)pair,(u8)(pair>>8)};compare(1,data,2,2);
    for(unsigned at=0;at<4;++at) {
      u8 block[]={0xD0,0x90,0xD0,0xBF,0xD1,0x80,0xD1,0x8F};
      block[at*2]=data[0];block[at*2+1]=data[1];compare(1,block,8,8);
    }
  }
  u32 rng=0xC061F411;
  for(unsigned test=0;test<10000;++test) {
    const unsigned n=test%33;std::array<u8,40> bytes;std::array<u16,40> units;
    for(unsigned i=0;i<n;++i){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;bytes[i]=(u8)rng;units[i]=(u16)rng;}
    compare(1,bytes.data(),n,n);compare(3,units.data(),n,n);
  }
  const size_t page=(size_t)sysconf(_SC_PAGESIZE);
  auto* a=(u8*)mmap(nullptr,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);
  auto* b=(u8*)mmap(nullptr,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);
  assert(a!=MAP_FAILED&&b!=MAP_FAILED&&mprotect(a+page,page,PROT_READ|PROT_WRITE)==0&&mprotect(b+page,page,PROT_READ|PROT_WRITE)==0);
  for(unsigned n=0;n<=257;++n)for(unsigned pattern=0;pattern<3;++pattern) {
    std::vector<u8> m8(n),utf8(n*3+1);std::vector<u16> utf16(n+1);
    for(unsigned i=0;i<n;++i)m8[i]=pattern==0?'A':pattern==1?(u8)(0xC0+i%64):valid[i%valid.size()];
    usize n8=0,n16=0;assert(old::to_utf8(m8.data(),n,utf8.data(),(usize)utf8.size(),n8));
    assert(old::to_utf16(m8.data(),n,utf16.data(),(usize)utf16.size(),n16));
    for(unsigned family=0;family<4;++family) {
      const unsigned in_size=family==1?n8:family==3?n*2:n;
      const unsigned out_size=family==0?n8:family==2?n*2:n;
      const void* source=family==1?(const void*)utf8.data():family==3?(const void*)utf16.data():m8.data();
      if(in_size)std::memcpy(a+page*2-in_size,source,in_size);
      usize written=0;
      assert(kernels[family][2](a+page*2-in_size,family==1?n8:n,b+page*2-out_size,family==0?n8:n,written));
      assert(written==(family==0?n8:n));
    }
  }
  assert(munmap(a,page*3)==0&&munmap(b,page*3)==0);
  std::puts("M8 conversion: all Unicode/BMP/byte pairs, strict failures, capacity prefixes, alignments and exact guard boundaries PASS");
}
