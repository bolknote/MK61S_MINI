#include "shared_memory.hpp"
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using namespace shared_memory;
static bool pinned=true,try_nested=false;
static unsigned evictions=0;
static EvictionDecision evict() {
  ++evictions;
  if(try_nested) assert(allocate_retained_buffer(8)==nullptr);
  return pinned ? EvictionDecision::KEEP:EvictionDecision::RELEASE;
}
static void check(const u8* p,usize n,u8 value) {for(usize i=0;i<n;++i)assert(p[i]==value);}
int main() {
  const usize total=capacity(Arena::OVERLAY);
  u8* const begin=(u8*)adjust_heap(0);
  assert(total>8192 && !allocate_retained_buffer(0));
  for(usize n:{usize(INT32_MAX),usize(-1)}) {
    assert(!allocate_retained_buffer(n));assert(adjust_heap(0)==begin);
  }
  for(unsigned misalign=0;misalign<8;++misalign) for(usize n:{usize(1),usize(2),usize(7),usize(8),usize(9),usize(31),usize(127),usize(8192)}) {
    std::memset(begin,0xA7,total);
    assert(adjust_heap(misalign)==begin);
    u8* p=(u8*)allocate_retained_buffer(n);
    const usize offset=(misalign+7U)&~usize(7),rounded=(n+7U)&~usize(7);
    assert(p==begin+offset && !(uintptr_t(p)&7));
    check(begin,offset,0xA7);check(p,n,0);check(p+n,rounded-n,0xA7);
    assert(adjust_heap(0)==begin+offset+rounded);
    check(begin+offset+rounded,total-offset-rounded,0xA7);
    assert(adjust_heap(-i32(offset+rounded))==begin+offset+rounded);
    assert(validate_invariants());
  }
  Lease staging;assert(staging.acquire_cache(Arena::OVERLAY,Owner::VFAT_STAGE,STAGE_INDEX_SIZE));
  assert(staging.set_evictable(evict));std::memset(staging.data(),0x5A,staging.size());
  assert(!allocate_retained_buffer(8) && evictions==1);
  assert(adjust_heap(0)==begin && staging.ok());check(staging.data(),staging.size(),0x5A);
  pinned=false;try_nested=true;
  assert(allocate_retained_buffer(8)==begin && evictions==2 && !staging.ok());
  check(begin,8,0);assert(adjust_heap(-8)==begin+8);try_nested=false;
  Lease app;assert(app.acquire_cache(Arena::APP,Owner::LOADABLE_MODULE,33));
  assert(app.set_evictable(evict));std::memset(app.data(),0x69,app.size());
  const usize gap=total-capacity(Arena::APP);
  assert(allocate_retained_buffer(gap)==begin);
  check(begin,gap,0);check(app.data(),app.size(),0x69);
  assert(!allocate_retained_buffer(1) && adjust_heap(0)==begin+gap);
  assert(evictions==2 && app.ok() && validate_invariants());
  assert(adjust_heap(-i32(gap))==begin+gap);app.reset();
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());
  std::puts("Retained allocation: 8-byte alignment, zeroing, padding, atomic heap OOM, pinned APP/cache, eviction callback isolation PASS");
}
