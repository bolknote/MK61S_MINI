#ifndef MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#define MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#include "language_vm_abi.hpp"
#include "language_vm_cache_codec.hpp"
#include "crc32.hpp"
#include "dwt_profiler.hpp"
#include <new>
#include <string.h>
namespace language_vm {
enum class CachePolicy : uint8_t { LRU, REUSE_DENSITY };
// Capacity includes the bounded directory and counters. No heap allocation;
// only pinned, generation-checked handles expose immutable program bytes.
template<unsigned Capacity, unsigned Slots=16, CachePolicy Policy=CachePolicy::LRU, bool Mixed=false>
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
  // Synchronous, borrowed storage only. Never retained in a cache entry.
  struct Scratch {
    uint8_t* data; unsigned size;
    constexpr Scratch(uint8_t* p=nullptr,unsigned n=0) : data(p),size(n) {}
  };
  struct PackingStatistics { uint16_t packs,thaws; unsigned packed; };
 private:
  enum class State:uint8_t { EMPTY, BUILDING, READY, STALE, PACKED };
  struct Entry {
    Key key={}; ValidatedImage validated={}; uint32_t age=0,generation=0;
    uint16_t offset=0,size=0; uint8_t pins=0; State state=State::EMPTY;
    uint16_t reuse=0; // Uses the existing reserved word; no additional metadata.
  };
  static constexpr unsigned Metadata=sizeof(Entry)*Slots+sizeof(Statistics)+16;
 public:
  static_assert(Capacity>=Metadata+32,"cache budget must include metadata and a small image");
  static_assert(Policy == CachePolicy::LRU || Policy == CachePolicy::REUSE_DENSITY, "unknown cache policy");
  static_assert(!Mixed || Slots<=32,"mixed packing uses a bounded candidate mask");
  static constexpr unsigned PAYLOAD_CAPACITY=(Capacity-Metadata)&~7U;
  static constexpr unsigned metadata_bytes() {return Metadata;}
  const Statistics& statistics() const {return statistics_;}
  PackingStatistics packing_statistics() const {
    unsigned packed=0;
    if constexpr(Mixed) for(const auto& e:entries_) packed+=e.state==State::PACKED;
    return {(uint16_t)reserved_,(uint16_t)(reserved_>>16),packed};
  }
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
  Handle find(Key key,Scratch scratch={}) {
    ++statistics_.lookups;synchronize(key.revision);
    for(unsigned i=0;i<Slots;++i) {
      auto& e=entries_[i];
      if constexpr(Mixed) {
        if(e.state==State::PACKED && same(e.key,key) && !e.pins) {
          if(!thaw(e,checked(scratch))) break;
        }
      }
      if(e.state==State::READY && same(e.key,key) && e.pins!=255) {
        if constexpr(Policy == CachePolicy::REUSE_DENSITY) if(e.reuse < 255) ++e.reuse;
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
      if constexpr(Mixed) if(slot<Slots && pack_one(nullptr,{})) continue;
      unsigned oldest=Slots;
      for(unsigned i=0;i<Slots;++i) {
        const auto& e=entries_[i];
        if(e.state!=State::EMPTY && !e.pins && (oldest==Slots || colder(e, entries_[oldest]))) oldest=i;
      }
      if(oldest==Slots) return failed();
      if constexpr(Policy == CachePolicy::REUSE_DENSITY)
        for(auto& e : entries_) e.reuse >>= 1; // Adapt to a new working set, not unbounded LFU.
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
  alignas(8) uint8_t bytes_[PAYLOAD_CAPACITY]={};
  Entry entries_[Slots]={}; Statistics statistics_={};
  uint32_t revision_=0,clock_=0,generation_=0,reserved_=0;
  friend struct ImageCacheTestAccess;
  static unsigned allocated(unsigned size) {return (size+7U)&~7U;}
  static bool colder(const Entry& a, const Entry& b) {
    if constexpr(Policy == CachePolicy::REUSE_DENSITY) {
      const uint32_t left = (uint32_t)a.reuse * logical_size(b);
      const uint32_t right = (uint32_t)b.reuse * logical_size(a);
      if(left != right) return left < right;
    }
    return a.age < b.age;
  }
  static bool same(Key a,Key b) {return a.id==b.id && a.language==b.language && a.revision==b.revision && !a.reserved && !b.reserved;}
  static unsigned logical_size(const Entry& e) {
    if constexpr(Mixed) if(e.state==State::PACKED) return allocated(e.validated.size);
    return allocated(e.size);
  }
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
      for(const auto& e:entries_) if(e.state!=State::EMPTY && (!Mixed || e.size) && at<e.offset+allocated(e.size) && e.offset<at+wanted)
        if(e.offset+allocated(e.size)>next) next=e.offset+allocated(e.size);
      if(next==at) return true;
      at=next;
    }
    return false;
  }
  void compact() {
    unsigned out=0,previous=0;
    for(unsigned n=0;n<Slots;++n) {
      unsigned slot=Slots;
      for(unsigned i=0;i<Slots;++i) if(entries_[i].state!=State::EMPTY && (!Mixed || entries_[i].size) && entries_[i].offset>=previous &&
          (slot==Slots || entries_[i].offset<entries_[slot].offset)) slot=i;
      if(slot==Slots) break;
      auto& e=entries_[slot];previous=e.offset+allocated(e.size);
      memmove(bytes_+out,bytes_+e.offset,e.size);e.offset=(uint16_t)out;out+=allocated(e.size);
    }
  }
  static Scratch checked(Scratch s) {
    // The caller owns phase/lifetime; the cache separately rejects overlap
    // with its entire object (including directory), and unaligned loans.
    if(!s.data || (reinterpret_cast<uintptr_t>(s.data)&7U)) return {};
    s.size&=~7U;return s;
  }
  Scratch external(Scratch s) const {
    return s.data && !vm_cache_lzss::overlap(s.data,s.size,
        reinterpret_cast<const uint8_t*>(this),sizeof(*this)) ? s : Scratch{};
  }
  unsigned largest_hole(unsigned& offset,unsigned block=0,unsigned block_size=0) const {
    unsigned cursor=0,best=0;offset=0;
    for(unsigned n=0;n<=Slots+1;++n) {
      unsigned next=PAYLOAD_CAPACITY,end=PAYLOAD_CAPACITY;
      for(const auto& e:entries_) if(e.state!=State::EMPTY && e.size &&
          e.offset>=cursor && e.offset<next) {next=e.offset;end=next+allocated(e.size);}
      if(block_size && block>=cursor && block<next) {next=block;end=next+block_size;}
      if(next-cursor>best) {best=next-cursor;offset=cursor;}
      if(next==PAYLOAD_CAPACITY) break;
      cursor=end;
    }
    return best;
  }
  void age_reuse() {
    if constexpr(Policy==CachePolicy::REUSE_DENSITY) for(auto& e:entries_) e.reuse>>=1;
  }
  bool pack(Entry& e,Scratch scratch) {
    if(e.state!=State::READY || e.pins || allocated(e.size)<=8) return false;
    // No source pointer escapes this call. Compact before codec temporaries
    // are live, and never while another image has a pinned address.
    if(!pinned()) compact();
    scratch=external(scratch);
    unsigned dictionary_at=0,dictionary_size=0;
    uint8_t* dictionary=scratch.data;
    if(scratch.size>=sizeof(vm_cache_lzss::Workspace)) {
      scratch.data+=sizeof(vm_cache_lzss::Workspace);
      scratch.size-=sizeof(vm_cache_lzss::Workspace);
    } else {
      dictionary_size=sizeof(vm_cache_lzss::Workspace);
      if(!hole(dictionary_size,dictionary_at)) return false;
      dictionary=bytes_+dictionary_at;
    }
    unsigned at=0;
    const unsigned hole_size=largest_hole(at,dictionary_at,dictionary_size);
    const unsigned maximum=allocated(e.size)-8;
    const bool staged=(scratch.size>=hole_size || scratch.size>=maximum);
    const unsigned capacity=(staged?scratch.size:hole_size)<maximum ?
        (staged?scratch.size:hole_size) : maximum;
    // Even maximal 18-byte matches require two token bytes. This lower
    // bound avoids encoding into a gap that cannot possibly save an image.
    if(capacity<((e.size+17U)/18U)*2U) return false;
    auto* output=staged?scratch.data:bytes_+at;
    MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_CACHE_PACK);
    size_t written=0;
    auto* work=new(dictionary) vm_cache_lzss::Workspace;
    if(!vm_cache_lzss::encode(bytes_+e.offset,e.size,*work,output,capacity,written)) return false;
    const uint32_t checksum=mk61_crc32::calculate(bytes_+e.offset,e.size);
    if(staged) memcpy(bytes_+e.offset,output,written);
    else e.offset=(uint16_t)at;
    e.size=(uint16_t)written;e.state=State::PACKED;
    // Magic is constant only for raw READY certificates. While PACKED its
    // otherwise redundant word stores the full decoded-image CRC, without
    // growing the directory. No certificate is exposed until CRC passes.
    e.validated.magic=checksum;
    if((reserved_&0xFFFFU)!=0xFFFFU) ++reserved_;
    age_reuse();return true;
  }
  bool pack_one(const Entry* protected_entry,Scratch scratch) {
    uint32_t tried=0;
    for(unsigned n=0;n<Slots;++n) {
      unsigned candidate=Slots;
      for(unsigned i=0;i<Slots;++i) {
        const auto& e=entries_[i];
        if(!(tried&(uint32_t(1)<<i)) && &e!=protected_entry &&
            e.state==State::READY && !e.pins && (candidate==Slots || colder(e,entries_[candidate]))) candidate=i;
      }
      if(candidate==Slots) return false;
      tried|=uint32_t(1)<<candidate;
      if(pack(entries_[candidate],scratch)) return true;
    }
    return false;
  }
  bool make_room(unsigned wanted,unsigned& at,Entry* protected_entry,Scratch scratch) {
    for(;;) {
      if(hole(wanted,at)) return true;
      if(!pinned()) compact();
      if(hole(wanted,at)) return true;
      if(pack_one(protected_entry,scratch)) continue;
      unsigned victim=Slots;
      for(unsigned i=0;i<Slots;++i) {
        const auto& e=entries_[i];
        if(e.state!=State::EMPTY && &e!=protected_entry && !e.pins &&
            (victim==Slots || colder(e,entries_[victim]))) victim=i;
      }
      if(victim==Slots) return false;
      entries_[victim]={};++statistics_.evictions;age_reuse();
    }
  }
  bool thaw(Entry& e,Scratch scratch) {
    MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_CACHE_THAW);
    scratch=external(scratch);
    const unsigned raw=e.validated.size;
    if(raw<HEADER_SIZE || allocated(raw)>PAYLOAD_CAPACITY || !e.size) {e={};return false;}
    const uint8_t* source=bytes_+e.offset;
    const unsigned stored=e.size;
    if(allocated(stored)<=scratch.size) {
      memcpy(scratch.data,source,stored);source=scratch.data;
      scratch.data+=allocated(stored);scratch.size-=allocated(stored);
      e.size=0; // Source is now protected in the borrowed prefix, not lost.
    } else e.pins=1; // Pinned compressed source forbids compaction over it.
    unsigned at=0;
    if(!make_room(allocated(raw),at,&e,scratch) ||
       !vm_cache_lzss::decode(source,stored,bytes_+at,raw,raw) ||
       mk61_crc32::calculate(bytes_+at,raw)!=e.validated.magic) {
      e={};return false; // Reload ordinary source/file cache, never run bad bytes.
    }
    e.offset=(uint16_t)at;e.size=(uint16_t)raw;e.pins=0;e.state=State::READY;
    e.validated.magic=VALIDATED_MAGIC;
    if((reserved_>>16)!=0xFFFFU) reserved_+=0x10000U;
    return true;
  }
};
} // namespace language_vm
#endif
