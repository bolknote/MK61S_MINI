#include "mk61_ai_linear.hpp"
#include "mk61_ai_kernels.h"
#include <array>
#include <vector>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
using namespace mk61ai;
static std::uint32_t state=611009;
static std::uint32_t random32(){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
int main(){
 constexpr unsigned cols=384,rows=4;
 std::vector<std::uint8_t> nibble(rows*cols/2),planes(nibble.size()),scale(rows*cols/16);
 std::array<std::int16_t,cols> x16;std::array<std::int8_t,cols>x8;
 std::array<float,cols/8> activation_scale;
 std::array<float,rows> out,expected;
 unsigned checks=0;
 for(unsigned trial=0;trial<1000;++trial){
  for(auto&b:nibble)b=std::uint8_t(random32());
  for(unsigned i=0;i<scale.size();i+=2){scale[i]=0;scale[i+1]=0x3c;}
  for(unsigned i=0;i<cols;++i){x16[i]=std::int16_t(random32());x8[i]=std::int8_t(random32());}
  if(trial<4)for(unsigned i=0;i<cols;++i)x16[i]=trial==0?-32768:trial==1?32767:trial==2?(i&1?-32768:32767):0;
  for(unsigned i=0;i<nibble.size();i+=16)mk61ai_pack_q4_planes32(nibble.data()+i,planes.data()+i);
  for(unsigned group:{8U,16U,32U})for(bool wide:{false,true})for(bool packed:{false,true}){
   for(unsigned i=0;i<cols/group;++i)activation_scale[i]=float(i%5+1)*0x1p-15f;
   for(unsigned r=0;r<rows;++r){expected[r]=0;
    for(unsigned at=0;at<cols;at+=group){std::int64_t sum=0;
     for(unsigned j=0;j<group;++j){unsigned c=at+j;auto b=nibble[r*cols/2+c/2];int w=int(c&1?b>>4:b&15)-8;sum+=w*(wide?int(x16[c]):int(x8[c]));}
     expected[r]+=float(sum)*activation_scale[at/group];
    }
   }
   LinearBatch b;b.arithmetic=wide?Arithmetic::INT16:Arithmetic::INT8;b.activation_group=group;b.columns=cols;b.rows=rows;b.bits=4;b.grid=packed?256:0;
   b.quant=x8.data();b.quant16=x16.data();b.activation_scales=activation_scale.data();b.weights=packed?planes.data():nibble.data();b.scales=scale.data();b.output=out.data();
   linear_batch_sram(&b);assert(b.status==ModelStatus::OK);assert(!std::memcmp(out.data(),expected.data(),sizeof(out)));checks+=rows;
  }
 }
 std::printf("A8/A16 group8/16/32 and nibble/bitplane kernels vs independent int64: %u rows PASS\n",checks);
}
