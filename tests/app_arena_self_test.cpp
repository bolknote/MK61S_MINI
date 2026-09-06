#include "../code/shared_memory.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <cstdint>
#include <initializer_list>
using namespace shared_memory;
static bool pinned = true;
static EvictionDecision evict() { return pinned ? EvictionDecision::KEEP : EvictionDecision::RELEASE; }
int main() {
  static_assert(OVERLAY_SIZE == 20480);
  for(usize bytes : {usize(1), usize(1924), usize(3356), usize(9152), usize(17252), usize(20140), usize(20480)}) {
    Lease app;
    assert(app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, bytes));
    assert(app.size() == bytes && (uintptr_t(app.data()) & 7) == 0);
    assert(app.set_evictable(evict));
    const usize free = OVERLAY_SIZE - ((bytes + 7) & ~usize(7));
    assert(capacity(Arena::OVERLAY) == free);
    assert(capacity(Arena::APP) + free == OVERLAY_SIZE);
    memset(app.data(), 0xA5, bytes);
    Lease prefix;
    if(free) {
      assert(prefix.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, free));
      assert(prefix.data() + free == app.data());
      memset(prefix.data(), 0x5A, free);
      assert(!contains(Arena::OVERLAY, app.data()));
      assert(contains(Arena::APP, app.data(), bytes));
      assert(validate_invariants());
      prefix.reset();
    }
    assert(!prefix.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, free + 1));
    for(usize i = 0; i < bytes; ++i) assert(app.data()[i] == 0xA5);
    pinned = false;
    assert(prefix.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, OVERLAY_SIZE));
    assert(!app.ok() && capacity(Arena::APP) == 0);
    assert(validate_invariants());
    // A live prefix cannot be overwritten to make room for an APP.
    assert(!app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 8));
    prefix.reset(); pinned = true;
    assert(validate_invariants());
  }
  puts("APP arena: exact allocations, overlap refusal, live pinning and cache eviction PASS");
}
