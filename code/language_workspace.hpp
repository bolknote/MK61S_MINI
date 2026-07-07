#ifndef LANGUAGE_WORKSPACE_HPP
#define LANGUAGE_WORKSPACE_HPP

#include "rust_types.h"

namespace language_workspace {

enum class Owner : u8 {
  NONE,
  FOCAL,
  TINYBASIC,
  USB_DISK
};

static constexpr usize SIZE = 8192;

void* acquire(Owner owner, usize required);
Owner current_owner(void);

} // namespace language_workspace

#endif
