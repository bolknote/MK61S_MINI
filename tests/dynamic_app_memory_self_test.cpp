#include "../code/shared_memory.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>

using namespace shared_memory;
static bool pinned = true;
static unsigned eviction_calls;
static EvictionDecision evict() {
  ++eviction_calls;
  return pinned ? EvictionDecision::KEEP : EvictionDecision::RELEASE;
}
static usize aligned(usize size) { return (size + 31U) & ~usize(31); }
static void check_bytes(const u8* memory, usize size, u8 value) {
  for(usize i = 0; i < size; ++i) assert(memory[i] == value);
}

int main() {
  const usize total = capacity(Arena::OVERLAY);
  auto* const begin = static_cast<u8*>(adjust_heap(0));
  auto* const end = begin + total;
  assert(total > APP_MAX_SIZE + STAGE_INDEX_SIZE);
  assert(capacity(Arena::APP) == 0 && validate_invariants());

  // A pre-existing libc allocation moves only the free lower boundary.
  assert(adjust_heap(123) == begin);
  memset(begin, 0x39, 123);
  assert(capacity(Arena::OVERLAY) == total - 128);
  Lease staging;
  assert(staging.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, STAGE_INDEX_SIZE));
  assert(staging.data() == begin + 128);
  assert(staging.set_evictable(evict));
  memset(staging.data(), 0x5A, staging.size());
  for(usize bytes : {usize(1), usize(1924), usize(3356), usize(9216),
                    usize(17252), usize(20140), APP_MAX_SIZE}) {
    Lease app;
    assert(app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, bytes));
    assert(app.data() == end - aligned(bytes));
    assert(app.size() == bytes && capacity(Arena::APP) == aligned(bytes));
    assert(capacity(Arena::OVERLAY) == total - 128 - aligned(bytes));
    assert(app.set_evictable(evict));
    memset(app.data(), 0xA5, bytes);
    assert(!contains(Arena::OVERLAY, app.data()));
    assert(contains(Arena::APP, app.data(), bytes));
    assert(!adjust_heap(1) && !adjust_heap(-1));
    assert(adjust_heap(0) == begin + 123);
    assert(staging.data() == begin + 128);
    check_bytes(staging.data(), staging.size(), 0x5A);
    check_bytes(begin, 123, 0x39);
    check_bytes(app.data(), bytes, 0xA5);
    assert(validate_invariants());
    app.reset();
    assert(capacity(Arena::APP) == 0 && capacity(Arena::OVERLAY) == total - 128);
    check_bytes(staging.data(), staging.size(), 0x5A);
  }
  assert(eviction_calls == 0);
  staging.reset();
  assert(adjust_heap(-123) == begin + 123);

  // A loader must not evict a lower buffer to force a large APP into RAM.
  pinned = false;
  assert(staging.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, total - 1024));
  assert(staging.set_evictable(evict));
  memset(staging.data(), 0x67, staging.size());
  Lease app;
  assert(!app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 1025));
  assert(eviction_calls == 0 && staging.ok());
  check_bytes(staging.data(), staging.size(), 0x67);
  staging.reset();

  // Heap may consume exactly the remaining gap, never the rounded APP lease.
  assert(app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 33));
  assert(app.set_evictable(evict));
  memset(app.data(), 0xA5, app.size());
  const usize gap = total - 64;
  assert(adjust_heap((i32) gap) == begin);
  assert(!adjust_heap(1) && !adjust_heap(INT32_MAX));
  assert(!adjust_heap(INT32_MIN) && !adjust_heap(-(i32)gap - 1));
  assert(eviction_calls == 0 && app.ok());
  assert(capacity(Arena::OVERLAY) == 0 && validate_invariants());
  check_bytes(app.data(), app.size(), 0xA5);
  assert(adjust_heap(-(i32)gap) == begin + gap);

  // A running APP remains pinned; an idle one can yield its memory to staging.
  pinned = true;
  assert(!staging.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, total));
  assert(app.ok());
  pinned = false;
  assert(staging.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, total));
  assert(!app.ok() && capacity(Arena::APP) == 0);
  staging.reset();
  assert(!app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, APP_MAX_SIZE + 1));
  assert(adjust_heap((i32)total) == begin);
  assert(!app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 1));
  assert(adjust_heap(-(i32)total) == end);
  assert(capacity(Arena::OVERLAY) == total && validate_invariants());
  puts("Dynamic RAM: heap/APP/staging boundaries, stable buffers, OOM, unload and pinning PASS");
}
