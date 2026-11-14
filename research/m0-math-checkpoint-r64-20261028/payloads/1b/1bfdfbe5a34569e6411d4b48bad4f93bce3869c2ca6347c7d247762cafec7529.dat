#ifndef MK61_PAGE_DAMAGE_HPP
#define MK61_PAGE_DAMAGE_HPP

#include "rust_types.h"

namespace page_damage {

inline void clear(u16* masks, u8 page_count) {
  if(masks == nullptr) return;
  for(u8 page = 0; page < page_count; page++) masks[page] = 0;
}

inline void markAll(u16* masks, u8 page_count, u16 columns = 0xFFFFU) {
  if(masks == nullptr || columns == 0) return;
  for(u8 page = 0; page < page_count; page++) masks[page] |= columns;
}

inline void markSpan(u16* masks, u8 page_count, u8 page_height,
                     u16 top, u16 height, u16 columns) {
  if(masks == nullptr || page_count == 0 || page_height == 0 ||
     height == 0 || columns == 0) return;

  const u16 first_page = top / page_height;
  if(first_page >= page_count) return;

  const u32 bottom = (u32) top + height;
  u32 last_page = (bottom - 1U) / page_height;
  if(last_page >= page_count) last_page = page_count - 1U;
  for(u16 page = first_page; page <= last_page; page++) {
    masks[page] |= columns;
  }
}

inline bool any(const u16* masks, u8 page_count) {
  if(masks == nullptr) return false;
  for(u8 page = 0; page < page_count; page++) {
    if(masks[page] != 0) return true;
  }
  return false;
}

} // пространство имён page_damage

#endif
