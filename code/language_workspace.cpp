#include "language_workspace.hpp"
#include "workspace_swap.hpp"

namespace language_workspace {

static shared_memory::Owner unified_owner(Owner owner) {
  switch(owner) {
    case Owner::NONE: return shared_memory::Owner::NONE;
    case Owner::FOCAL: return shared_memory::Owner::FOCAL;
    case Owner::TINYBASIC: return shared_memory::Owner::TINYBASIC;
    case Owner::IMAGE_VIEWER: return shared_memory::Owner::IMAGE_VIEWER;
    case Owner::MARKDOWN_VIEWER: return shared_memory::Owner::MARKDOWN_VIEWER;
    case Owner::CHIP8: return shared_memory::Owner::CHIP8;
    case Owner::USB_DISK: return shared_memory::Owner::USB_DISK;
    case Owner::TERMINAL_TRANSFER:
      return shared_memory::Owner::TERMINAL_TRANSFER;
  }
  return shared_memory::Owner::NONE;
}

static Owner legacy_owner(shared_memory::Owner owner) {
  switch(owner) {
    case shared_memory::Owner::FOCAL: return Owner::FOCAL;
    case shared_memory::Owner::TINYBASIC: return Owner::TINYBASIC;
    case shared_memory::Owner::IMAGE_VIEWER: return Owner::IMAGE_VIEWER;
    case shared_memory::Owner::MARKDOWN_VIEWER: return Owner::MARKDOWN_VIEWER;
    case shared_memory::Owner::CHIP8: return Owner::CHIP8;
    case shared_memory::Owner::USB_DISK: return Owner::USB_DISK;
    case shared_memory::Owner::TERMINAL_TRANSFER:
      return Owner::TERMINAL_TRANSFER;
    default: return Owner::NONE;
  }
}

Lease::Lease(Owner next_owner, usize required) : Lease() {
  (void) acquire(next_owner, required);
}

bool Lease::acquire(Owner next_owner, usize required_size) {
  const shared_memory::Owner owner = unified_owner(next_owner);
  if(lease.ok()) {
    return lease.acquire(shared_memory::Arena::WORKSPACE,
                         owner, required_size);
  }
  const workspace_swap::RestoreResult restored =
      workspace_swap::restore(owner, required_size, lease);
  if(restored == workspace_swap::RestoreResult::ACQUIRED) return true;
  if(restored == workspace_swap::RestoreResult::BUSY) return false;
  workspace_swap::capture_resident_before(owner);
  return lease.acquire(shared_memory::Arena::WORKSPACE,
                       owner, required_size);
}

Lease::~Lease(void) {
  reset();
}

void Lease::reset(void) {
  lease.reset();
}

Owner resident_owner(void) {
  return legacy_owner(
      shared_memory::resident_owner(shared_memory::Arena::WORKSPACE));
}

Owner active_owner(void) {
  return legacy_owner(
      shared_memory::active_owner(shared_memory::Arena::WORKSPACE));
}

bool discard(Owner owner) {
  return shared_memory::discard_resident(
      shared_memory::Arena::WORKSPACE, unified_owner(owner));
}

void* data(Owner owner) {
  return shared_memory::data(shared_memory::Arena::WORKSPACE,
                             unified_owner(owner));
}

} // пространство имён language_workspace
