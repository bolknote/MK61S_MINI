#ifndef MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#define MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#include "language_vm_abi.hpp"
#include <string.h>
namespace language_vm {
// Capacity includes the bounded directory and counters. No heap allocation;
// only pinned, generation-checked handles expose immutable program bytes.
template<unsigned Capacity, unsigned Slots=16>
class ImageCache {
 public:
  struct Key { uint32_t revision; uint16_t id; Language language; uint8_t reserved=0; };
  struct Handle {
    uint32_t generation=0; uint16_t slot=0xFFFF;
    explicit operator bool() const {return generation && slot<Slots;}
  };
  struct Statistics {
    uint32_t lookups=0,hits=0,misses=0,reservations=0,reservation_failures=0,
             publications=0,evictions=0,invalidations=0;
  };
 private:
  enum class State:uint8_t { EMPTY, BUILDING, READY, STALE };
  struct Entry {
    Key key={}; ValidatedImage validated={}; uint32_t age=0,generation=0;
    uint16_t offset=0,size=0; uint8_t pins=0; State state=State::EMPTY;
    uint16_t reserved=0;
  };
  static constexpr unsigned Metadata=sizeof(Entry)*Slots+sizeof(Statistics)+16;
 public:
  static_assert(Capacity>=Metadata+32,"cache budget must include metadata and a small image");
  static constexpr unsigned PAYLOAD_CAPACITY=(Capacity-Metadata)&~7U;
  static constexpr unsigned metadata_bytes() {return Metadata;}
  const Statistics& statistics() const {return statistics_;}
  unsigned used() const {
    unsigned n=0;for(const auto& e:entries_) if(e.state!=State::EMPTY) n+=allocated(e.size);return n;
  }
  void synchronize(uint32_t revision) {
    revision_=revision;
    for(auto& e:entries_) if(e.state!=State::EMPTY && e.key.revision!=revision) {
      if(e.state!=State::STALE) ++statistics_.invalidations;
      e.state=State::STALE;if(!e.pins) e={};
    }
  }
  Handle find(Key key) {
    ++statistics_.lookups;synchronize(key.revision);
    for(unsigned i=0;i<Slots;++i) {
      auto& e=entries_[i];
      if(e.state==State::READY && same(e.key,key) && e.pins!=255) {
        ++e.pins;e.age=age();++statistics_.hits;return {e.generation,(uint16_t)i};
      }
    }
    ++statistics_.misses;return {};
  }
  Handle reserve(Key key,uint16_t size) {
    synchronize(key.revision);
    if(size<HEADER_SIZE || allocated(size)>PAYLOAD_CAPACITY || key.id==0xFFFF || key.reserved ||
       (key.language!=Language::BASIC && key.language!=Language::FOCAL)) return failed();
    for(;;) {
      unsigned slot=Slots,offset=0;
      for(unsigned i=0;i<Slots;++i) if(entries_[i].state==State::EMPTY) {slot=i;break;}
      if(slot<Slots && hole(allocated(size),offset)) {
        auto& e=entries_[slot];e={};e.key=key;e.size=size;e.offset=(uint16_t)offset;
        e.state=State::BUILDING;e.pins=1;e.generation=++generation_;
        if(!e.generation) e.generation=++generation_;
        e.age=age();++statistics_.reservations;return {e.generation,(uint16_t)slot};
      }
      if(!pinned()) compact();
      if(slot<Slots && hole(allocated(size),offset)) continue;
      unsigned oldest=Slots;
      for(unsigned i=0;i<Slots;++i) {
        const auto& e=entries_[i];
        if(e.state!=State::EMPTY && !e.pins && (oldest==Slots || e.age<entries_[oldest].age)) oldest=i;
      }
      if(oldest==Slots) return failed();
      entries_[oldest]={};++statistics_.evictions;
    }
  }
  uint8_t* building(Handle h) {
    auto* e=entry(h);return e && e->pins && e->state==State::BUILDING ? bytes_+e->offset : nullptr;
  }
  const uint8_t* image(Handle h) const {
    const auto* e=entry(h);
    return e && e->pins && (e->state==State::READY || e->state==State::STALE) ? bytes_+e->offset : nullptr;
  }
  const ValidatedImage* certificate(Handle h) const {
    const auto* e=entry(h);return image(h) ? &e->validated : nullptr;
  }
  bool publish(Handle h,const ValidatedImage& validated) {
    auto* e=entry(h);
    if(!e || e->state!=State::BUILDING || !e->pins || e->key.revision!=revision_ ||
       validated.magic!=VALIDATED_MAGIC || validated.size!=e->size || validated.flags>15 ||
       validated.language!=e->key.language || (validated.flags&1) ||
       ((validated.flags&RESOURCE_FLAG) && !(validated.flags&OWNED_RESOURCE_FLAG))) return false;
    e->validated=validated;e->state=State::READY;e->age=age();++statistics_.publications;return true;
  }
  bool release(Handle h) {
    auto* e=entry(h);if(!e || !e->pins) return false;
    --e->pins;if(!e->pins && (e->state==State::BUILDING || e->state==State::STALE)) *e={};return true;
  }
  bool pin(Handle h) {
    auto* e=entry(h);if(!e || e->state!=State::READY || e->pins==255) return false;
    ++e->pins;e->age=age();return true;
  }
 private:
  alignas(8) uint8_t bytes_[PAYLOAD_CAPACITY];
  Entry entries_[Slots]={}; Statistics statistics_={};
  uint32_t revision_=0,clock_=0,generation_=0,reserved_=0;
  static unsigned allocated(unsigned size) {return (size+7U)&~7U;}
  static bool same(Key a,Key b) {return a.id==b.id && a.language==b.language && a.revision==b.revision && !a.reserved && !b.reserved;}
  Entry* entry(Handle h) {return h && entries_[h.slot].generation==h.generation && entries_[h.slot].state!=State::EMPTY ? &entries_[h.slot] : nullptr;}
  const Entry* entry(Handle h) const {return h && entries_[h.slot].generation==h.generation && entries_[h.slot].state!=State::EMPTY ? &entries_[h.slot] : nullptr;}
  uint32_t age() {
    if(clock_==UINT32_MAX) {for(auto& e:entries_) e.age>>=1;clock_>>=1;}
    return ++clock_;
  }
  Handle failed() {++statistics_.reservation_failures;return {};}
  bool pinned() const {for(const auto& e:entries_) if(e.pins) return true;return false;}
  bool hole(unsigned wanted,unsigned& at) const {
    at=0;
    while(at+wanted<=PAYLOAD_CAPACITY) {
      unsigned next=at;
      for(const auto& e:entries_) if(e.state!=State::EMPTY && at<e.offset+allocated(e.size) && e.offset<at+wanted)
        if(e.offset+allocated(e.size)>next) next=e.offset+allocated(e.size);
      if(next==at) return true;at=next;
    }
    return false;
  }
  void compact() {
    unsigned out=0,previous=0;
    for(unsigned n=0;n<Slots;++n) {
      unsigned slot=Slots;
      for(unsigned i=0;i<Slots;++i) if(entries_[i].state!=State::EMPTY && entries_[i].offset>=previous &&
          (slot==Slots || entries_[i].offset<entries_[slot].offset)) slot=i;
      if(slot==Slots) break;
      auto& e=entries_[slot];previous=e.offset+allocated(e.size);
      memmove(bytes_+out,bytes_+e.offset,e.size);e.offset=(uint16_t)out;out+=allocated(e.size);
    }
  }
};
} // namespace language_vm
#endif
