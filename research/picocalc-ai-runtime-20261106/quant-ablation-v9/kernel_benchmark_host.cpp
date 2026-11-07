#include "mk61_app.h"
#include <chrono>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cassert>
extern int bench_main();
const mk61_app_api* mk61_api=nullptr;
uint32_t mk61_app_image_crc=0,mk61_app_current_kind=4;
static unsigned rows=0;static bool finished=false;
static uint32_t call(uint32_t op,uint32_t a,uint32_t,uint32_t,void*p){
 if(op==MK61_SERVICE_CAPABILITIES)return MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO;
 if(op==MK61_SERVICE_MICROS)return uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
 if(op==MK61_SERVICE_DEBUG_WRITE){const char*s=static_cast<char*>(p);if(!std::strncmp(s,"AI_QKERNEL mode=",16))++rows;if(!std::strncmp(s,"AI_QKERNEL DONE",15))finished=true;std::fwrite(s,1,a,stdout);return a;}
 return 0;
}
static int format(char*out,uint32_t cap,const char*fmt,va_list args){return std::vsnprintf(out,cap,fmt,args);}
int main(){
 static mk61_app_services services{};services.magic=MK61_APP_SERVICES_MAGIC;services.version=MK61_APP_SERVICES_VERSION;services.struct_size=sizeof(services);services.call=call;services.format=format;
 static mk61_app_api api{};api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);api.service=[](){};api.display_clear=[]()->uint32_t{return 0;};api.display_write_m8=[](uint32_t,uint32_t,const char*,uint32_t)->uint32_t{return 0;};api.key_poll=[]()->int32_t{return -1;};api.query_service=[](uint32_t id,uint32_t version)->const void*{return id==MK61_APP_SERVICE_COMMON&&version==MK61_APP_SERVICES_VERSION?&services:nullptr;};mk61_api=&api;
 const int result=bench_main();assert(result==0);assert(rows==18&&finished);std::puts("HOST benchmark protocol/18records/all numerical checks PASS");
}
