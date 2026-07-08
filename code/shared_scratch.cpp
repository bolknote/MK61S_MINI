#include "shared_scratch.hpp"

namespace shared_scratch {

alignas(8) static u8 scratch[SIZE];
static Owner active_owner = Owner::NONE;

Lease::Lease(Owner next_owner, usize required) : owner(next_owner), buffer(0) {
  buffer = acquire(next_owner, required);
}

Lease::~Lease(void) {
  if(buffer != 0) release(owner);
}

u8* acquire(Owner owner, usize required) {
  if(owner == Owner::NONE || required > SIZE || active_owner != Owner::NONE) return 0;
  active_owner = owner;
  return scratch;
}

void release(Owner owner) {
  if(owner != Owner::NONE && active_owner == owner) active_owner = Owner::NONE;
}

u8* data(Owner owner) {
  if(owner == Owner::NONE || active_owner != owner) return 0;
  return scratch;
}

Owner current_owner(void) {
  return active_owner;
}

} // namespace shared_scratch
