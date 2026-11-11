#include "stm3_runtime.h"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <cstdio>
#include <random>
static uint32_t get(const uint8_t*p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=uint32_t(p[i])<<(8*i);return v;}
static void put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=uint8_t(v>>(8*i));}
int main(){
 std::mt19937 rng(771);
 for(unsigned n=1;n<=268;++n)for(unsigned mode=0;mode<3;++mode){
  uint8_t src[268],enc[272];
  for(unsigned i=0;i<n;++i)src[i]=mode==0?0:mode==1?255:uint8_t(rng());
  unsigned e=stm3_cobs_encode(src,n,enc,sizeof(enc));assert(e);
  unsigned d=stm3_cobs_decode(enc,e,enc,sizeof(enc));assert(d==n&&!memcmp(src,enc,n));
 }
 stm3_runtime r;const stm3_backend b={};stm3_init(&r,&b);
 r.state=STM3_FINISHED;r.job_id=37;r.job.output_bytes=512;
 for(unsigned i=0;i<512;++i)r.output[i]=uint8_t(i*113u+177u);
 for(unsigned count=0;count<=252;++count){
  uint8_t shared[256];put(shared,37);put(shared+4,512-count);put(shared+8,count);
  uint16_t n;stm3_command(&r,STM3_READ,shared,12,shared,&n);
  assert(get(shared)==0&&n==4+count&&!memcmp(shared+4,r.output+512-count,count));
 }
 std::printf("COMPACT ASan/UBSan PASS: 804 in-place COBS vectors,253 overlapping READ lengths; HOST runtime=%zu\n",sizeof(r));
}
