#include "../code/shared_memory.hpp"
#include "../code/mpu_guard_policy.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>

using namespace shared_memory;
static usize rounded(usize n) { return (n + 31U) & ~usize(31); }
static void bytes(const u8* p, usize n, u8 value) {
  for(usize i = 0; i < n; ++i) assert(p[i] == value);
}
static uintptr_t oracle(uintptr_t floor, uintptr_t end, usize count,
                        const LifetimeBuffer* buffers, unsigned number,
                        const Lease& app, bool for_app=false) {
  const usize size = rounded(count);
  if(size > end - floor) return 0;
  for(uintptr_t at = (end-size)&~uintptr_t(31); at >= floor;) {
    if(for_app && ((end-at-size)&255U)) {
      if(at < floor+32) break;
      at -= 32;continue;
    }
    bool overlaps = app.ok() && at < (uintptr_t)app.data()+rounded(app.size()) &&
        (uintptr_t)app.data() < at+size;
    for(unsigned i=0; i<number; ++i) if(buffers[i].ok())
      overlaps |= at < (uintptr_t)buffers[i].data()+rounded(buffers[i].size()) &&
          (uintptr_t)buffers[i].data() < at+size;
    if(!overlaps) return at;
    if(at < floor+32) break;
    at -= 32;
  }
  return 0;
}
int main() {
  const usize total = capacity(Arena::OVERLAY);
  auto* const begin = (u8*)adjust_heap(0);
  const uintptr_t end = (uintptr_t)begin+total;
  assert(total==49152 && validate_invariants());
  const Owner owners[] = {Owner::M61_RUNTIME,Owner::USB_FRAMEBUFFER,Owner::STORAGE_WORKSPACE};
  std::array<unsigned,3> order = {{0,1,2}};
  do {
    for(unsigned allocation_order=0; allocation_order<6; ++allocation_order) {
      std::array<unsigned,3> create={{0,1,2}};
      for(unsigned i=0;i<allocation_order;++i) std::next_permutation(create.begin(),create.end());
      LifetimeBuffer buffers[2]; Lease app,stage; OverlayBuffer transport;
      assert(stage.acquire(Arena::OVERLAY,Owner::VFAT_STAGE,STAGE_INDEX_SIZE));
      assert(transport.acquire(Owner::USB_TRANSPORT,8264));
      memset(stage.data(),0x4A,stage.size()); memset(transport.data(),0xB5,transport.size());
      for(unsigned which:create) {
        if(which==2) { assert(app.acquire(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE)); memset(app.data(),0xC3,app.size()); }
        else { assert(buffers[which].acquire(owners[which],which?1536:2100)); memset(buffers[which].data(),0x51+which,buffers[which].size()); }
        assert(validate_invariants());
      }
      auto* app_address=app.data();
      for(unsigned which:order) {
        if(which==2) app.reset(); else buffers[which].reset();
        if(app.ok()) {assert(app.data()==app_address);bytes(app.data(),app.size(),0xC3);}
        for(unsigned i=0;i<2;++i) if(buffers[i].ok()) bytes(buffers[i].data(),buffers[i].size(),0x51+i);
        bytes(stage.data(),stage.size(),0x4A);bytes(transport.data(),transport.size(),0xB5);
        assert(validate_invariants());
      }
      // An upper independent buffer may survive the release of the prefix.
      stage.reset();transport.reset();
      assert(capacity(Arena::OVERLAY)==total && validate_invariants());
    }
  } while(std::next_permutation(order.begin(),order.end()));

  // Differential address oracle: deliberately fragment and reuse high gaps,
  // including buffers started after APP and stopped before or after it.
  LifetimeBuffer buffers[3]; Lease app,stage;
  assert(stage.acquire(Arena::OVERLAY,Owner::VFAT_STAGE,STAGE_INDEX_SIZE));
  memset(stage.data(),0x7A,stage.size());
  const uintptr_t floor=(uintptr_t)stage.data()+rounded(stage.size());
  unsigned rng=0x61F411U;
  for(unsigned step=0;step<6000;++step) {
    rng=rng*1664525U+1013904223U;
    const unsigned which=(rng>>16)%4;
    if(which==3) {
      if(app.ok()) app.reset();
      else {
        const usize wanted=32+((rng>>2)%(APP_MAX_SIZE-32));
        Lease absent;
        const uintptr_t expected=oracle(floor,end,wanted,buffers,3,absent,true);
        assert(app.acquire(Arena::APP,Owner::LOADABLE_MODULE,wanted)==(expected!=0));
        if(app.ok()) {assert((uintptr_t)app.data()==expected);memset(app.data(),0xAD,app.size());}
      }
    } else if(buffers[which].ok()) buffers[which].reset();
    else {
      const usize wanted=1+(rng%14000);
      const uintptr_t expected=oracle(floor,end,wanted,buffers,3,app);
      assert(buffers[which].acquire(owners[which],wanted)==(expected!=0));
      if(buffers[which].ok()) {assert((uintptr_t)buffers[which].data()==expected);memset(buffers[which].data(),0x60+which,wanted);}
    }
    for(unsigned i=0;i<3;++i) if(buffers[i].ok()) bytes(buffers[i].data(),buffers[i].size(),0x60+i);
    if(app.ok()) bytes(app.data(),app.size(),0xAD);
    bytes(stage.data(),stage.size(),0x7A);
    if(app.ok()) {
      const u32 native_end=0x2001BF00U-(u32)(end-(uintptr_t)app.data()-rounded(app.size()));
      u32 cursor=native_end-(u32)rounded(app.size());unsigned regions=0;
      while(cursor<native_end) {
        const auto region=mpu_guard_policy::next_app_region(cursor,native_end);
        assert(region.size && ++regions<=mpu_guard_policy::APP_REGION_COUNT);
        cursor=region.end;
      }
    }
    assert(validate_invariants());
  }
  app.reset();for(auto& b:buffers)b.reset();stage.reset();
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());

  LifetimeBuffer high,duplicate;
  assert(!high.acquire(Owner::NONE,1));
  assert(!high.acquire(Owner::M61_RUNTIME,0));
  assert(!high.acquire(Owner::M61_RUNTIME,~usize(0)));
  assert(high.acquire(Owner::M61_RUNTIME,33));
  assert(high.acquire(Owner::M61_RUNTIME,1));
  assert(!high.acquire(Owner::M61_RUNTIME,34));
  assert(!duplicate.acquire(Owner::M61_RUNTIME,1));
  memset(high.data(),0x82,high.size());
  const usize gap=total-rounded(high.size());
  assert(adjust_heap((i32)gap)==begin);
  assert(!adjust_heap(1) && !adjust_heap(INT32_MAX) && !adjust_heap(INT32_MIN));
  bytes(high.data(),high.size(),0x82);assert(validate_invariants());
  assert(adjust_heap(-(i32)gap)==begin+gap);high.reset();
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());
  puts("Lifetime buffers: all 36 allocation/release orders, stable APP, 6000 independent gap-oracle steps, canaries, OOM and heap bounds PASS");
}
