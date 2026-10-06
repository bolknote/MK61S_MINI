#include "../code/shared_memory.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace shared_memory;
static unsigned evictions;
static EvictionDecision evict() { ++evictions; return EvictionDecision::RELEASE; }
static void bytes(const u8* data, usize size, u8 value) {
  for(usize i=0;i<size;++i) assert(data[i]==value);
}

int main() {
  const usize total=capacity(Arena::OVERLAY);
  auto* begin=(u8*)adjust_heap(0);
  // Keep the heap unaligned and leave too little room for the largest APP
  // once USB+bytecode are present. No libc, cache eviction, or static array.
  constexpr usize heap_size=4093, session_size=2793, image_size=6143;
  assert(adjust_heap(heap_size)==begin);
  auto* lower=begin+4096;
  const usize free=total-4096;
  Lease session(Arena::OVERLAY,Owner::USB_SCREEN,session_size);
  Lease app(Arena::APP,Owner::LOADABLE_MODULE,15336);
  assert(session.ok() && session.data()==lower && app.ok());
  assert(app.set_evictable(evict));
  memset(session.data(),0xB7,session.size()); memset(app.data(),0xA3,app.size());
  OverlayBuffer image, second;
  assert(!image.acquire(Owner::NONE,1) && !image.acquire(Owner::FOCAL,1));
  assert(!image.acquire(Owner::LOADABLE_MODULE,0));
  assert(!image.acquire(Owner::LOADABLE_MODULE,free));
  assert(!image.acquire(Owner::LOADABLE_MODULE,(usize)-1));
  assert(!evictions && app.ok() && validate_invariants());
  assert(image.acquire(Owner::LOADABLE_MODULE,image_size));
  auto* pointer=image.data();
  assert(pointer==lower+2800 && (uintptr_t(pointer)&7U)==0);
  assert(image.size()==image_size && capacity(Arena::OVERLAY)==2800);
  memset(pointer,0xD6,image.size());
  assert(image.acquire(Owner::LOADABLE_MODULE,32) && image.size()==image_size);
  assert(!image.acquire(Owner::LOADABLE_MODULE,image_size+1));
  assert(!image.acquire(Owner::VFAT_STAGE,1));
  assert(!second.acquire(Owner::LOADABLE_MODULE,1));
  assert(!session.resize_to(2801));
  assert(!adjust_heap(1) && !adjust_heap(-1) && adjust_heap(0)==begin+heap_size);
  bytes(session.data(),session.size(),0xB7); bytes(app.data(),app.size(),0xA3);
  assert(validate_invariants());

  // Every APP switch is fenced by the end of the bytecode, not just USB.
  app.reset();
  assert(capacity(Arena::OVERLAY)==2800);
  assert(!app.acquire_cache(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE));
  assert(!evictions && image.data()==pointer && validate_invariants());
  assert(app.acquire_cache(Arena::APP,Owner::LOADABLE_MODULE,10564));
  assert(app.set_evictable(evict));
  bytes(pointer,image_size,0xD6);
  session.reset(); // USB exits while a large program is suspended in INPUT.
  assert(active_owner(Arena::OVERLAY)==Owner::NONE);
  assert(!adjust_heap(1) && !adjust_heap(-1));
  assert(!session.acquire(Arena::OVERLAY,Owner::USB_SCREEN,2801));
  assert(!evictions); // Not even an idle APP can free a hole across bytecode.
  assert(session.acquire(Arena::OVERLAY,Owner::USB_SCREEN,session_size));
  memset(session.data(),0x72,session.size());
  bytes(pointer,image_size,0xD6); assert(validate_invariants());
  image.reset(); image.reset();
  assert(capacity(Arena::OVERLAY)==free-10592);
  bytes(session.data(),session.size(),0x72);
  assert(session.resize_to(6000));
  session.reset(); app.reset();
  assert(adjust_heap(-i32(heap_size))==begin+heap_size);
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());

  // The opposite lifetime ordering and an empty lower lease also coalesce.
  {
    OverlayBuffer buffer;
    assert(buffer.acquire(Owner::LOADABLE_MODULE,17) && buffer.data()==begin);
    assert(capacity(Arena::OVERLAY)==0);
    assert(!session.acquire(Arena::OVERLAY,Owner::USB_SCREEN,1));
    assert(!adjust_heap(1));
    assert(app.acquire(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE));
    assert(validate_invariants());
  }
  app.reset();
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());
  puts("OverlayBuffer: USB/APP/image coexistence, bounds, OOM, detach, RAII PASS");
}
