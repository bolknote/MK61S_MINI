#include "loadable_buffer_services.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
namespace {
std::vector<u8> memory(8U*1024*1024);bool present=true,io_ok=true;
bool available(){return present;}
bool read(u32 at,void* out,usize n){if(!io_ok || at>memory.size() || n>memory.size()-at)return false;std::memcpy(out,memory.data()+at,n);return true;}
bool write(u32 at,const void* in,usize n){if(!io_ok || at>memory.size() || n>memory.size()-at)return false;std::memcpy(memory.data()+at,in,n);return true;}
}
int main(){
 using namespace shared_memory;using loadable_buffers::Session;
 static_assert(MK61_SERVICE_LANGUAGE_ERROR_TEXT==42 && MK61_SERVICE_BUFFER==43,"append-only operations");
 static_assert(MK61_SERVICE_MEMORY_ACQUIRE==13 && MK61_APP_SERVICES_VERSION==2,"old ABI preserved");
 assert(configure_buffer_backend({(usize)memory.size(),available,read,write,nullptr}));
 u32 stale=0,stale_window=0;
 {
  Session s;mk61_service_buffer r{};r.size=6U*1024*1024;r.access=MK61_BUFFER_EXTERNAL;
  assert(s.call(MK61_BUFFER_ACQUIRE,r) && !r.data && r.storage==MK61_BUFFER_PSRAM);stale=r.handle;
  const auto handle=r.handle;std::array<u8,513> input{},output{};
  for(unsigned i=0;i<input.size();++i)input[i]=(u8)(i*73);
  r.offset=1021;r.size=input.size();r.data=input.data();assert(s.call(MK61_BUFFER_WRITE,r));
  r.data=output.data();assert(s.call(MK61_BUFFER_READ,r) && output==input);
  r.offset=UINT32_MAX;assert(!s.call(MK61_BUFFER_READ,r));
  r.offset=0;r.size=4097;assert(!s.call(MK61_BUFFER_READ,r));
  r.offset=1021;r.size=513;r.flags=MK61_BUFFER_WINDOW_WRITABLE;r.window=0;
  assert(s.call(MK61_BUFFER_WINDOW_OPEN,r));stale_window=r.window;
  assert(!s.call(MK61_BUFFER_RELEASE,r));std::memset(r.data,0xA7,r.size);
  io_ok=false;assert(!s.call(MK61_BUFFER_WINDOW_COMMIT,r));io_ok=true;
  assert(s.call(MK61_BUFFER_WINDOW_COMMIT,r));assert(s.call(MK61_BUFFER_WINDOW_CLOSE,r));
  r.handle=handle;r.offset=1021;r.size=513;r.data=output.data();assert(s.call(MK61_BUFFER_READ,r));
  for(auto byte:output)assert(byte==0xA7);
  r.offset=0;r.size=4096;r.flags=0x6B;assert(s.call(MK61_BUFFER_FILL,r));
  r.offset=0;r.size=513;r.data=output.data();assert(s.call(MK61_BUFFER_READ,r));
  for(auto byte:output)assert(byte==0x6B);
  r.window=0;r.flags=0;assert(s.call(MK61_BUFFER_WINDOW_OPEN,r));std::memset(r.data,0,513);
  assert(!s.call(MK61_BUFFER_WINDOW_COMMIT,r));assert(s.call(MK61_BUFFER_WINDOW_CLOSE,r));
  r.data=output.data();assert(s.call(MK61_BUFFER_READ,r));for(auto byte:output)assert(byte==0x6B);
  r.window=0;r.flags=MK61_BUFFER_WINDOW_WRITABLE;assert(s.call(MK61_BUFFER_WINDOW_OPEN,r));
  // APP returns without closing its window or releasing the 6 MiB buffer.
 }
 assert(buffer_statistics().active==0 && buffer_statistics().pinned==0 && validate_buffer_invariants());
 {
  Session s;mk61_service_buffer r{};r.handle=stale;assert(!s.call(MK61_BUFFER_INFO,r));
  r.window=stale_window;assert(!s.call(MK61_BUFFER_WINDOW_CLOSE,r));
  r={};r.size=512;r.access=MK61_BUFFER_DIRECT;assert(s.call(MK61_BUFFER_ACQUIRE,r) && r.data && r.handle!=stale);
  assert(s.call(MK61_BUFFER_RELEASE,r));
  present=false;r={};r.size=512;r.access=MK61_BUFFER_EXTERNAL;assert(!s.call(MK61_BUFFER_ACQUIRE,r));
  r.access=MK61_BUFFER_BLOCK;assert(s.call(MK61_BUFFER_ACQUIRE,r) && r.data && r.storage==MK61_BUFFER_SRAM);
  assert(s.call(MK61_BUFFER_RELEASE,r));present=true;
  std::array<mk61_service_buffer,4> slots{};
  for(auto& b:slots){b.size=32;b.access=MK61_BUFFER_EXTERNAL;assert(s.call(MK61_BUFFER_ACQUIRE,b));}
  r={};r.size=32;assert(!s.call(MK61_BUFFER_ACQUIRE,r));
 }
 assert(buffer_statistics().active==0 && validate_buffer_invariants());
 std::puts("APP buffers: 6 MiB, bounds, slots, stale handles, transactional windows, pinning, return cleanup and SRAM fallback PASS");
}
