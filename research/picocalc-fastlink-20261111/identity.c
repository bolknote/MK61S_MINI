/* Read-only M3 identity. CRC is software; the resident CRC peripheral is free. */
#include "stm3_module.h"
#include "link.h"
#define R(a) (*(volatile const uint32_t *)(uintptr_t)(a))
static uint32_t offset,crc,bytes;
__attribute__((section(".text.module_entry"),used))
uint32_t module_entry(uint32_t op,const stm3_api *api,stm3_job *job) {
 if(!api||api->abi!=STM3_ABI||api->size!=sizeof(*api))return STM3_INVALID;
 if(op==STM3_CANCEL||op==STM3_FINI)return STM3_DONE;
 if(job->output_capacity<120)return STM3_INVALID;
 if(op==STM3_INIT) {
  if(job->input_bytes!=4||fl_get(job->input)!=FL_ID_MAGIC)return STM3_INVALID;
  const uint8_t *meta=(const uint8_t *)(uintptr_t)0x0800f400u;
  bytes=fl_get(meta+16);
  if(fl_get(meta)!=0x3155334du||fl_get(meta+4)!=1||fl_get(meta+8)!=0x410||
     fl_get(meta+12)!=0x08002000u||bytes<8||bytes>0xd400u||
     R(0x0800f420u)!=0xc001cafeu||~fl_crc_step(~0u,meta,28)!=fl_get(meta+28))return STM3_INVALID;
  for(unsigned i=0;i<36;++i)job->output[i]=meta[i];
  offset=0;crc=~0u;job->output_bytes=120;job->progress=0;return STM3_MORE;
 }
 if(op!=STM3_STEP||offset>=bytes)return STM3_INVALID;
 unsigned take=bytes-offset;if(take>128)take=128;
 crc=fl_crc_step(crc,(const uint8_t *)(uintptr_t)(0x08002000u+offset),take);
 offset+=take;job->progress=offset;
 if(offset<bytes)return STM3_MORE;
 fl_put(job->output+36,~crc);fl_put(job->output+40,R(0xe0042000u));
 fl_put(job->output+44,*(volatile const uint16_t *)(uintptr_t)0x1ffff7e0u);
 fl_put(job->output+48,R(0x40021004u));fl_put(job->output+52,R(0x4002101cu));
 fl_put(job->output+56,R(0x40020080u)); /* DMA7 CCR */
 fl_put(job->output+60,R(0x40020000u)); /* DMA ISR */
 fl_put(job->output+64,R(0x40010004u)); /* AFIO MAPR */
 fl_put(job->output+68,R(0x40010c04u));fl_put(job->output+72,R(0x40011004u));
 fl_put(job->output+76,R(0x40005400u));fl_put(job->output+80,R(0x40005418u));
 fl_put(job->output+84,R(0x4000480cu));fl_put(job->output+88,R(0x40004814u));
 fl_put(job->output+92,R(0x40020030u));fl_put(job->output+96,R(0x40020034u));
 fl_put(job->output+100,R(0xe000e100u));fl_put(job->output+104,R(0xe000e104u));
 fl_put(job->output+108,FL_ID_MAGIC);fl_put(job->output+112,R(0xe000ed00u));
 fl_put(job->output+116,2);return STM3_DONE;
}
