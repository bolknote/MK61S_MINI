#include "mk61_ai_linear.hpp"
#include "stm3_module.h"
#include "../examples/portable-apps/MK61AI/m3_linear_protocol.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <random>
extern "C" uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
static void put(void*p,uint32_t v){std::memcpy(p,&v,4);}
int main(){
 using namespace mk61ai;
 const stm3_api api{STM3_ABI,sizeof(stm3_api),nullptr,nullptr};
 alignas(4)uint8_t input[512],output[512],vector[576],weights[512],scales[64];
 stm3_job job{input,0,output,sizeof(output),0,0};std::mt19937 rng(0x494e5438);
 unsigned checked=0;
 for(unsigned cols:{32U,128U,384U,512U})for(unsigned test=0;test<100;++test){
  assert(module_entry(STM3_FINI,&api,&job)==STM3_DONE);
  const unsigned rows=std::min(2U,(512U-AI_M3_HEADER)/(cols/2+cols/16));
  for(unsigned j=0;j<cols;++j)vector[j]=test<2?uint8_t(test?-128:127):uint8_t(rng());
  for(unsigned g=0;g<cols/32;++g){float s=test==2?0:float(1+rng()%1000)*0x1p-16f;std::memcpy(vector+cols+4*g,&s,4);}
  for(auto&w:weights)w=uint8_t(rng());
  const uint16_t edges[]={0,0x8000,1,0x83ff,0x0400,0xbc00,0x3c00,0x7bff};
  for(unsigned at=0;at<sizeof(scales);at+=2){uint16_t h=test<8?edges[test]:uint16_t((rng()%0x7800)^((rng()&1)<<15));std::memcpy(scales+at,&h,2);}
  float expected[2]{},actual[2]{};
  LinearBatch b{};b.arithmetic=Arithmetic::INT8;b.bits=4;b.grid=0;b.columns=cols;b.rows=rows;b.quant=(const int8_t*)vector;
  b.activation_scales=(const float*)(vector+cols);b.weights=weights;b.scales=scales;b.output=expected;
  linear_batch_flash(&b);assert(b.status==ModelStatus::OK);
  put(input,AI_M3_INT8_MAGIC);put(input+4,AI_M3_PREPARE);put(input+8,cols);put(input+12,0);job.input_bytes=16;
  assert(module_entry(STM3_INIT,&api,&job)==STM3_DONE&&job.output_bytes==12);
  for(unsigned at=0;at<cols*9/8;){unsigned n=std::min(512U,cols*9/8-at);std::memcpy(input,vector+at,n);job.input_bytes=n;
   assert(module_entry(STM3_INIT,&api,&job)==STM3_DONE);uint32_t received;std::memcpy(&received,output+8,4);assert(received==at+n);at+=n;}
  put(input,AI_M3_INT8_MAGIC);put(input+4,AI_M3_RUN);put(input+8,cols);put(input+12,rows);
  for(unsigned r=0;r<rows;++r){auto*p=input+16+r*(cols/2+cols/16);std::memcpy(p,weights+r*cols/2,cols/2);std::memcpy(p+cols/2,scales+r*cols/16,cols/16);}
  job.input_bytes=16+rows*(cols/2+cols/16);assert(module_entry(STM3_INIT,&api,&job)==STM3_MORE);
  for(unsigned g=0;g<cols/32;++g)assert(module_entry(STM3_STEP,&api,&job)==(g+1==cols/32?STM3_DONE:STM3_MORE));
  assert(job.output_bytes==rows*4&&job.progress==cols/32);std::memcpy(actual,output,rows*4);
  assert(!std::memcmp(expected,actual,rows*4));checked+=rows;
 }
 assert(module_entry(STM3_CANCEL,&api,&job)==STM3_DONE);
 put(input,AI_M3_INT8_MAGIC);put(input+4,AI_M3_RUN);put(input+8,128);put(input+12,1);job.input_bytes=88;
 assert(module_entry(STM3_INIT,&api,&job)==STM3_INVALID);
 std::printf("M3 INT8 HOST ASan/UBSan PASS: %u rows exactly equal to Pico INT8 group32, including two-row kernel, chunk boundaries, half scales and extrema\n",checked);
}
