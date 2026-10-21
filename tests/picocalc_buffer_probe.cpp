#include "mk61_app.h"
#include <cstring>
using u8=uint8_t;
using u32=uint32_t;
static_assert(sizeof(mk61_service_buffer)==32,"APP buffer wire layout");
namespace {
const mk61_app_services* services;
void report(const char* text){services->call(MK61_SERVICE_DEBUG_WRITE,std::strlen(text),0,0,(void*)text);}
bool call(u32 operation,mk61_service_buffer& r){return mk61_app_buffer_call(services,operation,&r);}
u8 pattern(unsigned i,unsigned page){return ((i%320/16+i/320)&1)?(page?0:255):(page?255:0);}
}
int main(){
 services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_BUFFERS|MK61_SERVICE_CAP_EXTERNAL_BUFFERS|MK61_SERVICE_CAP_DEBUG_IO);
 if(!services)return 1;
 mk61_service_buffer large{},frames{};
 if(!mk61_app_buffer_acquire(services,6U*1024*1024,MK61_BUFFER_EXTERNAL,&large) || large.data || large.storage!=MK61_BUFFER_PSRAM)return 2;
 const u32 required=large.handle;
 u8 source[513],check[513];for(unsigned i=0;i<sizeof(source);++i)source[i]=(u8)(i*73);
 if(!mk61_app_buffer_write(services,required,1021,source,sizeof(source)) ||
    !mk61_app_buffer_read(services,required,1021,check,sizeof(check)) || std::memcmp(source,check,sizeof(source)))return 3;
 auto window=large;window.offset=1021;window.size=513;window.flags=MK61_BUFFER_WINDOW_WRITABLE;
 if(!call(MK61_BUFFER_WINDOW_OPEN,window) || mk61_app_buffer_release(services,required))return 4;
 std::memset(window.data,0xA7,window.size);
 if(!call(MK61_BUFFER_WINDOW_COMMIT,window) || !call(MK61_BUFFER_WINDOW_CLOSE,window))return 5;
 if(!mk61_app_buffer_read(services,required,1021,check,sizeof(check)))return 6;
 for(auto byte:check)if(byte!=0xA7)return 7;
 if(mk61_app_buffer_read(services,required,6U*1024*1024,check,1) ||
    mk61_app_buffer_read(services,required,UINT32_MAX,check,2))return 8;
 // Sector-cache invalidation uses short writes. Exercise that path thousands
 // of times, not just the large packet stream used by framebuffer data.
 for(unsigned i=0;i<4096;++i){
  const u32 word=i^0x5AA55AA5U;
  if(!mk61_app_buffer_write(services,required,i*1024+17,&word,sizeof(word)))return 15;
  if(!(i&63))mk61_api->service();
 }
 for(unsigned i=0;i<4096;++i){
  u32 word=0;
  if(!mk61_app_buffer_read(services,required,i*1024+17,&word,sizeof(word)) || word!=(i^0x5AA55AA5U))return 16;
  if(!(i&63))mk61_api->service();
 }
 report("PSRAM SMALL IO PASS\n");
 if(!mk61_app_buffer_acquire(services,25600,MK61_BUFFER_EXTERNAL,&frames) || frames.data)return 9;
 for(unsigned page=0;page<2;++page)for(unsigned at=0;at<12800;at+=512){
  for(unsigned i=0;i<512;++i)source[i]=pattern(at+i,page);
  if(!mk61_app_buffer_write(services,frames.handle,page*12800+at,source,512))return 10;
  mk61_api->service();
 }
 if(!mk61_api->graphics_begin())return 11;
 for(unsigned stage=0;stage<3;++stage){
  auto frame=frames;frame.offset=(stage&1)*12800;frame.size=12800;
  if(!call(MK61_BUFFER_PRESENT,frame))return 12;
  char text[]="PSRAM FRAME 0 READY\n";text[12]=(char)('0'+stage);report(text);
  if(mk61_api->key_wait()!=MK61_APP_KEY_OK){mk61_api->graphics_end();return 13;}
 }
 mk61_api->graphics_end();
 // Deliberately leave a live window and both required buffers on return.
 window=large;window.offset=1021;window.size=513;window.window=0;window.flags=MK61_BUFFER_WINDOW_WRITABLE;
 if(!call(MK61_BUFFER_WINDOW_OPEN,window))return 14;
 report("PSRAM BUFFER PASS\n");return 0;
}
