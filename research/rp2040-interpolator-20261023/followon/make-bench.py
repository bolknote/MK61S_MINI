#!/usr/bin/env python3
from pathlib import Path
import re
from generate import extract
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=(ROOT/'.build/rp2040-interpolator-20261023/combined-v3-v1/math/source/benchmark.c').read_text()
source=source.replace('#include "kernels.h"','#include "kernels.h"\n#include "api.h"\n#include "vectors.h"')
source=source.replace('"/INTRP01"','"/INTRP02"')
begin=source.index('#if INTERP_VARIANT==1');end=source.index('enum {ROUNDS=',begin)
source=source[:begin]+'''#if INTERP_VARIANT==1
#define FIRST_GROUP 0
#define LOCAL_GROUPS 1
#elif INTERP_VARIANT==2
#define FIRST_GROUP 1
#define LOCAL_GROUPS 2
#elif INTERP_VARIANT==3
#define FIRST_GROUP 3
#define LOCAL_GROUPS 2
#elif INTERP_VARIANT==4
#define FIRST_GROUP 5
#define LOCAL_GROUPS 2
#endif
'''+source[end:]
source=source.replace(extract(source,'fill'),'''static void fill(unsigned group,unsigned kind) {
  uint32_t random=0x725abc11U+kind*37U;
  for(unsigned i=0;i<STREAM;++i) {
    if(group==1 || group==2) {
      inputs[i].a=((uint64_t)random32(&random)<<32)|random32(&random);
      inputs[i].b=kind==0?32:kind==1?256:1024;
    } else {inputs[i].a=fo_inputs[kind][i];inputs[i].b=0;}
  }
}
''')
begin=source.index('#if INTERP_VARIANT==1',source.index('static void fill'))
end=source.index('static __attribute__((noipa)) uint64_t identity',begin)
source=source[:begin]+'''#if INTERP_VARIANT==1
static UnaryPair* const left[]={fo_ln_cpu};
static UnaryPair* const right[]={fo_ln_interp};
#elif INTERP_VARIANT==2
static UnaryPair* const left[]={fo_texture_cpu,fo_audio_cpu};
static UnaryPair* const right[]={fo_texture_pop,fo_audio_interp};
#elif INTERP_VARIANT==3
static UnaryPair* const left[]={fo_sqrt_base,fo_sqrt_base};
static UnaryPair* const right[]={fo_sqrt_new_cpu,fo_sqrt_new_interp};
#elif INTERP_VARIANT==4
static UnaryPair* const left[]={fo_rsqrt_base,fo_rsqrt_base};
static UnaryPair* const right[]={fo_rsqrt_new_cpu,fo_rsqrt_new_interp};
#endif
static void setup(unsigned group) {
#if INTERP_VARIANT==1
  (void)group;fo_lookup_setup();
#elif INTERP_VARIANT==2
  if(group==1)fo_texture_setup();else fo_audio_setup();
#else
  (void)group;fo_root_setup();
#endif
}
'''+source[end:]
scalar=extract(source,'time_batch')
pop='''static uint32_t time_batch(UnaryPair* function,unsigned group,unsigned mode,int hardware) {
  uint32_t elapsed=0,sum=0;
  if(hardware && !mode)setup(group);
  for(unsigned k=0;k<SAMPLES;++k) {
    const Pair in=inputs[k&(STREAM-1)];uint64_t result;const uint32_t start=micros();
    if(hardware && mode){State state;save(&state);setup(group);result=function(in.a,in.b);restore(&state);}
    else result=function(in.a,in.b);
    elapsed+=micros()-start;
    // Whole output validation and hashing deliberately follow the stop timer.
    if(function!=identity) {
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
      const uint32_t bytes=(unsigned)in.b*(group==2?2:1);
      sum=interp_checksum_step(sum,((uint64_t)fo_pop_hash(bytes)<<32)|(uint32_t)(result^(result>>32)),k);
    } else sum=interp_checksum_step(sum,result,k);
    mk61_api->service();
  }
  sink=sum;last_checksum=sum;
  restore(&output.state_before);restore_divider(output.divider_before);
  State now;save(&now);if(!same(&now,&output.state_before))++output.failures;
  return elapsed;
}
'''
source=source.replace(scalar,'#if INTERP_VARIANT==2\n'+pop+'#else\n'+scalar+'#endif\n')
source=source.replace(extract(source,'correctness'),'''static void correctness(void) {
  for(unsigned local=0;local<GROUPS;++local)for(unsigned kind=0;kind<CASES;++kind) {
    const unsigned group=FIRST_GROUP+local;fill(group,kind);setup(group);
    for(unsigned i=0;i<STREAM;++i) {
      const Pair in=inputs[i];const uint64_t a=left[local](in.a,in.b);
#if INTERP_VARIANT==2
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
#endif
      const uint64_t b=right[local](in.a,in.b);
#if INTERP_VARIANT==2
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
#endif
      ++output.checks;if(a!=b)++output.failures;
#if INTERP_VARIANT==3
      if(a!=fo_sqrt_expected[kind][i])++output.failures;
#elif INTERP_VARIANT==4
      if(a!=fo_rsqrt_expected[kind][i])++output.failures;
#endif
    }
    restore(&output.state_before);restore_divider(output.divider_before);mk61_api->service();
  }
}
''')
source=source.replace('output.magic=0x31505249;output.version=3;', 'output.magic=0x324f4649;output.version=4;')
source=source.replace('const int hw=b && group!=3 && group!=5;', 'const int hw=b && group!=3 && group!=5;')
source=source.replace('if((group<3 || group>6) && row->checksum[r][0]!=row->checksum[r][1])', 'if(row->checksum[r][0]!=row->checksum[r][1])')
(HERE/'benchmark.c').write_text(source)
