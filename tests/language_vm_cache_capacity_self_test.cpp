// Real cache policies at the two proposed capacities; no device timing.
#include "language_vm_image_cache.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace language_vm;
namespace {
template<unsigned Budget,bool Mixed>
unsigned exercise() {
  using Cache=ImageCache<Budget,16,CachePolicy::REUSE_DENSITY,Mixed>;
  struct Guarded {uint64_t before=0x61CAFE;Cache cache;uint64_t after=0xCAFEB0;} guarded;
  struct Workspace {
    uint64_t before=0x123456;
    alignas(8) uint8_t prefix[COMPILER_WORKSPACE_SIZE];
    uint8_t values[VALUES_SIZE];
    uint64_t after=0x654321;
  } workspace;
  std::memset(workspace.values,0xB7,sizeof(workspace.values));
  auto& cache=guarded.cache;
  static_assert(sizeof(Cache)==Budget);
  static_assert(Cache::PAYLOAD_CAPACITY==Budget-688);
  // 15 images occupy 28,560 bytes: beyond raw24, within raw32.
  // Images are deliberately compressible; codec/source/value canaries are
  // checked on every lookup. Full compiler/INPUT execution is tested separately.
  constexpr unsigned Size=1904,Count=15;
  std::array<std::array<uint8_t,Size>,Count> originals;
  for(unsigned id=0;id<Count;++id)for(unsigned n=0;n<Size;++n)
    originals[id][n]=(uint8_t)((id+1)*13+n%29);
  unsigned warm=0;
  for(unsigned pass=0;pass<4;++pass) {
    const auto before=cache.statistics();
    for(unsigned id=0;id<Count;++id) {
      const typename Cache::Key key={1,(uint16_t)(id+1),Language::BASIC,0};
      auto h=cache.find(key,{workspace.prefix,sizeof(workspace.prefix)});
      if(!h) {
        h=cache.reserve(key,Size);assert(h);
        std::memcpy(cache.building(h),originals[id].data(),Size);
        ValidatedImage certificate={};certificate.magic=VALIDATED_MAGIC;
        certificate.size=Size;certificate.language=Language::BASIC;
        assert(cache.publish(h,certificate));
      }
      assert(cache.image(h) && cache.certificate(h));
      assert(!std::memcmp(cache.image(h),originals[id].data(),Size));
      assert(cache.release(h));
      assert(guarded.before==0x61CAFE && guarded.after==0xCAFEB0);
      assert(workspace.before==0x123456 && workspace.after==0x654321);
      for(auto value:workspace.values)assert(value==0xB7);
    }
    const auto after=cache.statistics();
    assert(after.hits-before.hits+after.misses-before.misses==Count);
    if(pass)warm+=after.misses-before.misses;
  }
  if constexpr(Budget==32768 && !Mixed)assert(!warm);
  const auto packing=cache.packing_statistics();
  if constexpr(Mixed)assert(packing.packs && packing.thaws);
  else assert(!packing.packs && !packing.thaws);
  // A live image must survive revision invalidation and allocation pressure.
  auto pinned=cache.find({1,Count,Language::BASIC,0},{workspace.prefix,sizeof(workspace.prefix)});
  assert(pinned);const auto* address=cache.image(pinned);
  cache.synchronize(2);assert(cache.image(pinned)==address);
  assert(!std::memcmp(address,originals.back().data(),Size));
  assert(!cache.find({2,Count,Language::BASIC,0}));
  auto next=cache.reserve({2,99,Language::BASIC,0},Size);assert(next);
  assert(cache.image(pinned)==address && !std::memcmp(address,originals.back().data(),Size));
  assert(cache.release(next) && cache.release(pinned));
  std::printf("capacity=%u mixed=%u warm_misses=%u packs=%u thaws=%u; values/CRC/pins/revision guards PASS\n",
              Budget,Mixed,warm,packing.packs,packing.thaws);
  return warm;
}
}
int main() {
  const auto raw=exercise<24576,false>();
  const auto mixed=exercise<24576,true>();
  const auto larger=exercise<32768,false>();
  assert(raw>mixed && !larger);
}
