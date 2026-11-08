/* All observations stay in RAM. No formatting or filesystem writes at boost. */
#include "mk61_app.h"
static uint8_t source[4096+8], destination[4096+8];
typedef void* (*copy_fn)(void*,const void*,uint32_t);
static const mk61_app_services* s;
static uint32_t call(uint32_t op,uint32_t index,uint32_t value) {
  return s->call(MK61_SERVICE_COMPUTE,op,index,value,0);
}
uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->current.phase>4096)return 0;
  const unsigned rounds=flow->current.phase?flow->current.phase:4096;
  s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_UI);
  if(!s || call(0xC006,0,0)!=0x55435231)return 0;
  call(0xC009,61,call(0xC007,0,0));
  copy_fn copy=(copy_fn)s->runtime[MK61_RUNTIME_SLOT_memcpy];
  uint32_t errors=0,format_errors=0;
  mk61_api->display_clear();
  for(unsigned phase=0;phase<3;++phase) {
    mk61_api->delay_ms(10);
    const uint32_t token=phase==1?mk61_app_compute_begin(s):0;
    call(0xC002,0,0);
    const uint32_t hz=mk61_app_compute_hz(s);
    call(0xC009,64+phase*2,call(0xC00E,0,0));
    call(0xC009,65+phase*2,call(0xC00E,1,0));
    const uint32_t started=s->call(MK61_SERVICE_MICROS,0,0,0,0);
    uint32_t previous=started,maximum_gap=0,hash=0x31415926;
    for(unsigned round=0;round<rounds;++round) {
      for(unsigned i=0;i<1024;++i){hash^=hash<<13;hash^=hash>>17;hash^=hash<<5;}
      if(!(round&63U)) {
        char formatted[32];
        const int formatted_length=mk61_app_snprintf(s,formatted,sizeof(formatted),"%lu",1430475313UL);
        const char expected_text[]="1430475313";
        unsigned wrong=formatted_length!=10;
        for(unsigned i=0;i<sizeof(expected_text);++i)if(formatted[i]!=expected_text[i])wrong=1;
        if(wrong) {
          if(!format_errors) {
            call(0xC009,112,(uint32_t)formatted_length);
            for(unsigned i=0;i<3;++i) {
              uint32_t word=0;for(unsigned j=0;j<4;++j)word|=(uint32_t)(uint8_t)formatted[4*i+j]<<(8*j);
              call(0xC009,113+i,word);
            }
          }
          ++format_errors;
        }
        const unsigned offset=(round>>6)&7U, length=1U+((round*17U+phase*23U)%4096);
        for(unsigned i=0;i<sizeof(source);++i){source[i]=(uint8_t)(i*73U+round);destination[i]=0xA5;}
        if(copy(destination+offset,source+7U-offset,length)!=destination+offset)++errors;
        for(unsigned i=0;i<sizeof(destination);++i) {
          const uint8_t expected=i>=offset && i<offset+length?(uint8_t)((i-offset+7U-offset)*73U+round):0xA5;
          if(*(volatile uint8_t*)(destination+i)!=expected)++errors;
        }
        char line[26];for(unsigned i=0;i<sizeof(line);++i)line[i]=(char)('A'+((round/64U+i+phase)%26U));
        mk61_api->display_write_m8(0,phase%mk61_api->display_rows(),line,sizeof(line));
      }
      mk61_api->service();(void)mk61_api->key_poll();
      if(phase==1 && !(round&63U))mk61_api->delay_ms(1);
      const uint32_t now=s->call(MK61_SERVICE_MICROS,0,0,0,0),gap=now-previous;
      if(gap>maximum_gap)maximum_gap=gap;
      previous=now;
    }
    call(0xC003,0,0);
    call(0xC009,phase*20U,hash);call(0xC009,phase*20U+1,hz);
    call(0xC009,phase*20U+2,previous-started);call(0xC009,phase*20U+3,maximum_gap);
    for(unsigned i=0;i<8;++i){call(0xC009,phase*20U+4+i,call(0xC004,i,0));call(0xC009,phase*20U+12+i,call(0xC005,i,0));}
    if(token && !mk61_app_compute_end(s,token))++errors;
  }
  call(0xC009,60,errors);
  call(0xC009,62,format_errors);
  call(0xC009,63,0x31415926U);
  call(0xC00A,0,0); // Return to the low clock before any terminal/file activity.
  mk61_app_flow_exit(flow,errors?MK61_APP_RUNTIME_ERROR:MK61_APP_OK,MK61_FLOW_OK);
  return 1;
}
