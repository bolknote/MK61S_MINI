// STM32duino exposes this analog-reference macro before firmware headers.
#define EXTERNAL 0
#include "../code/shared_memory.hpp"
static_assert(EXTERNAL == 0, "Shared buffers must preserve Arduino's EXTERNAL macro");
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <limits>
#include <vector>
using namespace shared_memory;
namespace {
std::vector<u8> memory(8U*1024*1024, 0xA5);
bool online = true, allowed = true, fail_read = false, fail_write = false;
bool ready() { return online; }
bool foreground() { return allowed; }
bool read(u32 at, void* bytes, usize count) {
  assert(at <= memory.size() && count <= memory.size()-at);
  if(fail_read) return false;
  std::memcpy(bytes, memory.data()+at, count); return true;
}
bool write(u32 at, const void* bytes, usize count) {
  assert(at <= memory.size() && count <= memory.size()-at);
  if(fail_write) return false;
  std::memcpy(memory.data()+at, bytes, count); return true;
}
Buffer* cache = nullptr;
bool reject_eviction = false;
unsigned evicted = 0;
EvictionDecision evict() {
  Buffer forbidden;
  assert(!forbidden.acquire(Owner::APPLICATION, 1));
  assert(!cache->reset());
  u8 b = 0; assert(!cache->read(0, &b, 1));
  assert(!configure_buffer_backend({}));
  if(reject_eviction) return EvictionDecision::KEEP;
  ++evicted; return EvictionDecision::RELEASE;
}
void clean() { assert(validate_buffer_invariants()); assert(buffer_statistics().active == 0); }
}
int main() {
  clean();
  {
    Buffer direct, fallback, missing;
    assert(direct.acquire(Owner::APPLICATION, 123));
    assert(direct.data() && direct.storage() == BufferStorage::INTERNAL);
    assert(fallback.acquire(Owner::IMAGE_VIEWER, 321, BufferAccess::BLOCK));
    assert(fallback.data());
    assert(!missing.acquire(Owner::APPLICATION, 32, BufferAccess::EXTERNAL_ONLY));
    assert(direct.fill(0x73));
    std::array<u8, 8> out{};
    assert(direct.read(8, out.data(), out.size())); for(u8 b:out) assert(b==0x73);
    assert(!direct.read(123, out.data(), 1)); assert(direct.read(123, nullptr, 0));
    assert(!direct.write(std::numeric_limits<usize>::max(), out.data(), out.size()));
    assert(!direct.write(0, nullptr, 1));
    const auto g=direct.generation(); assert(direct.acquire(Owner::APPLICATION, 100));
    assert(direct.generation()==g && direct.size()==123);
    assert(!direct.acquire(Owner::IMAGE_VIEWER, 100));
    assert(!configure_buffer_backend({}));
    assert(validate_buffer_invariants());
  }
  clean();
  assert(configure_buffer_backend({(usize)memory.size(), ready, read, write, foreground}));
  {
    Buffer a,b,c;
    assert(!a.acquire(Owner::NONE, 1)); assert(!a.acquire(Owner::APPLICATION, 0));
    assert(!a.acquire(Owner::APPLICATION, std::numeric_limits<usize>::max()));
    assert(a.acquire(Owner::APPLICATION, 3001, BufferAccess::BLOCK));
    assert(!a.data() && a.storage()==BufferStorage::EXTERNAL_DEVICE);
    assert(b.acquire(Owner::IMAGE_VIEWER, 70001, BufferAccess::EXTERNAL_ONLY));
    assert(c.acquire(Owner::MARKDOWN_VIEWER, 32777, BufferAccess::EXTERNAL_ONLY));
    assert(a.fill(0x11) && b.fill(0x22) && c.fill(0x33));
    const auto before=buffer_statistics();
    assert(b.reset()); assert(buffer_statistics().external_largest==before.external_largest);
    assert(b.acquire(Owner::IMAGE_VIEWER, 70001, BufferAccess::BLOCK));
    std::array<u8, 129> bytes{}; assert(a.read(2872,bytes.data(),129));
    for(u8 v:bytes) assert(v==0x11);
    assert(c.read(0,bytes.data(),bytes.size())); for(u8 v:bytes) assert(v==0x33);
    {
      BufferWindow window;
      assert(window.acquire(c, 17, 129, true));
      assert(buffer_statistics().pinned==1 && !c.reset());
      std::memset(window.data(),0x6B,window.size());
      assert(c.read(17,bytes.data(),bytes.size())); for(u8 v:bytes) assert(v==0x33);
      assert(window.writeback());
      assert(c.read(17,bytes.data(),bytes.size())); for(u8 v:bytes) assert(v==0x6B);
      fail_write=true; assert(!window.writeback()); fail_write=false;
    }
    assert(buffer_statistics().pinned==0);
    fail_read=true; { BufferWindow window; assert(!window.acquire(c, 0, 64)); }
    fail_read=false; assert(buffer_statistics().pinned==0);
    allowed=false;
    assert(!c.read(0, bytes.data(), 1) && !c.reset());
    Buffer denied; assert(!denied.acquire(Owner::APPLICATION, 1));
    allowed=true;
    assert(validate_buffer_invariants());
    online=false; assert(!a.ok() && !a.read(0,bytes.data(),1));
    assert(a.reset()); online=true;
  }
  clean();
  {
    Buffer optional, user; cache=&optional;
    assert(optional.acquire_cache(Owner::LOADABLE_MODULE, memory.size(), evict));
    reject_eviction=true;
    assert(!user.acquire(Owner::APPLICATION, 1024, BufferAccess::EXTERNAL_ONLY));
    reject_eviction=false;
    {
      BufferWindow window; assert(window.acquire(optional, 0, 32));
      assert(!user.acquire(Owner::APPLICATION, 1024, BufferAccess::EXTERNAL_ONLY));
    }
    assert(user.acquire(Owner::APPLICATION, 1024, BufferAccess::EXTERNAL_ONLY));
    assert(evicted==1 && !optional.ok() && optional.size()==0 && user.ok());
    assert(optional.acquire_cache(Owner::LOADABLE_MODULE, memory.size()-1024, evict));
    assert(buffer_statistics().external_used==memory.size());
    assert(user.fill(0x81)); assert(validate_buffer_invariants());
  }
  clean();
  // Mapping semantics do not change with storage: edits require writeback.
  {
    Buffer direct; assert(direct.acquire(Owner::APPLICATION, 64)); assert(direct.fill(7));
    { BufferWindow window; assert(window.acquire(direct,0,16,true)); window.data()[0]=9; }
    assert(direct.data()[0]==7);
    { BufferWindow window; assert(window.acquire(direct,0,16,true)); window.data()[0]=9; assert(window.writeback()); }
    assert(direct.data()[0]==9);
    { BufferWindow window; assert(window.acquire(direct,0,16)); assert(!window.writeback()); }
  }
  clean();
  assert(configure_buffer_backend({}));
  std::puts("Shared buffers: direct SRAM, indirect PSRAM, bounds, fragmentation, eviction, pins, transactional windows, context guards and no-device fallback PASS");
}
