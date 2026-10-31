/* Real SDK workload: local/slot18 strchr, SRAM and supplier-provided Flash.
 * external_text is bound after INIT; no fixed peripheral or device address.
 */
#include "mk61_app.h"
#include <string.h>
#include <limits.h>
#include "bench.h"
static char* (*volatile search)(const char*,int)=strchr;
static unsigned char storage[544] __attribute__((aligned(16)));
const char* volatile external_text;
volatile uint32_t checks;
/* Optional hardware runner input, supplied only after SDK INIT. The same
 * packed APP can execute the checked timing core using a qualified external
 * timer. Zero request_mode runs the untimed correctness workload. */
volatile uint32_t request_mode;
volatile st_case request;
st_tick volatile request_tick;
st_samples samples;
static int check(const char* text,int c) {
  const unsigned char target=(unsigned char)c;
  const unsigned char* p=(const unsigned char*)text;
  const char* expected;
  for(;;++p) {
    if(*p==target){expected=(const char*)p;break;}
    if(!*p){expected=0;break;}
  }
  if(search(text,c)!=expected)return 0;
  ++checks;return 1;
}
int main(void) {
  static const unsigned lengths[]={0,1,2,3,4,7,8,15,16,31,32,63,64,127,128,255,511};
  static const int targets[]={0,0x52,0x152,-1,255,128,-256,INT_MIN};
  if(request_mode) {
    const st_case c={request.text,request.text_bytes,request.character,request.expected_offset,request.repeats};
    return st_measure(&c,search,request_tick,&samples);
  }
  checks=0;
  if(!external_text)return 20;
  for(unsigned l=0;l<sizeof(lengths)/sizeof(lengths[0]);++l)
    for(unsigned align=0;align<4;++align)
      for(unsigned mode=0;mode<sizeof(targets)/sizeof(targets[0]);++mode) {
        const unsigned n=lengths[l];unsigned char* p=storage+align;
        for(unsigned i=0;i<sizeof(storage);++i)storage[i]=0xa5;
        for(unsigned i=0;i<n;++i)p[i]=0x81;
        const unsigned hit=mode%2?n/2:(n?n-1:0);
        const unsigned char c=(unsigned char)targets[mode];
        if(n && c)p[hit]=c;
        p[n]=0;
        if(!check((const char*)p,targets[mode]))return 10;
        for(unsigned i=0;i<sizeof(storage);++i) {
          const unsigned char expected=i<align || i>align+n?0xa5:
              i==align+n?0:n && c && i==align+hit?c:0x81;
          if(storage[i]!=expected)return 11;
        }
      }
  for(unsigned align=0;align<4;++align)
    for(unsigned mode=0;mode<sizeof(targets)/sizeof(targets[0]);++mode)
      if(!check(external_text+align,targets[mode]))return 12;
  return 0;
}
