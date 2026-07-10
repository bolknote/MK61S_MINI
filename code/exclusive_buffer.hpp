#ifndef EXCLUSIVE_BUFFER_HPP
#define EXCLUSIVE_BUFFER_HPP

#include "rust_types.h"

namespace exclusive_buffer {

enum class Owner : u8 {
  NONE,
  DISPLAY_FONT,
  USB_WRITE
};

// STM32duino configures MSC_MEDIA_PACKET as 8192 bytes. The same storage is
// reused for a persistent external font while USB mass-storage mode is idle.
static constexpr usize SIZE = 8192;

bool acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // namespace exclusive_buffer

#endif
