#include "exclusive_buffer.hpp"

namespace exclusive_buffer {

#if defined(MK61_DISPLAY_UC1609)
alignas(4) static u8 buffer[SIZE];
static Owner owner = Owner::NONE;

bool acquire(Owner next_owner, usize required) {
  if(next_owner == Owner::NONE || required == 0 || required > SIZE) return false;
  if(owner == next_owner) return true;
  if(owner != Owner::NONE) return false;
  owner = next_owner;
  return true;
}

void release(Owner released_owner) {
  if(released_owner == Owner::NONE) return;
  if(owner != released_owner) __builtin_trap();
  owner = Owner::NONE;
}

u8* data(Owner expected_owner) {
  return expected_owner != Owner::NONE && owner == expected_owner ? buffer : 0;
}

Owner current_owner(void) {
  return owner;
}
#else
bool acquire(Owner, usize) { return false; }
void release(Owner) {}
u8* data(Owner) { return 0; }
Owner current_owner(void) { return Owner::NONE; }
#endif

} // пространство имён exclusive_buffer
