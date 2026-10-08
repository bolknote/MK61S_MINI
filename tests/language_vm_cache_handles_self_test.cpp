#include "language_vm_image_cache.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>
using namespace language_vm;
template<CachePolicy Policy>
void test_handles() {
  using Cache=ImageCache<1024,8,Policy>;
  static_assert(sizeof(Cache)<=1024,"metadata is outside cache budget");
  Cache cache;
  ValidatedImage certificate={VALIDATED_MAGIC,64,32,4,64,0,1,0,Language::BASIC};
  auto first=cache.reserve({1,1,Language::BASIC,0},64);
  assert(first && !cache.find({1,1,Language::BASIC,0}));
  memset(cache.building(first),0xA1,64);
  assert(cache.publish(first,certificate));
  const auto* address=cache.image(first);
  assert(cache.pin(first));assert(cache.release(first));
  auto second=cache.reserve({1,2,Language::BASIC,0},400);
  assert(second);memset(cache.building(second),0xB2,400);
  auto large_certificate=certificate;large_certificate.size=400;
  assert(cache.publish(second,large_certificate));
  auto failed=cache.reserve({1,3,Language::BASIC,0},400);
  assert(!failed && cache.image(first)==address && address[63]==0xA1);
  assert(cache.release(second));
  failed=cache.reserve({1,3,Language::BASIC,0},400);
  assert(failed && cache.image(first)==address);
  assert(!cache.building(second) && !cache.image(second) && !cache.release(second));
  assert(cache.release(failed));
  cache.synchronize(2);assert(cache.image(first)==address && address[0]==0xA1);
  assert(!cache.pin(first));assert(cache.release(first));assert(!cache.image(first));
  assert(!cache.release(first) && cache.used()==0);
  // Rollback BUILDING records and generations cannot turn an old handle
  // into a reference to a reused slot. Exercise fragmented, changing epochs.
  uint32_t random=0x61CACE;
  typename Cache::Handle live[8]={};uint8_t markers[8]={};uint32_t revision=3;
  for(unsigned i=0;i<5000;++i) {
    random=random*1664525U+1013904223U;
    unsigned n=(random>>16)%8;
    if(live[n]) {
      const auto* p=cache.image(live[n]);assert(p && p[0]==markers[n] && p[63]==markers[n]);
      assert(cache.release(live[n]));live[n]={};
    } else {
      auto h=cache.reserve({revision,(uint16_t)(n+10),Language::BASIC,0},64);
      if(h) {
        uint8_t marker=(uint8_t)(random>>24);memset(cache.building(h),marker,64);
        if(random&1) {assert(cache.publish(h,certificate));live[n]=h;markers[n]=marker;}
        else assert(cache.release(h));
      }
    }
    if(i%73==0) cache.synchronize(++revision);
    assert(cache.used()<=Cache::PAYLOAD_CAPACITY);
  }
  for(auto h:live) if(h) assert(cache.release(h));
  cache.synchronize(++revision);assert(cache.used()==0);
  assert(cache.statistics().reservation_failures && cache.statistics().evictions);
}
int main() {
  static_assert(sizeof(ImageCache<24576>) == sizeof(ImageCache<24576,16,CachePolicy::REUSE_DENSITY>));
  test_handles<CachePolicy::LRU>();
  test_handles<CachePolicy::REUSE_DENSITY>();
  puts("VM cache handles: LRU/density, total budget, BUILDING rollback, pins, stale epochs, OOM, generation reuse, fragmented fuzz PASS");
}
