#include "bench.h"
#include <assert.h>
#include <stdio.h>
static unsigned calls,ticks,zero_tick;
static uint32_t clock_tick(void) {++ticks;return zero_tick?0:0xffffffe8u+ticks*16u;}
static int cmp(const char* a,const char* b) {++calls;return (unsigned char)*a-(unsigned char)*b;}
static int ncmp(const char* a,const char* b,size_t n) {++calls;return n?((unsigned char)*a-(unsigned char)*b):0;}
static int wrong(const char* a,const char* b) {(void)a;(void)b;++calls;return 0;}
int main(void) {
  sc_samples out;sc_route route={cmp,ncmp};
  sc_case c={"\xff","\x7f",2,2,1,0,64,1};
  assert(!sc_measure(&c,&route,clock_tick,&out));
  assert(calls==7*(64+2) && ticks==14 && out.completed_rounds==7);
  for(unsigned i=0;i<7;++i)assert(out.raw[i]==16); /* Includes tick wrap. */
  c.bounded=1;c.expected_sign=-1;c.left="\x7f";c.right="\xff";
  calls=ticks=0;assert(!sc_measure(&c,&route,clock_tick,&out));
  assert(calls==7*(64+2) && out.oracle_sign==-1);
  c.n=0;c.left=c.right=0;c.left_bytes=c.right_bytes=0;c.expected_sign=0;
  calls=ticks=0;assert(!sc_measure(&c,&route,clock_tick,&out));
  assert(calls==7*(64+2));
  c=(sc_case){"A","B",2,2,1,0,64,-1};route.compare=wrong;
  calls=ticks=0;assert(sc_measure(&c,&route,clock_tick,&out)==3);
  assert(calls==1 && ticks==0 && out.completed_rounds==0);
  route.compare=cmp;c.expected_sign=1;calls=ticks=0;
  assert(sc_measure(&c,&route,clock_tick,&out)==2 && !calls && !ticks);
  c.expected_sign=-1;c.left_bytes=0;
  assert(sc_measure(&c,&route,clock_tick,&out)==2 && !calls && !ticks);
  c.left_bytes=2;zero_tick=1;calls=ticks=0;
  assert(sc_measure(&c,&route,clock_tick,&out)==4 && calls==66 && ticks==2 && !out.completed_rounds);
  c.repeats=0;assert(sc_measure(&c,&route,clock_tick,&out)==1);
  c.repeats=SC_MAX_REPEATS+1;assert(sc_measure(&c,&route,clock_tick,&out)==1);
  puts("Benchmark core: real call count, unsigned oracle, n=0, wrap, first fault and invalid timer PASS; synthetic ticks, no speed claim");
}
