#include "zx0_candidates.hpp"
#include "zx0_prototypes.hpp"
#include "arm_thumb_bcj.hpp"
#include "crc32.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>

namespace k = zx0_candidates;
static u32 random_state = 0xC061F411;
static u32 random_value() {
  random_state ^= random_state << 13; random_state ^= random_state >> 17;
  random_state ^= random_state << 5; return random_state;
}
static u32 checks;
static void fill(u8* p, size_t n, unsigned pattern) {
  for(size_t i=0;i<n;++i) p[i]=pattern==0?'X':pattern==1?(u8)('a'+i%3):
    pattern==2?(u8)(i*73+i/17):pattern==3?(u8)(random_value()%7):(u8)random_value();
}
static void copies() {
  std::vector<u8> original(35000),a,b;
  for(unsigned pattern=0;pattern<5;++pattern) {
    fill(original.data(),original.size(),pattern);
    for(unsigned align=0;align<4;++align) {
      std::vector<unsigned> offsets;
      for(unsigned i=0;i<=64;++i) offsets.push_back(i);
      for(unsigned i:{127U,128U,129U,255U,256U,511U,1024U,32768U}) offsets.push_back(i);
      for(unsigned offset:offsets) {
        std::vector<unsigned> lengths;
        for(unsigned i=0;i<=65;++i)lengths.push_back(i);
        for(unsigned i:{127U,128U,129U,255U,256U,257U,512U,1024U})lengths.push_back(i);
        for(unsigned length:lengths) {
          const unsigned position=offset+align+4;
          a=original;b=original;u8* x=a.data()+position;u8* y=b.data()+position;
          assert(k::copy_scalar(x,a.data(),a.data()+position+length,offset,length));
          assert(k::copy_word(y,b.data(),b.data()+position+length,offset,length));
          assert(x-a.data()==y-b.data()&&a==b);++checks;
        }
      }
    }
  }
  std::array<u8,64> data;data.fill(0xA7);auto old=data;
  u8* p=data.data()+16;
  assert(!k::copy_word(p,data.data(),data.data()+32,17,1));
  assert(p==data.data()+16&&data==old);
  assert(!k::copy_word(p,data.data(),data.data()+32,1,17));
  assert(p==data.data()+16&&data==old);
}
static void matches() {
  std::vector<u8> input(9000);
  for(unsigned pattern=0;pattern<5;++pattern) {
    fill(input.data(),input.size(),pattern);
    for(unsigned align=0;align<4;++align)for(unsigned size=0;size<=513;++size) {
      const unsigned position=256+align;
      for(unsigned offset=1;offset<=256;++offset) {
        assert(k::match_scalar(input.data(),(u16)(position+size),(u16)position,(u16)offset)==
               k::match_word(input.data(),(u16)(position+size),(u16)position,(u16)offset));++checks;
      }
    }
  }
}
static void lcp() {
  std::array<u8,1024> input;
  std::array<u16,257> initial,a,b,c;
  for(unsigned pattern=0;pattern<5;++pattern) {
    fill(input.data(),input.size(),pattern);
    for(unsigned align=0;align<4;++align)for(unsigned position=0;position<=513;++position) {
      for(auto& value:initial)value=(u16)(random_value()%8192);
      a=b=c=initial;u16 an,af,bn,bf,cn,cf;
      k::lcp_scalar(input.data()+align,(u16)position,a.data(),an,af);
      k::lcp_blocks<false>(input.data()+align,(u16)position,b.data(),bn,bf);
      k::lcp_blocks<true>(input.data()+align,(u16)position,c.data(),cn,cf);
      assert(a==b&&a==c&&an==bn&&an==cn&&af==bf&&af==cf);++checks;
    }
  }
  for(unsigned mask=0;mask<16;++mask)for(unsigned value=0;value<256;++value) {
    u32 difference=0;
    for(unsigned lane=0;lane<4;++lane)if(mask&(1U<<lane))
      difference|=(u32)(value?value:1)<<(lane*8);
    u32 expected=0;
    for(unsigned lane=0;lane<4;++lane)if(!(mask&(1U<<lane)))expected|=0xFFU<<(lane*8);
    assert(k::equal_byte_mask<false>(difference)==expected);
    assert(k::equal_byte_mask<true>(difference)==expected);++checks;
  }
}
struct Source { const u8* bytes; size_t size,position,limit; };
static bool read(void* context,u8& value) {
  auto& s=*(Source*)context;
  if(s.position==s.size||s.position==s.limit)return false;
  value=s.bytes[s.position++];return true;
}
struct Sink { std::vector<u8> bytes;size_t limit; };
static bool write(void* context,u8 value) {
  auto& s=*(Sink*)context;if(s.bytes.size()==s.limit)return false;
  s.bytes.push_back(value);return true;
}
static const zx0_prototypes::Decode decoders[]={zx0::decode,zx0_prototypes::decode_scalar,
  zx0_prototypes::decode_word,zx0_prototypes::decode_dsp};
static const zx0_prototypes::Encode encoders[]={zx0::encode,zx0_prototypes::encode_scalar,
  zx0_prototypes::encode_word,zx0_prototypes::encode_dsp};
