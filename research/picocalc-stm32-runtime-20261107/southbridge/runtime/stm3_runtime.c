#include "stm3_runtime.h"
#include <string.h>
static uint32_t get32(const void* p){const uint8_t*s=(const uint8_t*)p;return (uint32_t)s[0]|(uint32_t)s[1]<<8|(uint32_t)s[2]<<16|(uint32_t)s[3]<<24;}
static void put32(void*p,uint32_t v){uint8_t*s=(uint8_t*)p;for(unsigned i=0;i<4;++i)s[i]=(uint8_t)(v>>(8*i));}
static uint32_t now(stm3_runtime*r){return r->backend.micros?r->backend.micros(r->backend.context):0;}
uint32_t stm3_crc32(const void*data,size_t n){const uint8_t*p=(const uint8_t*)data;uint32_t v=~0u;while(n--){v^=*p++;for(unsigned i=0;i<8;++i)v=(v>>1)^(0xedb88320u&(0u-(v&1)));}return ~v;}
void stm3_init(stm3_runtime*r,const stm3_backend*b){memset(r,0,sizeof(*r));r->backend=*b;}
static void fault(stm3_runtime*r,uint32_t e){r->error=e;r->state=STM3_FAULT;}
static uint32_t invoke(stm3_runtime*r,unsigned operation){
 stm3_api api={STM3_ABI,sizeof(stm3_api),r->backend.micros,r->backend.context};
 const uint32_t before=now(r);
 const uint32_t result=r->backend.invoke(r->backend.context,r->entry,operation,&api,&r->job);
 const uint32_t took=now(r)-before;
 if(took>r->max_slice_us)r->max_slice_us=took;
 // Cooperative modules: this detects an overrun after return, not a sandbox.
 if(took>r->header.slice_us){fault(r,STM3_E_TIME);return STM3_INVALID;}
 if(r->job.output_bytes>r->header.output_limit||r->job.output_bytes>STM3_IO_CAPACITY){fault(r,STM3_E_MODULE);return STM3_INVALID;}
 return result;
}
static uint32_t commit(stm3_runtime*r){
 stm3_header h;
 if(r->state!=STM3_LOADING||r->received!=r->package_bytes)return STM3_E_STATE;
 memcpy(&h,r->arena.bytes,sizeof(h));
 if(stm3_crc32(&h,60)!=h.header_crc)return STM3_E_CRC;
 if(h.magic!=STM3_MAGIC||h.header_bytes!=64||h.package_bytes!=r->package_bytes||h.flags)return STM3_E_FORMAT;
 if(h.abi!=STM3_ABI||h.target!=STM3_TARGET)return STM3_E_ABI;
 if(h.image_bytes<4||h.image_bytes>STM3_IMAGE_CAPACITY||h.bss_bytes>STM3_IMAGE_CAPACITY-h.image_bytes||h.reloc_count>STM3_RELOC_LIMIT)return STM3_E_SIZE;
 if(h.package_bytes!=64+h.image_bytes+4*h.reloc_count||!(h.entry_offset&1)||((h.entry_offset&~1u)>=h.image_bytes))return STM3_E_FORMAT;
 if(!h.input_limit||h.input_limit>STM3_IO_CAPACITY||!h.output_limit||h.output_limit>STM3_IO_CAPACITY||h.stack_hint>512||!h.slice_us||h.slice_us>2000)return STM3_E_SIZE;
 if(stm3_crc32(r->arena.bytes+64,h.package_bytes-64)!=h.payload_crc)return STM3_E_CRC;
 const uint32_t base=r->backend.load_address(r->backend.context,r->arena.bytes),memory=h.image_bytes+h.bss_bytes;
 if((base&3)||base>UINT32_MAX-memory)return STM3_E_FORMAT;
 const uint8_t* relocs=r->arena.bytes+64+h.image_bytes;
 uint32_t previous=0;
 for(uint32_t i=0;i<h.reloc_count;++i){
  const uint32_t at=get32(relocs+4*i);
  if((at&3)||at>h.image_bytes-4||(i&&at<=previous))return STM3_E_FORMAT;
  const uint32_t value=get32(r->arena.bytes+64+at);
  if(value<STM3_LINK_BASE||value-STM3_LINK_BASE>memory)return STM3_E_FORMAT;
  previous=at;
 }
 // Relocations remain beyond the old image while the image is moved down.
 memmove(r->arena.bytes,r->arena.bytes+64,h.image_bytes);
 for(uint32_t i=0;i<h.reloc_count;++i){const uint32_t at=get32(relocs+4*i);put32(r->arena.bytes+at,base+(get32(r->arena.bytes+at)-STM3_LINK_BASE));}
 memset(r->arena.bytes+h.image_bytes,0,h.bss_bytes);
 memset(r->input,0,sizeof(r->input));memset(r->output,0,sizeof(r->output));
 r->header=h;r->entry=base+h.entry_offset;r->state=STM3_READY;r->error=0;
 if(r->module_id==UINT32_MAX){fault(r,STM3_E_MODULE);return STM3_E_MODULE;}
 ++r->module_id;return STM3_OK;
}
static uint32_t start_job(stm3_runtime*r,const uint8_t*in){
 if(r->state!=STM3_READY&&r->state!=STM3_FINISHED&&r->state!=STM3_CANCELLED)return STM3_E_STATE;
 if(get32(in)!=r->module_id)return STM3_E_MODULE;
 if(get32(in+4)>r->header.input_limit||!get32(in+8)||get32(in+8)>10000)return STM3_E_SIZE;
 if(r->job_id==UINT32_MAX)return STM3_E_JOB;
 memset(r->output,0,sizeof(r->output));r->job=(stm3_job){r->input,get32(in+4),r->output,r->header.output_limit,0,0};
 ++r->job_id;r->state=STM3_RUNNING;r->error=0;r->steps=0;r->max_slice_us=0;r->started=now(r);r->deadline_us=get32(in+8)*1000;
 const uint32_t result=invoke(r,STM3_INIT);
 if(r->state==STM3_FAULT)return r->error;
 if(result==STM3_DONE)r->state=STM3_FINISHED;
 else if(result!=STM3_MORE){fault(r,STM3_E_MODULE);return STM3_E_MODULE;}
 return STM3_OK;
}
static void finish_deferred(stm3_runtime*r);
void stm3_tick(stm3_runtime*r){
 if(r->state==STM3_RUNNING){
  if(now(r)-r->started>r->deadline_us||r->steps>=10000)fault(r,STM3_E_TIME);
  else{
   ++r->steps;const uint32_t result=invoke(r,STM3_STEP);
   if(r->state!=STM3_FAULT){
    if(result==STM3_DONE)r->state=STM3_FINISHED;
    else if(result!=STM3_MORE)fault(r,STM3_E_MODULE);
   }
  }
 }
 if(r->deferred&&r->state!=STM3_RUNNING)finish_deferred(r);
}
void stm3_command(stm3_runtime*r,uint8_t command,const uint8_t*in,uint16_t n,uint8_t*out,uint16_t*out_n){
 uint32_t error=STM3_OK;unsigned used=4;
 switch(command){
 case STM3_HELLO:
  if(n){error=STM3_E_ARGUMENT;break;}
  put32(out+4,STM3_ABI);put32(out+8,STM3_TARGET);put32(out+12,STM3_IMAGE_CAPACITY);put32(out+16,STM3_IO_CAPACITY);
  put32(out+20,r->state);put32(out+24,r->bad_frames);put32(out+28,r->sequence_conflicts);
  put32(out+32,r->backend.baud);put32(out+36,r->backend.transport_flags|STM3_TRANSPORT_START_RESULT);used=40;break;
 case STM3_LOAD_BEGIN:
  if(n!=4){error=STM3_E_ARGUMENT;break;}
  if(r->state==STM3_RUNNING||r->state==STM3_LOADING||r->state==STM3_READY||r->state==STM3_FINISHED||r->state==STM3_CANCELLED){error=STM3_E_STATE;break;}
  if(get32(in)<64||get32(in)>STM3_PACKAGE_CAPACITY){error=STM3_E_SIZE;break;}
  memset(r->arena.bytes,0,sizeof(r->arena.bytes));memset(&r->header,0,sizeof(r->header));memset(&r->job,0,sizeof(r->job));r->entry=0;
  r->package_bytes=get32(in);r->received=0;r->state=STM3_LOADING;r->error=0;break;
 case STM3_LOAD_CHUNK:
  if(n<5){error=STM3_E_ARGUMENT;break;}
  if(r->state!=STM3_LOADING){error=STM3_E_STATE;break;}
  if(get32(in)!=r->received||n-4u>r->package_bytes-r->received){error=STM3_E_SIZE;break;}
  memcpy(r->arena.bytes+r->received,in+4,n-4);r->received+=n-4;put32(out+4,r->received);used=8;break;
 case STM3_LOAD_COMMIT:
  if(n){error=STM3_E_ARGUMENT;break;}
  error=commit(r);if(error){if(r->state==STM3_LOADING)fault(r,error);break;}
  put32(out+4,r->module_id);used=8;break;
 case STM3_WRITE:
  if(n<4){error=STM3_E_ARGUMENT;break;}
  if(r->state!=STM3_READY&&r->state!=STM3_FINISHED&&r->state!=STM3_CANCELLED){error=STM3_E_STATE;break;}
  if(get32(in)>r->header.input_limit||n-4u>r->header.input_limit-get32(in)){error=STM3_E_SIZE;break;}
  memcpy(r->input+get32(in),in+4,n-4);break;
 case STM3_START:{
  if(n!=12){error=STM3_E_ARGUMENT;break;}
  error=start_job(r,in);if(error)break;
  put32(out+4,r->job_id);used=8;break;}
 case STM3_START_RESULT:{
  if(n!=16){error=STM3_E_ARGUMENT;break;}
  const uint32_t count=get32(in+12);
  if(count>STM3_RESULT_LIMIT||count>r->header.output_limit){error=STM3_E_SIZE;break;}
  error=start_job(r,in);if(error)break;
  if(r->state==STM3_RUNNING){r->deferred=1;r->deferred_count=count;*out_n=0;return;}
  if(count>r->job.output_bytes){error=STM3_E_SIZE;break;}
  put32(out+4,r->job_id);put32(out+8,r->max_slice_us);
  memcpy(out+12,r->output,count);used=12+count;break;}
 case STM3_STATUS:
  if(n!=4){error=STM3_E_ARGUMENT;break;}
  if(get32(in)!=r->job_id||!r->job_id){error=STM3_E_JOB;break;}
  put32(out+4,r->job_id);put32(out+8,r->state);put32(out+12,r->error);put32(out+16,r->job.progress);
  put32(out+20,r->job.output_bytes);put32(out+24,r->steps);put32(out+28,r->max_slice_us);used=32;break;
 case STM3_READ:{
  if(n!=12){error=STM3_E_ARGUMENT;break;}
  if(get32(in)!=r->job_id||!r->job_id){error=STM3_E_JOB;break;}
  if(r->state!=STM3_FINISHED){error=STM3_E_STATE;break;}
  if(get32(in+8)>STM3_WIRE_PAYLOAD-4||get32(in+4)>r->job.output_bytes||get32(in+8)>r->job.output_bytes-get32(in+4)){error=STM3_E_SIZE;break;}
  // Request and response payloads may share memory after in-place decoding.
  const uint32_t offset=get32(in+4),count=get32(in+8);
  memcpy(out+4,r->output+offset,count);used+=count;break;}
 case STM3_CANCEL_JOB:
  if(n!=4){error=STM3_E_ARGUMENT;break;}
  if(get32(in)!=r->job_id||!r->job_id){error=STM3_E_JOB;break;}
  if(r->state!=STM3_RUNNING){error=STM3_E_STATE;break;}
  (void)invoke(r,STM3_CANCEL);if(r->state!=STM3_FAULT)r->state=STM3_CANCELLED;else error=r->error;break;
 case STM3_UNLOAD:
  if(n){error=STM3_E_ARGUMENT;break;}
  if(r->state==STM3_RUNNING){error=STM3_E_STATE;break;}
  if(r->state!=STM3_LOADING&&r->state!=STM3_EMPTY&&r->entry)(void)invoke(r,STM3_FINI);
  memset(r->arena.bytes,0,sizeof(r->arena.bytes));memset(r->input,0,sizeof(r->input));memset(r->output,0,sizeof(r->output));
  memset(&r->header,0,sizeof(r->header));memset(&r->job,0,sizeof(r->job));r->entry=r->received=r->package_bytes=0;r->error=0;r->state=STM3_EMPTY;break;
 default:error=STM3_E_ARGUMENT;break;
 }
 put32(out,error);*out_n=(uint16_t)(error?4:used);
}
unsigned stm3_cobs_encode(const uint8_t*in,unsigned n,uint8_t*out,unsigned cap){
 if(!cap)return 0;
 unsigned at=1,code_at=0;uint8_t code=1;
 for(unsigned i=0;i<n;++i){if(!in[i]){out[code_at]=code;code_at=at++;code=1;if(at>cap)return 0;}else{if(at>=cap)return 0;out[at++]=in[i];if(++code==255){out[code_at]=code;code_at=at++;code=1;if(at>cap)return 0;}}}
 out[code_at]=code;return at;
}
unsigned stm3_cobs_decode(const uint8_t*in,unsigned n,uint8_t*out,unsigned cap){
 unsigned at=0,i=0;
 while(i<n){const unsigned code=in[i++];if(!code||code-1>n-i)return 0;for(unsigned j=1;j<code;++j){if(at>=cap||!in[i])return 0;out[at++]=in[i++];}if(code!=255&&i<n){if(at>=cap)return 0;out[at++]=0;}}
 return at;
}
static void reply(stm3_runtime*r,unsigned response){
 r->frame[0]=1;r->frame[1]=(uint8_t)(r->last_cmd|128);r->frame[2]=(uint8_t)r->last_seq;r->frame[3]=(uint8_t)(r->last_seq>>8);
 r->frame[4]=(uint8_t)response;r->frame[5]=(uint8_t)(response>>8);r->frame[6]=r->frame[7]=0;
 put32(r->frame+8+response,stm3_crc32(r->frame,8+response));
 unsigned encoded=stm3_cobs_encode(r->frame,12+response,r->tx,sizeof(r->tx)-1);
 if(!encoded){++r->bad_frames;return;}r->tx[encoded++]=0;r->tx_bytes=encoded;r->tx_at=0;r->have_reply=1;
}
static void finish_deferred(stm3_runtime*r){
 // Rebuild the header: duplicate/noisy RX frames may have reused frame[].
 uint32_t error=r->state==STM3_FAULT?r->error:STM3_OK;unsigned used=4;
 if(!error&&r->state!=STM3_FINISHED)error=STM3_E_STATE;
 if(!error&&r->deferred_count>r->job.output_bytes)error=STM3_E_SIZE;
 put32(r->frame+8,error);
 if(!error){
  put32(r->frame+12,r->job_id);put32(r->frame+16,r->max_slice_us);
  memcpy(r->frame+20,r->output,r->deferred_count);used=12+r->deferred_count;
 }
 r->deferred=0;reply(r,used);
}
void stm3_feed(stm3_runtime*r,uint8_t value){
 if(value){if(!r->frame_overflow){if(r->frame_bytes<sizeof(r->frame))r->frame[r->frame_bytes++]=value;else r->frame_overflow=1;}return;}
 if(!r->frame_bytes&&!r->frame_overflow)return;
 unsigned bytes=r->frame_overflow?0:stm3_cobs_decode(r->frame,r->frame_bytes,r->frame,sizeof(r->frame));r->frame_bytes=r->frame_overflow=0;
 if(bytes<12||r->frame[0]!=1||r->frame[1]&128||r->frame[6]||r->frame[7]){++r->bad_frames;return;}
 unsigned count=(unsigned)r->frame[4]|(unsigned)r->frame[5]<<8;
 if(count>STM3_WIRE_PAYLOAD||bytes!=12+count||stm3_crc32(r->frame,8+count)!=get32(r->frame+8+count)){++r->bad_frames;return;}
 const unsigned seq=(unsigned)r->frame[2]|(unsigned)r->frame[3]<<8;
 const unsigned crc=get32(r->frame+8+count),cmd=r->frame[1];
 // A duplicate pending START_RESULT never starts a second job. A different
 // request cannot steal the sole reply buffer while completion is pending.
 if(r->deferred){if(seq!=r->last_seq||cmd!=r->last_cmd||crc!=r->last_request_crc)++r->sequence_conflicts;return;}
 if(r->have_reply&&seq==r->last_seq){if(cmd==r->last_cmd&&crc==r->last_request_crc)r->tx_at=0;else ++r->sequence_conflicts;return;}
 if(r->tx_at<r->tx_bytes){++r->sequence_conflicts;return;}
 uint16_t response=0;
 // Commands consume their inputs before writing the overlapping response.
 stm3_command(r,(uint8_t)cmd,r->frame+8,(uint16_t)count,r->frame+8,&response);
 r->last_seq=seq;r->last_cmd=cmd;r->last_request_crc=crc;r->have_reply=0;
 if(response)reply(r,response);
}
unsigned stm3_transmit(stm3_runtime*r,uint8_t*out,unsigned cap){unsigned n=r->tx_bytes-r->tx_at;if(n>cap)n=cap;memcpy(out,r->tx+r->tx_at,n);r->tx_at+=n;return n;}
