#include "zx0_candidates.hpp"
#include "zx0_hil_transport.hpp"
namespace k=zx0_candidates;
alignas(4) static u8 input[1040],output[1040],expected[1040];
alignas(4) static u16 lcp[257],oracle_lcp[257];
struct Job {unsigned family,size,parameter,pattern,align;};
using Kernel=u32(*)(const Job&);
#define KERNEL __attribute__((noipa,aligned(16),optimize("Os")))
extern "C" KERNEL u32 zx0_copy_scalar(const Job& j) {
  u8* p=output+260+j.align;
  return k::copy_scalar(p,output,p+j.size,j.parameter,j.size)?(u32)(p-output):0;
}
extern "C" KERNEL u32 zx0_copy_word(const Job& j) {
  u8* p=output+260+j.align;
  return k::copy_word(p,output,p+j.size,j.parameter,j.size)?(u32)(p-output):0;
}
extern "C" KERNEL u32 zx0_match_scalar(const Job& j) {
  return k::match_scalar(input+j.align,(u16)(256+j.size),256,256);
}
extern "C" KERNEL u32 zx0_match_word(const Job& j) {
  return k::match_word(input+j.align,(u16)(256+j.size),256,256);
}
extern "C" KERNEL u32 zx0_lcp_scalar(const Job& j) {
  u16 a,b;k::lcp_scalar(input+j.align,(u16)j.size,lcp,a,b);return a|((u32)b<<16);
}
extern "C" KERNEL u32 zx0_lcp_word(const Job& j) {
  u16 a,b;k::lcp_blocks<false>(input+j.align,(u16)j.size,lcp,a,b);return a|((u32)b<<16);
}
extern "C" KERNEL u32 zx0_lcp_dsp(const Job& j) {
  u16 a,b;k::lcp_blocks<true>(input+j.align,(u16)j.size,lcp,a,b);return a|((u32)b<<16);
}
static const Kernel functions[][3]={{zx0_copy_scalar,zx0_copy_word,nullptr},
  {zx0_match_scalar,zx0_match_word,nullptr},{zx0_lcp_scalar,zx0_lcp_word,zx0_lcp_dsp}};
static u32 rng=1;
static u32 random_value() {rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void prepare(const Job& j) {
  rng=0xC061F411;
  for(unsigned i=0;i<sizeof(input);++i) {
    const u8 value=j.family==2?(j.pattern==0?'A':j.pattern==1?'A':j.pattern==2?(u8)(random_value()%2):(u8)random_value()):
      (u8)('a'+(i-j.align)%16);
    input[i]=value;output[i]=(u8)(i*73+i/17);
  }
  if(j.family==1&&j.size&&j.pattern) {
    const unsigned at=j.pattern==1?0:j.pattern==2?(j.size>3?3:j.size-1):j.size-1;
    input[j.align+256+at]^=0x80;
  }
  if(j.family==2&&j.pattern==1)input[j.align+j.size]='B';
  for(unsigned i=0;i<257;++i)lcp[i]=(u16)((i*31)%128);
}
static void measure(const Job& j,unsigned variant) {
  prepare(j);const auto function=functions[j.family][variant];
  u32 wanted;
  if(j.family==0) {
    memcpy(expected,output,sizeof(output));u8* p=expected+260+j.align;
    if(!k::copy_scalar(p,expected,p+j.size,j.parameter,j.size))++failures;
    wanted=(u32)(p-expected);
  } else if(j.family==1)wanted=zx0_match_scalar(j);
  else {
    memcpy(oracle_lcp,lcp,sizeof(lcp));u16 a,b;
    k::lcp_scalar(input+j.align,(u16)j.size,oracle_lcp,a,b);wanted=a|((u32)b<<16);
  }
  const u32 actual=function(j);
  if(actual!=wanted||(j.family==0&&memcmp(output,expected,sizeof(output)))||
     (j.family==2&&memcmp(lcp,oracle_lcp,sizeof(lcp))))++failures;
  const unsigned iterations=j.family==2?32:128;u32 times[7];
  for(unsigned sample=0;sample<7;++sample) {
    prepare(j);for(unsigned i=0;i<2;++i)checksum+=function(j);
    const u32 start=cycles();for(unsigned i=0;i<iterations;++i)checksum+=function(j);
    times[sample]=cycles()-start;mk61_api->service();
  }
  row(variant,j.align,iterations,times);
}
static void benchmark(unsigned index) {
  const auto& c=bench_cases[index];const unsigned count=c.family==2?3:2;
  for(unsigned align=0;align<4;++align)for(unsigned order=0;order<count;++order)
    measure({c.family,c.size,c.parameter,c.pattern,align},(index+order)%count);
}
static void native_checks() {
  for(unsigned mask=0;mask<16;++mask)for(unsigned value=1;value<=255;++value) {
    u32 difference=0,wanted=0;
    for(unsigned lane=0;lane<4;++lane) {
      if(mask&(1U<<lane))difference|=value<<(lane*8);else wanted|=0xFFU<<(lane*8);
    }
    if(k::equal_byte_mask<true>(difference)!=wanted)++failures;
  }
  for(unsigned p=0;p<=513;++p)for(unsigned pattern=0;pattern<4;++pattern) {
    const Job j={2,p,0,pattern,p%4};prepare(j);
    memcpy(oracle_lcp,lcp,sizeof(lcp));u16 a,b;
    k::lcp_scalar(input+j.align,(u16)p,oracle_lcp,a,b);
    if(zx0_lcp_dsp(j)!=(a|((u32)b<<16))||memcmp(lcp,oracle_lcp,sizeof(lcp)))++failures;
    if((p&31)==0)mk61_api->service();
  }
}
