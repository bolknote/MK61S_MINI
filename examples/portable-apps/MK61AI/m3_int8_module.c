#include "stm3_module.h"
#include "m3_linear_protocol.h"
#include "m3_q4_kernels.h"

/* A separate module frees the FP32 LUT/vector allocation. PREPARE chunks
 * contain columns INT8 values, then columns/32 binary32 activation scales.
 * RUN uses the same group32 FP16 weight scales as the Pico INT8 baseline. */
static uint8_t vector[AI_M3_MAX_COLUMNS*9/8] __attribute__((aligned(4)));
static uint32_t columns,received,group,rows;
static uint32_t get32(const uint8_t*p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
static float get_float(const uint8_t*p){union{uint32_t u;float f;}v={get32(p)};return v.f;}
static void put_float(uint8_t*p,float f){union{float f;uint32_t u;}v={f};put32(p,v.u);}
static uint32_t finite(float f){union{float f;uint32_t u;}v={f};return(v.u&0x7f800000u)!=0x7f800000u;}
static float half(uint32_t h){
 const uint32_t exponent=(h>>10)&31,mantissa=h&1023;
 union{uint32_t u;float f;}v;
 if(exponent)v.u=((exponent+112)<<23)|(mantissa<<13);
 else v.f=(float)mantissa*0x1p-24f;
 return h&0x8000?-v.f:v.f;
}
static uint32_t ack(stm3_job*j){
 put32(j->output,AI_M3_INT8_MAGIC);put32(j->output+4,columns);put32(j->output+8,received);
 j->output_bytes=12;j->progress=received;return STM3_DONE;
}
uint32_t module_entry(uint32_t op,const stm3_api*api,stm3_job*j){
 if(op==STM3_FINI||op==STM3_CANCEL){columns=received=group=rows=0;return STM3_DONE;}
 if(!api||api->abi!=STM3_ABI||api->size<sizeof(*api)||!j||!j->input||!j->output||j->output_capacity<12)return STM3_INVALID;
 if(op==STM3_INIT){
  group=rows=0;j->progress=j->output_bytes=0;
  if(columns&&received<columns*9/8){
   const uint32_t n=j->input_bytes;
   if(!n||n%4||n>512||n>columns*9/8-received)return STM3_INVALID;
   for(uint32_t i=0;i<n;i+=4)if(received+i>=columns){float s=get_float(j->input+i);if(!finite(s)||s<0)return STM3_INVALID;}
   for(uint32_t i=0;i<n;++i)vector[received+i]=j->input[i];
   received+=n;return ack(j);
  }
  if(j->input_bytes<AI_M3_HEADER||get32(j->input)!=AI_M3_INT8_MAGIC)return STM3_INVALID;
  const uint32_t command=get32(j->input+4),nc=get32(j->input+8),nr=get32(j->input+12);
  if(command==AI_M3_PREPARE){
   if(!nc||nc%32||nc>AI_M3_MAX_COLUMNS||nr||j->input_bytes!=AI_M3_HEADER)return STM3_INVALID;
   columns=nc;received=0;return ack(j);
  }
  if(command!=AI_M3_RUN||!columns||nc!=columns||received!=columns*9/8||!nr||nr>AI_M3_MAX_ROWS||
     j->input_bytes!=AI_M3_HEADER+nr*(columns/2+columns/16)||j->input_bytes>512)return STM3_INVALID;
  rows=nr;j->output_bytes=rows*4;
  for(uint32_t r=0;r<rows;++r)put_float(j->output+4*r,0);
  return STM3_MORE;
 }
 if(op!=STM3_STEP||!rows||group>=columns/32)return STM3_INVALID;
 const uint32_t stride=columns/2+columns/16;
 const uint8_t*w=j->input+AI_M3_HEADER;
 const int8_t*x=(const int8_t*)vector+32*group;
 int32_t sums[2];
 if(rows==2)ai_m3_dot2_a8_32(w+16*group,w+stride+16*group,x,sums);
 else sums[0]=ai_m3_dot1_a8_32(w+16*group,x);
 const float act_scale=get_float(vector+columns+4*group);
 for(uint32_t r=0;r<rows;++r){
  const uint8_t*s=w+r*stride+columns/2+2*group;
  const uint32_t h=s[0]|(uint32_t)s[1]<<8;if((h&0x7c00)==0x7c00)return STM3_INVALID;
  const float result=get_float(j->output+4*r)+(float)sums[r]*half(h)*act_scale;
  if(!finite(result))return STM3_INVALID;
  put_float(j->output+4*r,result);
 }
 j->progress=++group;return group==columns/32?STM3_DONE:STM3_MORE;
}
