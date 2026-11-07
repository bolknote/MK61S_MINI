#include "mk61_app.h"
#include "candidate/source/mk61_ai_linear.hpp"
#include "candidate/source/mk61_ai_kernels.h"
#include <cstring>
#include <cstdint>
#include <initializer_list>
using namespace mk61ai;
namespace {
constexpr unsigned ROWS=8,COLS=384,LOOPS=128;
std::uint8_t nibble[ROWS*COLS/2],planes[ROWS*COLS/2],scales[ROWS*COLS/16];
std::int8_t q8[COLS];std::int16_t q16[COLS];
float input[COLS],lookup[4*COLS],sum[COLS/32],a8[COLS/32],a16[COLS/32],out[ROWS],expected[ROWS];
volatile std::uint32_t sink=0;
std::uint32_t rng=611009;std::uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
void initialize(unsigned cols){
 for(unsigned i=0;i<cols;++i){q8[i]=std::int8_t(int(i%31)-15);q16[i]=std::int16_t(int(q8[i])*1024);input[i]=float(q8[i])*0x1p-5f;}
 for(unsigned i=0;i<ROWS*cols/2;++i)nibble[i]=std::uint8_t(next());
 for(unsigned i=0;i<ROWS*cols/16;i+=2){scales[i]=0;scales[i+1]=0x3c;}
 for(unsigned at=0;at<ROWS*cols/2;at+=16)mk61ai_pack_q4_planes32(nibble+at,planes+at);
 for(unsigned g=0;g<cols/32;++g){sum[g]=0;a8[g]=0x1p-5f;a16[g]=0x1p-15f;
  for(unsigned q=0;q<8;++q){float*t=lookup+g*128+q*16;t[0]=0;
   for(unsigned lane=0;lane<4;++lane)for(unsigned mask=0;mask<(1U<<lane);++mask)t[mask+(1U<<lane)]=t[mask]+input[g*32+q*4+lane];
   sum[g]+=t[15];
  }
 }
 for(unsigned r=0;r<ROWS;++r){std::int32_t total=0;
  for(unsigned j=0;j<cols;++j){const unsigned b=nibble[r*cols/2+j/2];const int w=int(j&1?b>>4:b&15)-8;total+=w*int(q8[j]);}
  expected[r]=float(total)*0x1p-5f;
 }
}
}
int main(){
 const auto*s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO);if(!s)return 1;
 mk61_api->display_clear();const char title[]="AI kernel bench; Esc: stop";mk61_api->display_write_m8(0,0,title,sizeof(title)-1);mk61_api->service();
 for(unsigned cols:{128U,384U}){
  initialize(cols);
  for(unsigned repeat=0;repeat<3;++repeat)for(unsigned order=0;order<3;++order){
   const unsigned mode=(order+repeat)%3;LinearBatch b;b.columns=cols;b.rows=ROWS;b.bits=4;b.activation_group=32;
   b.arithmetic=mode==0?Arithmetic::LUT_FLOAT32:mode==1?Arithmetic::INT8:Arithmetic::INT16;b.grid=mode==0?256:0;b.weights=mode==0?planes:nibble;b.scales=scales;b.quant=q8;b.quant16=q16;b.input=input;b.lookup=lookup;b.input_sums=sum;b.activation_scales=mode==2?a16:a8;b.output=out;
   linear_batch_sram(&b);if(b.status!=ModelStatus::OK)return 2;
   for(unsigned r=0;r<ROWS;++r)if(out[r]!=expected[r])return 3;
   const auto start=s->call(MK61_SERVICE_MICROS,0,0,0,nullptr);
   for(unsigned i=0;i<LOOPS;++i){
    __asm volatile("":::"memory");linear_batch_sram(&b);__asm volatile("":::"memory");
    if(b.status!=ModelStatus::OK)return 4;
    std::uint32_t bits;std::memcpy(&bits,out+(i&7),4);sink=sink*1664525U+bits+1013904223U;
    if((i&7)==7){mk61_api->service();const auto key=mk61_api->key_poll();if(key==27||key==0x85)return 5;}
   }
   const auto elapsed=s->call(MK61_SERVICE_MICROS,0,0,0,nullptr)-start;
   for(unsigned r=0;r<ROWS;++r)if(out[r]!=expected[r])return 6;
   char line[200];const int n=mk61_app_snprintf(s,line,sizeof(line),"AI_QKERNEL mode=%u cols=%u rows=%u loops=%u repeat=%u us=%u checksum=%08X correct=1\r\n",mode,cols,ROWS,LOOPS,repeat,elapsed,(unsigned)sink);
   if(n<=0||n>=int(sizeof(line)))return 7;
   s->call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,line);mk61_api->service();
  }
 }
 const char done[]="AI_QKERNEL DONE correct=1\r\n";s->call(MK61_SERVICE_DEBUG_WRITE,sizeof(done)-1,0,0,(void*)done);return 0;
}
