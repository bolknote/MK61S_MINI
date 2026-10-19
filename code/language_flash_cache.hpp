#ifndef MK61_LANGUAGE_FLASH_CACHE_HPP
#define MK61_LANGUAGE_FLASH_CACHE_HPP
#include "language_vm_abi.hpp"
namespace language_vm { namespace flash {
// Fixed page frames, shared across RUN/APP replacement. Identity includes the
// complete C9 mutation epoch: inode reuse, GC, edits and derived-cache eviction
// invalidate every old key. Small images may borrow adjacent frames for one
// RUN; a live loan survives key invalidation and cannot be overwritten.
class ReadCache {
public:
  struct Slot {uint32_t chunk,age;uint16_t directory;};
  struct Statistics {
    uint32_t lookups=0,hits=0,misses=0,publications=0,evictions=0,invalidations=0;
    uint32_t loan_hits=0,loan_misses=0;
  };
  struct Image {
    uint32_t fingerprint,stamp,age;
    uint16_t source,parent,root,directory;
    uint8_t bank;
    ValidatedImage validated;
  };
private:
  Slot* slots_;uint8_t* bytes_;uint16_t count_;
  uint16_t pinned_start_=0,pinned_count_=0;
  uint32_t revision_=0,clock_=0;
  Image images_[32];
  uint32_t fingerprints_[2];
  uint8_t fingerprint_mask_=0;
  Statistics statistics_;
  void synchronize(uint32_t revision) {
    if(revision_==revision && clock_!=UINT32_MAX)return;
    revision_=revision;clock_=0;++statistics_.invalidations;
    clear();
  }
protected:
  ReadCache(Slot* slots,uint8_t* bytes,uint16_t count)
      :slots_(slots),bytes_(bytes),count_(count) {}
  void clear() {
    for(unsigned i=0;i<count_;++i)slots_[i].directory=UINT16_MAX;
    for(auto& image:images_)image.source=UINT16_MAX;
    fingerprint_mask_=0;
  }
public:
  const Statistics& statistics() const {return statistics_;}
  uint32_t payload() const {return uint32_t(count_)*WRITE_BYTES;}
  uint32_t used() const {
    uint32_t result=0;for(unsigned i=0;i<count_;++i)
      if(slots_[i].directory!=UINT16_MAX || (i>=pinned_start_ && i-pinned_start_<pinned_count_))result+=WRITE_BYTES;
    return result;
  }
  bool fingerprint(uint32_t revision,Language language,uint32_t& value) {
    synchronize(revision);const unsigned i=unsigned(language)-1;
    if(i>=2 || !(fingerprint_mask_&(1U<<i)))return false;
    value=fingerprints_[i];return true;
  }
  void remember_fingerprint(uint32_t revision,Language language,uint32_t value) {
    synchronize(revision);const unsigned i=unsigned(language)-1;
    if(i<2){fingerprints_[i]=value;fingerprint_mask_|=uint8_t(1U<<i);}
  }
  bool image(uint32_t revision,uint16_t source,uint32_t fingerprint,Image& out) {
    synchronize(revision);if(source==UINT16_MAX)return false;
    for(auto& image:images_)if(image.source==source && image.fingerprint==fingerprint) {
      image.age=++clock_;out=image;return true;
    }
    return false;
  }
  void remember_image(uint32_t revision,Image image) {
    synchronize(revision);if(image.source==UINT16_MAX)return;
    unsigned selected=0;
    for(unsigned i=0;i<32;++i) {
      if(images_[i].source==image.source || images_[i].source==UINT16_MAX){selected=i;break;}
      if(images_[i].age<images_[selected].age)selected=i;
    }
    image.age=++clock_;images_[selected]=image;
  }
  bool get(uint32_t revision,uint16_t directory,uint32_t chunk,uint8_t* out) {
    synchronize(revision);++statistics_.lookups;
    if(directory==UINT16_MAX){++statistics_.misses;return false;}
    for(unsigned i=0;i<count_;++i)if(slots_[i].directory==directory && slots_[i].chunk==chunk) {
      slots_[i].age=++clock_;++statistics_.hits;
      memcpy(out,bytes_+i*WRITE_BYTES,WRITE_BYTES);return true;
    }
    ++statistics_.misses;return false;
  }
  void put(uint32_t revision,uint16_t directory,uint32_t chunk,const uint8_t* bytes) {
    synchronize(revision);if(directory==UINT16_MAX)return;
    unsigned selected=count_;
    for(unsigned i=0;i<count_;++i) {
      if(i>=pinned_start_ && i-pinned_start_<pinned_count_)continue;
      if(slots_[i].directory==directory && slots_[i].chunk==chunk){selected=i;break;}
      if(slots_[i].directory==UINT16_MAX){selected=i;break;}
      if(selected==count_ || slots_[i].age<slots_[selected].age)selected=i;
    }
    if(selected==count_)return;
    if(slots_[selected].directory!=UINT16_MAX)++statistics_.evictions;
    ++statistics_.publications;
    memcpy(bytes_+selected*WRITE_BYTES,bytes,WRITE_BYTES);
    slots_[selected]={chunk,++clock_,directory};
  }
  // Optional whole-image fast lane, backed by the very same page frames.
  // True with a null result means ineligible/busy: use the paged VM. False
  // is a backing I/O/service failure, not a reason to silently retry it.
  bool borrow(uint32_t revision,uint16_t directory,uint32_t size,const IO& io,const uint8_t*& image) {
    image=nullptr;synchronize(revision);
    const unsigned n=(size+WRITE_BYTES-1)/WRITE_BYTES;
    if(!size || size>8192 || n>count_ || directory==UINT16_MAX || pinned_count_)return true;
    unsigned selected=0;uint32_t oldest=UINT32_MAX;
    for(unsigned i=0;i+n<=count_;++i) {
      bool ready=true;uint32_t newest=0;
      for(unsigned j=0;j<n;++j) {
        const auto& slot=slots_[i+j];
        if(slot.directory!=directory || slot.chunk!=j)ready=false;
        if(slot.directory!=UINT16_MAX && slot.age>newest)newest=slot.age;
      }
      if(ready) {
        ++statistics_.loan_hits;
        const uint32_t age=++clock_;
        for(unsigned j=0;j<n;++j)slots_[i+j].age=age;
        pinned_start_=uint16_t(i);pinned_count_=uint16_t(n);
        image=bytes_+i*WRITE_BYTES;return true;
      }
      if(newest<oldest){oldest=newest;selected=i;}
    }
    ++statistics_.loan_misses;
    pinned_start_=uint16_t(selected);pinned_count_=uint16_t(n);
    for(unsigned j=0;j<n;++j) {
      if(slots_[selected+j].directory!=UINT16_MAX)++statistics_.evictions;
      slots_[selected+j].directory=UINT16_MAX;
    }
    // Include physical tail padding: get() promises a complete 1-KiB page.
    // Reads may populate other frames, but never the reserved destination.
    auto* destination=bytes_+selected*WRITE_BYTES;
    for(unsigned j=0;j<n;++j)if(!io.read ||
        !io.read(io.context,IMAGE,j*WRITE_BYTES,destination+j*WRITE_BYTES,WRITE_BYTES) ||
        (io.service && !io.service(io.context))) {
      pinned_count_=0;return false;
    }
    if(revision_!=revision){pinned_count_=0;return false;}
    synchronize(revision);const uint32_t age=++clock_;
    for(unsigned i=0;i<count_;++i)
      if((i<selected || i>=selected+n) && slots_[i].directory==directory && slots_[i].chunk<n)
        slots_[i].directory=UINT16_MAX;
    for(unsigned j=0;j<n;++j) {
      slots_[selected+j]={j,age,directory};++statistics_.publications;
    }
    image=destination;return true;
  }
  void release(const uint8_t* image) {
    if(pinned_count_ && image==bytes_+pinned_start_*WRITE_BYTES)pinned_count_=0;
  }
};
template<unsigned Capacity> class PageCache final:public ReadCache {
  static constexpr unsigned N=(Capacity-sizeof(ReadCache))/(WRITE_BYTES+sizeof(Slot));
  static_assert(Capacity>sizeof(ReadCache) && N && N<=UINT16_MAX,"page-cache budget");
  Slot slots_[N];uint8_t bytes_[N][WRITE_BYTES];
public:
  PageCache():ReadCache(slots_,bytes_[0],N) {clear();}
  static constexpr unsigned pages=N;
};
}}
#endif
