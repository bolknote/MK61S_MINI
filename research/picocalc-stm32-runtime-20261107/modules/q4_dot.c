#include "stm3_module.h"
static volatile uint32_t runs;
static uint32_t u32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void out32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
#if defined(__arm__) || defined(__thumb__)
__attribute__((section(".text.module_entry"),used))
#endif
uint32_t module_entry(uint32_t op,const stm3_api*api,stm3_job*job){
 if(!api||api->abi!=STM3_ABI||api->size!=sizeof(stm3_api))return STM3_INVALID;
 if(op==STM3_FINI||op==STM3_CANCEL)return STM3_DONE;
 if(job->input_bytes<12||u32(job->input)!=0x31544451u||u32(job->input+8)!=32)return STM3_INVALID;
 const unsigned rows=u32(job->input+4);
 if(!rows||rows>16||job->input_bytes!=76+rows*16||job->output_capacity<8+4*rows)return STM3_INVALID;
 if(op==STM3_INIT){++runs;job->progress=0;job->output_bytes=8+4*rows;out32(job->output,rows);out32(job->output+4,runs);return STM3_MORE;}
 if(op!=STM3_STEP||job->progress>=rows)return STM3_INVALID;
 const uint8_t*w=job->input+76+16*job->progress;int32_t sum=0;
 for(unsigned j=0;j<32;++j){
  const unsigned a=12+2*j;const int32_t x=(int16_t)((uint16_t)job->input[a]|(uint16_t)job->input[a+1]<<8);
  const int32_t weight=(int32_t)((w[j/2]>>(4*(j&1)))&15)-8;
  sum+=weight*x;
 }
 out32(job->output+8+4*job->progress,(uint32_t)sum);++job->progress;
 return job->progress==rows?STM3_DONE:STM3_MORE;
}
