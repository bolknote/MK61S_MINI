#include "language_vm_image_cache.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <random>
using namespace language_vm;

namespace language_vm {
struct ImageCacheTestAccess {
  template<class C> static bool pack(C& c,typename C::Handle h,typename C::Scratch s) {
    auto* e=c.entry(h);return e && c.pack(*e,c.checked(s));
  }
  template<class C> static bool packed(C& c,typename C::Handle h) {
    auto* e=c.entry(h);return e && e->state==C::State::PACKED;
  }
  template<class C> static void corrupt(C& c,typename C::Handle h) {
    auto* e=c.entry(h);assert(e && e->state==C::State::PACKED && e->size>1);
    c.bytes_[e->offset+1]^=1; // Valid literal corruption, not only malformed tokens.
  }
  template<class C> static void layout(C& c) {
    unsigned total=0;
    for(const auto& a:c.entries_) if(a.state!=C::State::EMPTY) {
      assert(a.size && a.offset%8==0 && a.offset+c.allocated(a.size)<=C::PAYLOAD_CAPACITY);
      assert(a.state!=C::State::PACKED || (!a.pins && a.validated.size>=HEADER_SIZE));
      total+=c.allocated(a.size);
      for(const auto& b:c.entries_) if(&a!=&b && b.state!=C::State::EMPTY)
        assert(a.offset+c.allocated(a.size)<=b.offset || b.offset+c.allocated(b.size)<=a.offset);
    }
    assert(total==c.used() && total<=C::PAYLOAD_CAPACITY);
  }
};
}
using Cache=ImageCache<8192,8,CachePolicy::REUSE_DENSITY,true>;
struct Loan {
  uint64_t before=UINT64_C(0xABCDEF1234567890);
  alignas(8) uint8_t prefix[COMPILER_WORKSPACE_SIZE];
  uint8_t values[VALUES_SIZE];
  uint64_t after=UINT64_C(0x13572468ABCDEF09);
  Loan(){memset(prefix,0xA7,sizeof(prefix));memset(values,0xB7,sizeof(values));}
  void check() const {
    assert(before==UINT64_C(0xABCDEF1234567890) && after==UINT64_C(0x13572468ABCDEF09));
    for(auto b:values)assert(b==0xB7);
  }
  Cache::Scratch scratch(){return {prefix,sizeof(prefix)};}
};
ValidatedImage certificate(unsigned bytes,Language lang=Language::BASIC) {
  return {VALIDATED_MAGIC,(uint16_t)bytes,32,4,(uint16_t)bytes,0,1,0,lang,false};
}
template<class C>
typename C::Handle publish(C& c,typename C::Key key,const std::vector<uint8_t>& bytes) {
  auto h=c.reserve(key,(uint16_t)bytes.size());
  if(h) {
    assert(!c.image(h));
    memcpy(c.building(h),bytes.data(),bytes.size());
    assert(c.publish(h,certificate(bytes.size(),key.language)));
    assert(c.image(h) && !memcmp(c.image(h),bytes.data(),bytes.size()));
  }
  return h;
}
int main() {
  static_assert(sizeof(ImageCache<24576,16,CachePolicy::REUSE_DENSITY,true>)==24576);
  static_assert(sizeof(ImageCache<24576,16,CachePolicy::REUSE_DENSITY,true>)==sizeof(ImageCache<24576>));
  static_assert(ImageCache<24576,16,CachePolicy::REUSE_DENSITY,true>::metadata_bytes()==880);
  static_assert(ImageCache<24576,16,CachePolicy::REUSE_DENSITY,true>::PAYLOAD_CAPACITY==23696);
  Loan loan;
  Cache c;
  const Cache::Key key={1,1,Language::BASIC,0};
  std::vector<uint8_t> raw(2048,0x62);
  auto h=publish(c,key,raw);assert(h && c.release(h));
  assert(ImageCacheTestAccess::pack(c,h,loan.scratch()));
  assert(ImageCacheTestAccess::packed(c,h) && !c.image(h) && !c.certificate(h) && !c.pin(h));
  auto hot=c.find(key,loan.scratch());assert(hot && hot.generation==h.generation);
  assert(!memcmp(c.image(hot),raw.data(),raw.size()) && c.certificate(hot)->magic==VALIDATED_MAGIC);
  assert(c.release(hot) && c.packing_statistics().packs==1 && c.packing_statistics().thaws==1);
  loan.check();ImageCacheTestAccess::layout(c);
  // Overlapping and unaligned loans are not used; bounded internal scratch
  // may still suffice, but neither cache metadata nor adjacent values change.
  assert(ImageCacheTestAccess::pack(c,h,{reinterpret_cast<uint8_t*>(&c),sizeof(c)}));
  hot=c.find(key,{loan.prefix+1,sizeof(loan.prefix)-1});assert(hot && c.release(hot));
  loan.check();ImageCacheTestAccess::layout(c);
  // CRC covers the complete decoded image, including header bytes. Corrupted
  // literal data that decodes structurally must never expose a certificate.
  assert(ImageCacheTestAccess::pack(c,h,loan.scratch()));
  ImageCacheTestAccess::corrupt(c,h);
  assert(!c.find(key,loan.scratch()) && !c.image(h) && !c.release(h));
  h=publish(c,key,raw);assert(h && c.release(h));
  hot=c.find(key,loan.scratch());assert(hot && c.release(hot));
  // Packing cannot create a new slot or execute an image above payload.
  assert(!c.reserve({1,2,Language::BASIC,0},(uint16_t)(Cache::PAYLOAD_CAPACITY+1)));
  // Incompressible bounded output fails transactionally, preserving raw bytes.
  std::mt19937 rng(0x61CA7);
  std::vector<uint8_t> noise(2048);for(auto& b:noise)b=(uint8_t)rng();
  auto n=publish(c,{1,2,Language::BASIC,0},noise);assert(n && c.release(n));
  assert(!ImageCacheTestAccess::pack(c,n,loan.scratch()));
  n=c.find({1,2,Language::BASIC,0},loan.scratch());
  assert(n && !memcmp(c.image(n),noise.data(),noise.size()) && c.release(n));
  {
    // No loan and a pinned neighbour leave too little simultaneous raw/thaw
    // space. Drop only the requested packed entry; the other pointer survives.
    using Tiny=ImageCache<1024,4,CachePolicy::REUSE_DENSITY,true>;
    Tiny tiny;std::vector<uint8_t> small(512,0x62), neighbour(noise.begin(),noise.begin()+512);
    auto packed=publish(tiny,{1,1,Language::BASIC,0},small);assert(packed && tiny.release(packed));
    assert(ImageCacheTestAccess::pack(tiny,packed,{loan.prefix,sizeof(loan.prefix)}));
    auto pinned=publish(tiny,{1,2,Language::BASIC,0},neighbour);assert(pinned);
    const auto* pointer=tiny.image(pinned);
    assert(!tiny.find({1,1,Language::BASIC,0}) && !tiny.image(packed));
    assert(tiny.image(pinned)==pointer && !memcmp(pointer,neighbour.data(),neighbour.size()));
    assert(tiny.used()==512 && tiny.release(pinned));
    ImageCacheTestAccess::layout(tiny);loan.check();
  }
  {
    using Lru=ImageCache<8192,8,CachePolicy::LRU,true>;
    Lru lru;auto handle=publish(lru,{1,1,Language::FOCAL,0},raw);
    assert(handle && lru.release(handle));
    assert(ImageCacheTestAccess::pack(lru,handle,{loan.prefix,sizeof(loan.prefix)}));
    handle=lru.find({1,1,Language::FOCAL,0},{loan.prefix,sizeof(loan.prefix)});
    assert(handle && !memcmp(lru.image(handle),raw.data(),raw.size()) && lru.release(handle));
    assert(lru.packing_statistics().packs==1 && lru.packing_statistics().thaws==1);
    ImageCacheTestAccess::layout(lru);loan.check();
  }
  // Pins remain immutable across real packing, fragmentation, OOM, stale
  // epochs, slot reuse and both language keys under the same source inode.
  Cache cache;
  std::vector<uint8_t> images[20];
  for(unsigned i=0;i<20;++i) {
    images[i].resize(64+(rng()%1500));
    for(unsigned j=0;j<images[i].size();++j) images[i][j]=(uint8_t)(j%9?i:rng());
  }
  Cache::Handle live[20]={};const uint8_t* pointers[20]={};
  uint32_t revision=1;
  unsigned publications=0;
  for(unsigned step=0;step<3000;++step) {
    const unsigned i=rng()%20;
    if(live[i]) {assert(cache.release(live[i]));live[i]={};}
    else {
      const Cache::Key k={revision,(uint16_t)(1+i/2),i%2?Language::FOCAL:Language::BASIC,0};
      auto found=cache.find(k,loan.scratch());
      if(!found) {found=publish(cache,k,images[i]);publications+=bool(found);}
      if(found) {
        assert(cache.image(found) && !memcmp(cache.image(found),images[i].data(),images[i].size()));
        if(rng()%3) {pointers[i]=cache.image(found);live[i]=found;}
        else assert(cache.release(found));
      }
    }
    if(step%41==0)cache.synchronize(++revision);
    for(unsigned j=0;j<20;++j) if(live[j]) {
      assert(cache.image(live[j])==pointers[j]);
      assert(!memcmp(pointers[j],images[j].data(),images[j].size()));
    }
    loan.check();ImageCacheTestAccess::layout(cache);
  }
  for(auto active:live)if(active)assert(cache.release(active));
  cache.synchronize(++revision);assert(cache.used()==0);
  assert(publications>100 && cache.statistics().reservation_failures && cache.statistics().invalidations);
  std::puts("VM mixed cache: fixed24K/688B metadata, raw/packed CRC, bounded encode, disjoint loan/values, safe thaw failure, LRU/density, pins/stale/slots/fragmentation/generation fuzz PASS");
}
