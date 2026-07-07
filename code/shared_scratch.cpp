#include "shared_scratch.hpp"

namespace shared_scratch {

alignas(8) static u8 scratch[SIZE];
static Owner active_owner = Owner::NONE;

Lease::Lease(Owner next_owner, usize required) : owner(next_owner), buffer(0) {
  if(next_owner == Owner::NONE || required > SIZE || active_owner != Owner::NONE) return;
  active_owner = next_owner;
  buffer = scratch;
}

Lease::~Lease(void) {
  if(buffer != 0 && active_owner == owner) active_owner = Owner::NONE;
}

Owner current_owner(void) {
  return active_owner;
}

} // namespace shared_scratch
