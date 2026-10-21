#include "../examples/portable-apps/WBMP/viewer.cpp"
#include "app_buffer_mock.hpp"
#include <vector>
#include <cassert>
#include <cstdio>
extern "C" { const mk61_app_api* mk61_api; }
namespace {
mk61_app_api api{};mk61_app_services services{};AppBufferMock external;
std::vector<u8> file;std::vector<std::vector<u8>> frames;
u8 borrowed[12800];unsigned key_index=0,begins=0,ends=0,reads=0;bool fail_file=false;
u32 file_size(u32 id){assert(id==42);return file.size();}
u32 file_read(u32 id,u32 offset,u8* out,u32 n){
 assert(id==42 && offset<=file.size() && n<=file.size()-offset);++reads;
 if(fail_file)return 0;std::memcpy(out,file.data()+offset,n);return n;
}
void service(){}
u32 yes(){return 1;}u32 width(){return 320;}u32 revision(){return 0;}
u32 begin(){++begins;return 1;}void end(){++ends;}
u32 present(const u8* bytes,u32 size){assert(bytes==borrowed && size==12800);frames.emplace_back(bytes,bytes+size);return 1;}
i32 key(){const i32 keys[]={MK61_APP_KEY_RIGHT,MK61_APP_KEY_FORWARD,MK61_APP_KEY_OK};assert(key_index<3);return keys[key_index++];}
void delay(u32){}
u32 call(u32 op,u32 a,u32 b,u32 c,void* payload){
 if(op==MK61_SERVICE_CAPABILITIES)return external.capabilities();
 if(op==MK61_SERVICE_BUFFER)return external.call(a,b,c,payload);
 assert(op==MK61_SERVICE_DISPLAY && a==MK61_SERVICE_DISPLAY_FRAMEBUFFER && b==sizeof(mk61_service_framebuffer));
 auto& frame=*(mk61_service_framebuffer*)payload;frame={};frame.pixels=borrowed;frame.bytes=12800;frame.width=frame.height=320;return 1;
}
const void* query(u32 id,u32 version){assert(id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION);return &services;}
void reset(bool enabled){
 assert(!external.active);external=AppBufferMock{};external.enabled=enabled;
 key_index=begins=ends=reads=0;fail_file=false;frames.clear();
 file={0,0,0x88,0,0x88,0}; // 1024 by 1024: well beyond the old 16-KiB limit.
 for(unsigned y=0;y<1024;++y)for(unsigned x=0;x<128;++x)file.push_back((u8)(x*73+y*11));
}
void verify(){
 assert(mk61_app_open_file(42)==MK61_APP_OK && frames.size()==3 && begins==1 && ends==1);
 wbmp::Info info{};assert(wbmp::inspect(file.data(),file.size(),info)==wbmp::Status::OK);
 const unsigned xs[]={0,8,8},ys[]={0,0,320};
 for(unsigned i=0;i<3;++i){std::vector<u8> expected(12800);assert(wbmp::decode_viewport(file.data(),file.size(),info,xs[i],ys[i],320,320,wbmp::Layout::PAGE_MAJOR_LSB,expected.data(),expected.size())==wbmp::Status::OK);assert(frames[i]==expected);}
 assert(!external.active && external.acquires==external.releases);
}
}
int main(){
 api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);
 api.capabilities=MK61_APP_CAP_TIME|MK61_APP_CAP_KEYBOARD|MK61_APP_CAP_FILES|MK61_APP_CAP_GRAPHICS;
 api.file_size=file_size;api.file_read=file_read;api.service=service;api.delay_ms=delay;
 api.graphics_available=yes;api.graphics_width=api.graphics_height=width;api.graphics_begin=begin;
 api.graphics_end=end;api.graphics_revision=revision;api.graphics_present=present;api.key_poll=key;api.query_service=query;
 services.magic=MK61_APP_SERVICES_MAGIC;services.version=MK61_APP_SERVICES_VERSION;services.struct_size=sizeof(services);services.call=call;mk61_api=&api;
 reset(true);verify();assert(external.writes && external.reads && external.bytes==file);
 reset(false);verify();assert(!external.acquires);
 reset(true);external.fail_acquire=true;verify();assert(!external.acquires);
 reset(true);external.fail_read=true;assert(mk61_app_open_file(42)==MK61_APP_IO_ERROR && !external.active && !begins);
 reset(true);external.fail_write=true;assert(mk61_app_open_file(42)==MK61_APP_IO_ERROR && !external.active && !begins);
 reset(true);fail_file=true;assert(mk61_app_open_file(42)==MK61_APP_IO_ERROR && !external.active && !begins);
 reset(true);file[0]=1;assert(mk61_app_open_file(42)==MK61_APP_INVALID_FILE && !external.active && !begins);
 std::puts("WBMP APP: 128-KiB image, PSRAM/SD fallback, exact pan frames and failure cleanup PASS");
}
