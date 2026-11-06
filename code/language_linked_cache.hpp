#ifndef MK61_LANGUAGE_LINKED_CACHE_HPP
#define MK61_LANGUAGE_LINKED_CACHE_HPP
#include "language_flash_cache.hpp"
#include "language_linked_program.hpp"

namespace language_vm { namespace linked {
// The first fragment inode identifies the actual container for this media
// epoch; source_id is only a local debug label. Reserve eight keys per byte
// offset for loans of at most eight 1-KiB pages. The high bit keeps these keys
// disjoint from ordinary fragment pages, even for an unaligned member.
inline bool borrow_image(flash::ReadCache& cache,uint32_t revision,uint16_t first_fragment,
                         const Member& member,const flash::IO& io,const uint8_t*& image) {
  image=nullptr;
  if(member.offset>=0x10000000U)return false;
  return cache.borrow(revision,first_fragment,member.validated.size,io,image,false,
                      0x80000000U|(member.offset<<3));
}
}}
#endif
