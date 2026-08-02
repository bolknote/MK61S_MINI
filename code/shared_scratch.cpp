#include "shared_scratch.hpp"

namespace shared_scratch {

static shared_memory::Owner unified_owner(Owner owner) {
  switch(owner) {
    case Owner::NONE: return shared_memory::Owner::NONE;
    case Owner::EXPLORER_VIEW: return shared_memory::Owner::EXPLORER_VIEW;
    case Owner::IMAGE_VIEWER: return shared_memory::Owner::IMAGE_VIEWER;
    case Owner::MARKDOWN_VIEWER: return shared_memory::Owner::MARKDOWN_VIEWER;
    case Owner::M61_FORMAT: return shared_memory::Owner::M61_FORMAT;
    case Owner::PROGRAM_STORE_RENAME:
      return shared_memory::Owner::PROGRAM_STORE_RENAME;
    case Owner::PROGRAM_STORE_READ_RANGE:
      return shared_memory::Owner::PROGRAM_STORE_READ_RANGE;
    case Owner::PROGRAM_STORE_COMPRESSION:
      return shared_memory::Owner::PROGRAM_STORE_COMPRESSION;
    case Owner::VFAT_COMMIT: return shared_memory::Owner::VFAT_COMMIT;
    case Owner::USB_CACHE: return shared_memory::Owner::USB_CACHE;
    case Owner::TERMINAL_TRANSFER:
      return shared_memory::Owner::TERMINAL_TRANSFER;
  }
  return shared_memory::Owner::NONE;
}

static Owner legacy_owner(shared_memory::Owner owner) {
  switch(owner) {
    case shared_memory::Owner::EXPLORER_VIEW: return Owner::EXPLORER_VIEW;
    case shared_memory::Owner::IMAGE_VIEWER: return Owner::IMAGE_VIEWER;
    case shared_memory::Owner::MARKDOWN_VIEWER: return Owner::MARKDOWN_VIEWER;
    case shared_memory::Owner::M61_FORMAT: return Owner::M61_FORMAT;
    case shared_memory::Owner::PROGRAM_STORE_RENAME:
      return Owner::PROGRAM_STORE_RENAME;
    case shared_memory::Owner::PROGRAM_STORE_READ_RANGE:
      return Owner::PROGRAM_STORE_READ_RANGE;
    case shared_memory::Owner::PROGRAM_STORE_COMPRESSION:
      return Owner::PROGRAM_STORE_COMPRESSION;
    case shared_memory::Owner::VFAT_COMMIT: return Owner::VFAT_COMMIT;
    case shared_memory::Owner::USB_CACHE: return Owner::USB_CACHE;
    case shared_memory::Owner::TERMINAL_TRANSFER:
      return Owner::TERMINAL_TRANSFER;
    default: return Owner::NONE;
  }
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
