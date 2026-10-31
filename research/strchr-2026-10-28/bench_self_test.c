#include "bench.h"
#include <assert.h>
#include <stdio.h>
static unsigned calls,ticks,wrong_call;
static uint32_t clock_value,step;
static uint32_t tick(void){++ticks;uint32_t value=clock_value;clock_value+=step;return value;}
static char* search(const char* p,int c) {
  ++calls;
  if(calls==wrong_call)return 0;
  for(;;++p){if((unsigned char)*p==(unsigned char)c)return (char*)p;if(!*p)return 0;}
}
static void reset(void){calls=ticks=wrong_call=0;clock_value=0;step=17;}
int main(void) {
  const char text[]={'A',(char)255,'B',0,'B'};
  st_case c={text,sizeof(text),-1,1,5};st_samples out;
  reset();assert(!st_measure(&c,search,tick,&out));
  assert(calls==ST_ROUNDS*(c.repeats+2) && ticks==2*ST_ROUNDS && out.completed_rounds==ST_ROUNDS);
  for(unsigned i=0;i<ST_ROUNDS;++i)assert(out.raw[i]==17);
  reset();clock_value=0xfffffff8u;assert(!st_measure(&c,search,tick,&out) && out.raw[0]==17);
  reset();wrong_call=1;assert(st_measure(&c,search,tick,&out)==3 && calls==1 && !ticks);
  reset();wrong_call=3;assert(st_measure(&c,search,tick,&out)==3 && calls==7 && ticks==2 && out.completed_rounds==0 && out.mismatch);
  reset();wrong_call=7;assert(st_measure(&c,search,tick,&out)==3 && calls==7 && out.completed_rounds==0);
  reset();step=0;assert(st_measure(&c,search,tick,&out)==4 && out.completed_rounds==0);
  reset();step=0x80000000u;assert(st_measure(&c,search,tick,&out)==4);
  reset();c.expected_offset=2;assert(st_measure(&c,search,tick,&out)==2 && !calls && !ticks);
  c.expected_offset=1;c.text_bytes=1;assert(st_measure(&c,search,tick,&out)==2);
  c.text_bytes=sizeof(text);c.repeats=0;assert(st_measure(&c,search,tick,&out)==1);
  c.repeats=ST_MAX_REPEATS+1;assert(st_measure(&c,search,tick,&out)==1);
  c.repeats=1;c.character=0x100;c.expected_offset=3;assert(!st_measure(&c,search,tick,&out));
  c.character='A';c.text_bytes=2;c.expected_offset=0;assert(st_measure(&c,search,tick,&out)==2);
  c.text_bytes=sizeof(text);
  c.character='Z';c.expected_offset=-1;assert(!st_measure(&c,search,tick,&out));
  c.text="";c.text_bytes=1;c.character=0;c.expected_offset=0;assert(!st_measure(&c,search,tick,&out));
  assert(st_measure(0,search,tick,&out)==1 && st_measure(&c,0,tick,&out)==1);
  assert(st_measure(&c,search,0,&out)==1 && st_measure(&c,search,tick,0)==1);
  puts("strchr bench: raw calls, pointer oracle, transient fault, first fault, timer wrap/zero/range PASS");
  return 0;
}
