#include "bench.h"
#include <limits.h>
static int oracle(const st_case* c,int32_t* offset) {
  if(!c->text || c->text_bytes>INT32_MAX)return 0;
  *offset=-1;
  for(size_t i=0;i<c->text_bytes;++i) {
    const unsigned char value=(unsigned char)c->text[i];
    if(*offset<0 && value==(unsigned char)c->character)*offset=(int32_t)i;
    if(!value)return 1;
  }
  return 0;
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noipa))
#else
__attribute__((noinline))
#endif
int st_measure(const st_case* c,st_search search,st_tick tick,st_samples* out) {
  if(!out)return 1;
  out->version=1;out->status=1;out->completed_rounds=0;
  out->oracle_offset=-2;out->before=out->after=out->mismatch=0;
  for(unsigned i=0;i<ST_ROUNDS;++i)out->raw[i]=0;
  if(!c || !search || !tick || !c->repeats || c->repeats>ST_MAX_REPEATS)return 1;
  if(!oracle(c,&out->oracle_offset) || out->oracle_offset!=c->expected_offset){out->status=2;return 2;}
  const uintptr_t expected=out->oracle_offset<0?0:(uintptr_t)(c->text+out->oracle_offset);
  for(unsigned round=0;round<ST_ROUNDS;++round) {
    out->before=(uintptr_t)search(c->text,c->character);
    if(out->before!=expected){out->status=3;return 3;}
    uintptr_t mismatch=0;
    __asm__ volatile("":::"memory");
    const uint32_t begin=tick();
    for(unsigned i=0;i<c->repeats;++i)mismatch|=(uintptr_t)search(c->text,c->character)^expected;
    const uint32_t end=tick();
    __asm__ volatile("":::"memory");
    out->raw[round]=end-begin;out->mismatch=mismatch;
    out->after=(uintptr_t)search(c->text,c->character);
    if(out->after!=expected || mismatch){out->status=3;return 3;}
    if(!out->raw[round] || out->raw[round]>=0x80000000u){out->status=4;return 4;}
    ++out->completed_rounds;
  }
  out->status=0;return 0;
}
