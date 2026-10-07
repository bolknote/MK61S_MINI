#ifndef MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#define MK61_LANGUAGE_VM_IMAGE_CACHE_HPP
#include "language_vm_abi.hpp"
#include <string.h>

namespace language_vm {
// Immutable bytecode only. Values, RNG, control frames and INPUT stay outside.
// Callers serialize access: images cannot move while the VM uses a returned entry.
template<unsigned Capacity, unsigned Slots = 12>
class ImageCache {
 public:
  struct Entry {
    uint32_t age;
    uint16_t id, offset, allocated;
    ValidatedImage validated;
  };
  const Entry* find(uint16_t id, uint32_t revision) {
    synchronize(revision);
    for(auto& entry : entries_) {
      if(entry.allocated && entry.id == id) {
        entry.age = ++clock_;
        return &entry;
      }
    }
    return nullptr;
  }
  const uint8_t* image(const Entry& entry) const { return bytes_ + entry.offset; }
  bool store(uint16_t id, uint32_t revision, const uint8_t* image,
             const ValidatedImage& validated) {
    synchronize(revision);
    const unsigned needed = (validated.size + 7U) & ~7U;
    if(!image || validated.magic != VALIDATED_MAGIC ||
       validated.language != Language::BASIC || (validated.flags & 1) ||
       !validated.size || needed > Capacity) return false;
    for(unsigned i=0;i<Slots;++i)
      if(entries_[i].allocated && entries_[i].id==id) remove(i);
    unsigned slot;
    for(;;) {
      slot=Slots;
      for(unsigned i=0;i<Slots;++i)
        if(!entries_[i].allocated) { slot=i; break; }
      if(slot!=Slots && used_+needed<=Capacity) break;
      unsigned oldest=Slots;
      for(unsigned i=0;i<Slots;++i)
        if(entries_[i].allocated && (oldest==Slots || entries_[i].age<entries_[oldest].age)) oldest=i;
      if(oldest==Slots) return false;
      remove(oldest);
    }
    memcpy(bytes_+used_,image,validated.size);
    entries_[slot]={++clock_,id,(uint16_t)used_,(uint16_t)needed,validated};
    used_+=needed;
    return true;
  }
  unsigned used() const { return used_; }
 private:
  alignas(8) uint8_t bytes_[Capacity];
  Entry entries_[Slots] = {};
  uint32_t revision_=0,clock_=0;
  unsigned used_=0;
  void synchronize(uint32_t revision) {
    if(revision_!=revision || clock_==0xFFFFFFFFUL) {
      memset(entries_,0,sizeof(entries_));used_=0;clock_=0;revision_=revision;
    }
  }
  void remove(unsigned index) {
    const unsigned offset=entries_[index].offset,size=entries_[index].allocated;
    memmove(bytes_+offset,bytes_+offset+size,used_-offset-size);
    used_-=size;
    entries_[index]={};
    for(auto& entry:entries_)
      if(entry.allocated && entry.offset>offset) entry.offset-=size;
  }
};
} // namespace language_vm
#endif
