#include "language_workspace.hpp"

#include "config.h"

#include <string.h>

namespace language_workspace {

#if MK61_ENABLE_FOCAL || MK61_ENABLE_TINYBASIC
alignas(8) static u8 workspace[SIZE];
#else
alignas(8) static u8 workspace[1];
#endif
static Owner owner = Owner::NONE;

void* acquire(Owner next_owner, usize required) {
  if(required > sizeof(workspace)) return NULL;
  if(owner != next_owner) {
    memset(workspace, 0, sizeof(workspace));
    owner = next_owner;
  }
  return workspace;
}

Owner current_owner(void) {
  return owner;
}

} // namespace language_workspace