static void decode_compare(const std::vector<u8>& packed,unsigned capacity,unsigned align=0,
                           size_t limit=1000000) {
  std::vector<u8> reference(capacity+8,0xA7);u32 count=123;Source source={packed.data(),packed.size(),0,limit};
  const zx0::Input input={&source,read};
  const bool ok=decoders[0](input,(u32)packed.size(),reference.data()+align,capacity,count);
  for(unsigned variant=1;variant<4;++variant) {
    std::vector<u8> actual(capacity+8,0xA7);u32 written=123;Source next={packed.data(),packed.size(),0,limit};
    const zx0::Input in={&next,read};
    assert(decoders[variant](in,(u32)packed.size(),actual.data()+align,capacity,written)==ok);
    assert(written==count&&actual==reference&&source.position==next.position);++checks;
  }
}
static std::vector<u8> codec_compare(const std::vector<u8>& raw,unsigned workspace,unsigned align=0,
                                    size_t limit=1000000) {
  std::vector<u8> first;bool first_ok=false;zx0::EncodeResult first_result={};
  for(unsigned variant=0;variant<4;++variant) {
    std::vector<u8> work(workspace+8,0xA7);Sink sink={{},limit};zx0::EncodeResult result={};
    const zx0::Output output={&sink,write};
    const bool ok=encoders[variant](raw.data(),(u32)raw.size(),work.data()+align,workspace,output,result);
    for(unsigned i=0;i<align;++i)assert(work[i]==0xA7);
    for(size_t i=align+workspace;i<work.size();++i)assert(work[i]==0xA7);
    if(!variant) {first=sink.bytes;first_ok=ok;first_result=result;}
    else {assert(ok==first_ok&&first==sink.bytes&&result.mode==first_result.mode&&result.output_size==first_result.output_size);++checks;}
  }
  if(first_ok) {
    for(unsigned a=0;a<4;++a)decode_compare(first,(unsigned)raw.size(),a);
    decode_compare(first,0);decode_compare(first,(unsigned)raw.size()-1);
    decode_compare(first,(unsigned)raw.size()+1);
  }
  return first;
}
static void codecs() {
  for(unsigned pattern=0;pattern<5;++pattern) {
    for(unsigned n:{1U,2U,3U,4U,7U,8U,15U,16U,31U,32U,63U,64U,127U,128U,257U,513U}) {
      std::vector<u8> input(n);fill(input.data(),n,pattern);
      const auto packed=codec_compare(input,4*(n+1)+128,n%4);
      if(n<=64) {
        for(unsigned cut=0;cut<packed.size();++cut) {
          decode_compare(std::vector<u8>(packed.begin(),packed.begin()+cut),n);
          decode_compare(packed,n,0,cut);
        }
      }
      if(n==513) {
        codec_compare(input,512,1);
        codec_compare(input,4*(n+1)+128,3,0);
        codec_compare(input,4*(n+1)+128,2,packed.size()/2);
      }
    }
  }
  for(unsigned test=0;test<5000;++test) {
    const unsigned n=test%65;std::vector<u8> packed(n);
    fill(packed.data(),n,4);decode_compare(packed,test%257,test%4);
  }
  std::vector<u8> large(8192,'x');codec_compare(large,4*(8192+1)+128);
}
static void guarded() {
  const size_t page=(size_t)sysconf(_SC_PAGESIZE);
  auto* mapping=(u8*)mmap(nullptr,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);
  assert(mapping!=MAP_FAILED&&mprotect(mapping+page,page,PROT_READ|PROT_WRITE)==0);
  u8* const end=mapping+page*2;
  for(unsigned n=0;n<=513;++n)for(unsigned offset=1;offset<=64;++offset) {
    u8* const start=end-n-offset;fill(start,n+offset,2);
    std::vector<u8> expected(start,end);u8* old=expected.data()+offset;
    assert(k::copy_scalar(old,expected.data(),expected.data()+expected.size(),offset,n));
    u8* out=end-n;assert(k::copy_word(out,start,end,offset,n));assert(out==end);
    assert(std::memcmp(start,expected.data(),expected.size())==0);++checks;
    fill(start,n+offset,offset%5);
    assert(k::match_scalar(start,(u16)(n+offset),(u16)offset,(u16)offset)==
           k::match_word(start,(u16)(n+offset),(u16)offset,(u16)offset));++checks;
  }
  assert(munmap(mapping,page*3)==0);
}
static u32 little32(const u8* p) {
  return p[0]|((u32)p[1]<<8)|((u32)p[2]<<16)|((u32)p[3]<<24);
}
static void app_stream(const char* path) {
  std::ifstream file(path,std::ios::binary);assert(file);
  const std::vector<u8> app((std::istreambuf_iterator<char>(file)),{});
  assert(app.size()>=64&&app[15]==1);
  const unsigned n=little32(app.data()+28);
  const unsigned stored=app[12]<6?little32(app.data()+24):little32(app.data()+40);
  assert(n&&n<=65536&&stored&&stored<=app.size()-64);
  std::vector<u8> packed(app.begin()+64,app.begin()+64+stored);
  for(unsigned align=0;align<4;++align)decode_compare(packed,n,align);
  std::vector<u8> raw(n);Source source={packed.data(),packed.size(),0,packed.size()};
  const zx0::Input input={&source,read};u32 written=0;
  assert(zx0::decode(input,stored,raw.data(),n,written)&&written==n);
  if(little32(app.data()+16)&2)arm_thumb_bcj::transform(raw.data(),n,false);
  assert(mk61_crc32::finish(mk61_crc32::extend(mk61_crc32::INITIAL_STATE,raw.data(),n))==little32(app.data()+52));
  std::printf("Actual APP stream %s: %u -> %u bytes, all prototypes and image CRC PASS\n",path,stored,n);
}
int main(int argc,char** argv) {
  copies();matches();lcp();guarded();codecs();
  for(int i=1;i<argc;++i)app_stream(argv[i]);
  std::printf("ZX0 prototypes: %u differential/bounds checks PASS; complete streams byte-identical\n",checks);
}
