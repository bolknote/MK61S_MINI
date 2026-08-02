#include "exclusive_buffer.hpp"

namespace exclusive_buffer {

static shared_memory::Lease lease;

static constexpr shared_memory::Owner unified_owners[] = {
  shared_memory::Owner::NONE,
  shared_memory::Owner::DISPLAY_FONT,
  shared_memory::Owner::USB_CACHE,
  shared_memory::Owner::PROGRAM_STORE_COMPRESSION
};

static_assert(sizeof(unified_owners) / sizeof(unified_owners[0]) ==
              (usize) Owner::PROGRAM_STORE_COMPRESSION + 1,
              "exclusive-buffer owner facade is incomplete");

static shared_memory::Owner unified_owner(Owner owner) {
  const usize index = (usize) owner;
  return index < sizeof(unified_owners) / sizeof(unified_owners[0])
      ? unified_owners[index] : shared_memory::Owner::NONE;
}

static Owner legacy_owner(shared_memory::Owner owner) {
  for(usize index = 1;
      index < sizeof(unified_owners) / sizeof(unified_owners[0]); index++) {
    if(unified_owners[index] == owner) return (Owner) index;
  }
  return Owner::NONE;
}

bool acquire(Owner next_owner, usize required) {
  return lease.acquire(shared_memory::Arena::BULK,
                       unified_owner(next_owner), required);
}

void release(Owner released_owner) {
  if(released_owner == Owner::NONE) return;
  if(current_owner() != released_owner) __builtin_trap();
  lease.reset();
}

u8* data(Owner expected_owner) {
  return (u8*) shared_memory::data(shared_memory::Arena::BULK,
                                   unified_owner(expected_owner));
}

Owner current_owner(void) {
  return legacy_owner(
      shared_memory::active_owner(shared_memory::Arena::BULK));
}

} // пространство имён exclusive_buffer
