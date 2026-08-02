#include "exclusive_buffer.hpp"

namespace exclusive_buffer {

static shared_memory::Lease lease;

static shared_memory::Owner unified_owner(Owner owner) {
  switch(owner) {
    case Owner::NONE: return shared_memory::Owner::NONE;
    case Owner::DISPLAY_FONT: return shared_memory::Owner::DISPLAY_FONT;
    case Owner::USB_CACHE: return shared_memory::Owner::USB_CACHE;
    case Owner::PROGRAM_STORE_COMPRESSION:
      return shared_memory::Owner::PROGRAM_STORE_COMPRESSION;
  }
  return shared_memory::Owner::NONE;
}

static Owner legacy_owner(shared_memory::Owner owner) {
  switch(owner) {
    case shared_memory::Owner::DISPLAY_FONT: return Owner::DISPLAY_FONT;
    case shared_memory::Owner::USB_CACHE: return Owner::USB_CACHE;
    case shared_memory::Owner::PROGRAM_STORE_COMPRESSION:
      return Owner::PROGRAM_STORE_COMPRESSION;
    default: return Owner::NONE;
  }
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
