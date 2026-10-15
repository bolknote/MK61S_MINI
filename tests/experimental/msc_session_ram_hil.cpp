// Qualification APP only: generated addresses are bound to an exact sealed
// ELF/BIN pair. Read the real allocator/MSC pointers without firmware hooks.
#include "mk61_app.h"
#include "msc_session_resident.hpp"
static uint32_t read32(uint32_t address) {
  return *(const volatile uint32_t*)(uintptr_t)address;
}
static char* hex(char* p,uint32_t n) {
  static const char digits[]="0123456789ABCDEF";
  for(unsigned i=0;i<8;++i)*p++=digits[(n>>(28-i*4))&15];
  *p++=' ';return p;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),0) ||
     read32(MSC_PROBE_FOOTER+24)!=MSC_PROBE_BUILD) return MK61_APP_RUNTIME_ERROR;
  const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
  if(!services) return MK61_APP_RUNTIME_ERROR;
  if(read32(MSC_PROBE_ARENAS+4)!=8192 ||
     read32(MSC_PROBE_ARENAS+2*MSC_PROBE_STRIDE+4)!=8192) return MK61_APP_RUNTIME_ERROR;
  char report[96]="MSCRAM1 ";char* at=report+8;
  at=hex(at,MSC_PROBE_BUILD);at=hex(at,read32(MSC_PROBE_HEAP));
  at=hex(at,MSC_PROBE_END);at=hex(at,read32(MSC_PROBE_PREPARED));
  at=hex(at,MSC_PROBE_SESSION);
  at=hex(at,read32(MSC_PROBE_ARENAS));
  at=hex(at,read32(MSC_PROBE_ARENAS+2*MSC_PROBE_STRIDE));
  at=hex(at,read32(MSC_PROBE_ARENAS+3*MSC_PROBE_STRIDE+4));
  at=hex(at,read32(MSC_PROBE_ARENAS+4*MSC_PROBE_STRIDE+4));at[-1]='\n';
  mk61_service_write file={"MSCRPT",(const uint8_t*)report,(uint32_t)(at-report),MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,
       MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)?MK61_APP_OK:MK61_APP_RUNTIME_ERROR;
}
