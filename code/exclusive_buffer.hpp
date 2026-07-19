#ifndef EXCLUSIVE_BUFFER_HPP
#define EXCLUSIVE_BUFFER_HPP

#include "rust_types.h"

namespace exclusive_buffer {

enum class Owner : u8 {
  NONE,
  DISPLAY_FONT,
  USB_CACHE
};

// Persistent external-font storage while the UI is running; all of it becomes
// 16 additional 512-byte write-back slots while USB mass-storage owns the UI.
static constexpr usize SIZE = 8192;

bool acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // namespace exclusive_buffer

#endif
