#include "language_workspace.hpp"

#include <string.h>

namespace language_workspace {

// Виртуальная FAT также использует этот буфер, в том числе в сборках, где оба языка
// отключены. Физическая ёмкость должна совпадать с объявленной.
alignas(8) static u8 workspace[SIZE];
static Owner resident = Owner::NONE;
static Owner active = Owner::NONE;
static u16 active_depth = 0;

Lease::Lease(void)
  : owner(Owner::NONE), memory(NULL), requested(0), was_fresh(false) {}

Lease::Lease(Owner next_owner, usize required) : Lease() {
  (void) acquire(next_owner, required);
}

bool Lease::acquire(Owner next_owner, usize required_size) {
  if(memory != NULL) return owner == next_owner && required_size <= requested;
  owner = next_owner;
  requested = required_size;
  was_fresh = false;
  if(next_owner == Owner::NONE || required_size == 0 || required_size > sizeof(workspace)) return false;
  if(active != Owner::NONE && active != next_owner) return false;

  if(active == next_owner) {
    active_depth++;
    memory = workspace;
    return true;
  }

  if(resident != next_owner) {
    memset(workspace, 0, sizeof(workspace));
    resident = next_owner;
    was_fresh = true;
  }
  active = next_owner;
  active_depth = 1;
  memory = workspace;
  return true;
}

Lease::~Lease(void) {
  reset();
}

void Lease::reset(void) {
  if(memory == NULL) return;
  if(active != owner || active_depth == 0) {
    __builtin_trap();
  }
  active_depth--;
  if(active_depth == 0) active = Owner::NONE;
  memory = NULL;
  owner = Owner::NONE;
  requested = 0;
  was_fresh = false;
}

Owner resident_owner(void) {
  return resident;
}

Owner active_owner(void) {
  return active;
}

void* data(Owner owner) {
  if(owner == Owner::NONE || active != owner || active_depth == 0) return NULL;
  return workspace;
}

} // пространство имён language_workspace
