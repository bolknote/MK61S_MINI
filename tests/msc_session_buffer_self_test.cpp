// Exercise the production manager with all simultaneously live MSC users.
#include "../code/shared_memory.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace shared_memory;
static unsigned evictions;
static EvictionDecision evict() { ++evictions; return EvictionDecision::RELEASE; }
static void check(const u8* data, usize n, u8 value) {
  for(usize i=0;i<n;++i) assert(data[i]==value);
}
int main() {
  const usize total=capacity(Arena::OVERLAY);
  auto* begin=(u8*)adjust_heap(0);
  // Qualify the largest format-valid disk APP together with the full stage
  // index and the unchanged F411 8-KiB packet. Never borrow fixed workspace.
  for(unsigned cycle=0;cycle<100;++cycle) {
    Lease stage(Arena::OVERLAY,Owner::VFAT_STAGE,STAGE_INDEX_SIZE);
    Lease app(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE);
    assert(stage.ok() && app.ok() && app.set_evictable(evict));
    memset(stage.data(),0x51,stage.size()); memset(app.data(),0x83,app.size());
    OverlayBuffer transport, second;
    assert(!transport.acquire(Owner::USB_TRANSPORT,total)); // OOM is atomic.
    assert(!transport.ok() && !evictions && validate_invariants());
    assert(transport.acquire(Owner::USB_TRANSPORT,8264));
    assert(transport.data()==begin+STAGE_INDEX_SIZE);
    assert((uintptr_t(transport.data())&7U)==0 && transport.size()==8264);
    assert(!second.acquire(Owner::USB_TRANSPORT,1));
    memset(transport.data(),0xD7,transport.size());
    assert(!adjust_heap(8) && !stage.resize_to(STAGE_INDEX_SIZE+8));
    assert(!stage.acquire(Arena::OVERLAY,Owner::USB_SCREEN,1));
    check(stage.data(),stage.size(),0x51); check(app.data(),app.size(),0x83);
    assert(validate_invariants());
    // Both teardown orders retain the stable USB address until its owner
    // explicitly releases it. Afterwards another client can use every byte.
    if(cycle&1) stage.reset();
    check(transport.data(),transport.size(),0xD7);
    transport.reset(); transport.reset();
    if(stage.ok()) stage.reset();
    assert(capacity(Arena::OVERLAY)==total-APP_MAX_SIZE);
    Lease other(Arena::OVERLAY,Owner::USB_SCREEN,total-APP_MAX_SIZE);
    assert(other.ok() && other.data()==begin);
    memset(other.data(),0x29,other.size());
    check(app.data(),app.size(),0x83);
    assert(!evictions && validate_invariants());
    other.reset();app.reset();
    assert(capacity(Arena::OVERLAY)==total && adjust_heap(0)==begin);
    assert(validate_invariants());
  }
  puts("MSC session RAM: 100 prepare/OOM/release/reuse cycles with pinned APP+stage PASS");
}
