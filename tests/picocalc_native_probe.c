/* Executed on Pico H by hil_picocalc_runtime.py, through the public APP ABI. */
#include "mk61_app.h"
#include <string.h>
int main(void) {
  const mk61_app_services* s=mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_MEMORY|MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_REGISTERS|
      MK61_SERVICE_CAP_MATH|MK61_SERVICE_CAP_NUMBER_IO|MK61_SERVICE_CAP_FONT|MK61_SERVICE_CAP_SETUP);
  if(!s) return 1;
  if(s->math(MK61_SERVICE_SQRT,9,0)!=3 || s->math(MK61_SERVICE_POW,2,10)!=1024) return 2;
  char number[32];mk61_service_number_format format={123.25,number,sizeof(number),10};
  if(!s->call(MK61_SERVICE_NUMBER_FORMAT,0,0,0,&format) || strcmp(number,"123.25")) return 3;
  mk61_service_number_parse parse={0,number,0};
  if(!s->call(MK61_SERVICE_NUMBER_PARSE,0,0,0,&parse) || parse.value!=123.25 || parse.consumed!=6) return 4;
  mk61_service_lease lease={{0},0,0,0,0};
  if(!s->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,1536,&lease) || !lease.data || lease.size<1536) return 5;
  for(unsigned i=0;i<lease.size;++i) if(lease.data[i]) return 6;
  if(!s->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_SCRATCH,0,0,&lease) || lease.data) return 7;
  mk61_service_glyph glyph;
  if(!s->call(MK61_SERVICE_FONT,0,'A',sizeof(glyph),&glyph) || glyph.width!=5 || glyph.height!=8) return 8;
  double value=42;
  if(!s->call(MK61_SERVICE_REF_WRITE,MK61_SERVICE_REF_R,5,0,&value)) return 9;
  value=0;if(!s->call(MK61_SERVICE_REF_READ,MK61_SERVICE_REF_R,5,0,&value) || value!=42) return 10;
  char filename[32];
  mk61_app_snprintf(s,filename,sizeof(filename),"MK61S-NATIVE-%lu",(unsigned long)mk61_api->millis_ms());
  if(s->call(MK61_SERVICE_FILE_EXISTS,MK61_SERVICE_FILE_TEXT,0,0,filename)) return 13;
  static const uint8_t bytes[]={42,61,0,255,10};
  mk61_service_write file={filename,bytes,sizeof(bytes),MK61_SERVICE_INVALID_ID};
  if(!s->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)) return 14;
  uint8_t copied[5];
  if(mk61_api->file_size(file.id)!=sizeof(bytes) || mk61_api->file_read(file.id,0,copied,sizeof(copied))!=sizeof(copied) || memcmp(bytes,copied,sizeof(bytes))) return 15;
  if(!s->call(MK61_SERVICE_FILE_REMOVE,file.id,0,0,0)) return 16;
  mk61_setup_datetime date={2026,10,17,20,30,0};
  if(!s->call(MK61_SERVICE_SETUP,MK61_SETUP_RTC_WRITE,0,0,&date)) return 11;
  mk61_api->delay_ms(1100);
  if(!s->call(MK61_SERVICE_SETUP,MK61_SETUP_RTC_READ,0,0,&date) || date.year!=2026 || date.second<1) return 12;
  static const char text[]="PICO NATIVE API PASS";
  mk61_api->display_clear();mk61_api->display_write_m8(0,0,text,sizeof(text)-1);
  s->call(MK61_SERVICE_DEBUG_WRITE,sizeof(text)-1,0,0,(void*)text);
  return 0;
}
