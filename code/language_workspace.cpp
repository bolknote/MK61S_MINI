#include "language_workspace.hpp"
#include "workspace_swap.hpp"

namespace language_workspace {

static shared_memory::Owner unified_owner(Owner owner) {
  const u8 value = (u8) owner;
  return value <= (u8) Owner::TERMINAL_TRANSFER
      ? (shared_memory::Owner) value : shared_memory::Owner::NONE;
}

static Owner legacy_owner(shared_memory::Owner owner) {
  const u8 value = (u8) owner;
  return value <= (u8) shared_memory::Owner::TERMINAL_TRANSFER
      ? (Owner) value : Owner::NONE;
}

Lease::Lease(Owner next_owner, usize required) : Lease() {
  (void) acquire(next_owner, required);
}

bool Lease::acquire(Owner next_owner, usize required_size) {
  const shared_memory::Owner owner = unified_owner(next_owner);
  return workspace_swap::acquire(
      owner, required_size, workspace_swap::AcquireMode::REQUIRED, lease);
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
