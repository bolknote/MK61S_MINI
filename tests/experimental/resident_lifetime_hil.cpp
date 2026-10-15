// Read-only allocator metadata probe; generated addresses pin an exact BIN/ELF.
// It uses the normal file service for its report and never calls private code.
#include "mk61_app.h"
#include "resident_lifetime.hpp"
static uint32_t read32(uint32_t address) {
  return *(const volatile uint32_t*)(uintptr_t)address;
}
static char* hex(char* p,uint32_t value) {
  static const char digits[]="0123456789ABCDEF";
  for(unsigned i=0;i<8;++i)*p++=digits[(value>>(28-i*4))&15];
  *p++=' ';return p;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),0) ||
     read32(LIFE_PROBE_FOOTER+24)!=LIFE_PROBE_BUILD) return MK61_APP_RUNTIME_ERROR;
  const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
  if(!services) return MK61_APP_RUNTIME_ERROR;
  const uint32_t heap=read32(LIFE_PROBE_HEAP);
  const uint32_t app=read32(LIFE_PROBE_ARENAS+4*92);
  const uint32_t app_size=read32(LIFE_PROBE_ARENAS+4*92+4);
  const uint32_t prefix_end=read32(LIFE_PROBE_ARENAS+3*92)+
      read32(LIFE_PROBE_ARENAS+3*92+12);
  if(!app_size || (app&31) || app<heap || app>LIFE_PROBE_END ||
      app_size>LIFE_PROBE_END-app) return MK61_APP_RUNTIME_ERROR;
  uint32_t count=0,bytes=0,owners=0,starts[3],lengths[3];
  for(uint32_t node=LIFE_PROBE_HEAD?read32(LIFE_PROBE_HEAD):0;node;) {
    if(++count>3 || node<0x20000000U || node>LIFE_PROBE_END-16 || (node&3))
      return MK61_APP_RUNTIME_ERROR;
    uint32_t address=read32(node),size=read32(node+4),owner=read32(node+8)&255;
    if(!size || size>LIFE_PROBE_END-0x20000000U || (address&31) ||
       address<((heap+7)&~7U) || address<prefix_end || address>LIFE_PROBE_END ||
       size>LIFE_PROBE_END-address || owner>=32 || (owners&(1U<<owner)))
      return MK61_APP_RUNTIME_ERROR;
    const uint32_t rounded=(size+31)&~31U;
    if(rounded>LIFE_PROBE_END-address ||
        (address<app+app_size && app<address+rounded)) return MK61_APP_RUNTIME_ERROR;
    for(uint32_t i=0;i+1<count;++i)
      if(address<starts[i]+lengths[i] && starts[i]<address+rounded)
        return MK61_APP_RUNTIME_ERROR;
    starts[count-1]=address;lengths[count-1]=rounded;
    bytes+=rounded;owners|=1U<<owner;node=read32(node+12);
  }
  char report[128]="LIFERAM1 ";char* at=report+9;
  at=hex(at,LIFE_PROBE_BUILD);at=hex(at,heap);
  at=hex(at,LIFE_PROBE_END);at=hex(at,read32(LIFE_PROBE_ARENAS+3*92+4));
  at=hex(at,read32(LIFE_PROBE_ARENAS+4*92+4));
  at=hex(at,count);at=hex(at,bytes);at=hex(at,owners);at[-1]='\n';
  mk61_service_write file={"LIFERPT",(const uint8_t*)report,(uint32_t)(at-report),MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,
      MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)?MK61_APP_OK:MK61_APP_RUNTIME_ERROR;
}
