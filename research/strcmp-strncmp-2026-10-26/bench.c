#include "bench.h"
#if defined(__GNUC__) && !defined(__clang__)
#define SC_NOINLINE __attribute__((noipa))
#else
#define SC_NOINLINE __attribute__((noinline))
#endif
static int sign(int value) {return (value>0)-(value<0);}
static int oracle(const sc_case* c,int* value) {
  for(size_t i=0;!c->bounded || i<c->n;++i) {
    if(i>=c->left_bytes || i>=c->right_bytes)return 0;
    const unsigned x=(unsigned char)c->left[i],y=(unsigned char)c->right[i];
    if(x!=y || !x){*value=(x>y)-(x<y);return 1;}
  }
  *value=0;return 1;
}
static int invoke(const sc_case* c,const sc_route* r) {
  return c->bounded?r->bounded(c->left,c->right,c->n):r->compare(c->left,c->right);
}
SC_NOINLINE int sc_measure(const sc_case* c,const sc_route* route,sc_tick tick,sc_samples* out) {
  if(!out)return 1;
  out->version=1;out->status=1;out->completed_rounds=0;
  out->oracle_sign=out->pre_sign=out->post_sign=0;out->checksum=0;
  for(unsigned i=0;i<SC_ROUNDS;++i)out->raw[i]=0;
  if(!c || !route || !tick || c->bounded>1 || !c->repeats || c->repeats>SC_MAX_REPEATS ||
     (c->bounded?!route->bounded:!route->compare))return 1;
  if(!oracle(c,&out->oracle_sign) || out->oracle_sign!=c->expected_sign){out->status=2;return 2;}
  for(unsigned round=0;round<SC_ROUNDS;++round) {
    out->pre_sign=sign(invoke(c,route));
    if(out->pre_sign!=out->oracle_sign){out->status=3;return 3;}
    uint32_t checksum=0;
    __asm__ volatile("":::"memory");
    const uint32_t begin=tick();
    if(c->bounded) {
      sc_ncmp f=route->bounded;
      for(unsigned i=0;i<c->repeats;++i)checksum|=(uint32_t)f(c->left,c->right,c->n);
    } else {
      sc_cmp f=route->compare;
      for(unsigned i=0;i<c->repeats;++i)checksum|=(uint32_t)f(c->left,c->right);
    }
    const uint32_t end=tick();
    __asm__ volatile("":::"memory");
    out->raw[round]=end-begin;out->checksum=checksum;
    out->post_sign=sign(invoke(c,route));
    if(out->post_sign!=out->oracle_sign || sign((int32_t)checksum)!=out->oracle_sign){out->status=3;return 3;}
    if(!out->raw[round]){out->status=4;return 4;}
    ++out->completed_rounds;
  }
  out->status=0;return 0;
}
