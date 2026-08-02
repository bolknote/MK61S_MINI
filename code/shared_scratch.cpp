#include "shared_scratch.hpp"

namespace shared_scratch {

static constexpr shared_memory::Owner unified_owners[] = {
  shared_memory::Owner::NONE,
  shared_memory::Owner::EXPLORER_VIEW,
  shared_memory::Owner::IMAGE_VIEWER,
  shared_memory::Owner::MARKDOWN_VIEWER,
  shared_memory::Owner::M61_FORMAT,
  shared_memory::Owner::PROGRAM_STORE_RENAME,
  shared_memory::Owner::PROGRAM_STORE_READ_RANGE,
  shared_memory::Owner::PROGRAM_STORE_COMPRESSION,
  shared_memory::Owner::VFAT_COMMIT,
  shared_memory::Owner::USB_CACHE,
  shared_memory::Owner::TERMINAL_TRANSFER
};

static_assert(sizeof(unified_owners) / sizeof(unified_owners[0]) ==
              (usize) Owner::TERMINAL_TRANSFER + 1,
              "shared-scratch owner facade is incomplete");

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

Lease::Lease(Owner next_owner, usize required) : Lease() {
  (void) acquire(next_owner, required);
}

bool Lease::acquire(Owner next_owner, usize required_size) {
  return lease.acquire(shared_memory::Arena::SCRATCH,
                       unified_owner(next_owner), required_size);
}

Lease::~Lease(void) {
  reset();
}

void Lease::reset(void) {
  lease.reset();
}

Owner current_owner(void) {
  return legacy_owner(
      shared_memory::active_owner(shared_memory::Arena::SCRATCH));
}

} // пространство имён shared_scratch
