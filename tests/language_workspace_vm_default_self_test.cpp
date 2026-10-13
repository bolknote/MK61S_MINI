#include "config.h"
#include "language_workspace.hpp"
#include "workspace_swap.hpp"
#include <cassert>
#include <cstdio>

// No explicit MK61_VM_FILE_CACHE define: exercise the real config.h policy
// in language_workspace.cpp, not only in the client translation unit.
constexpr bool vm_cache_on=MK61_VM_FILE_CACHE;
constexpr auto mapped=vm_cache_on?shared_memory::Owner::LANGUAGE_VM:shared_memory::Owner::NONE;
namespace {unsigned acquires;unsigned releases;unsigned char storage;}
namespace shared_memory {
Lease::~Lease() {}
void Lease::reset() {++releases;}
Owner resident_owner(Arena arena) {assert(arena==Arena::WORKSPACE);return Owner::LANGUAGE_VM;}
Owner active_owner(Arena arena) {return resident_owner(arena);}
bool discard_resident(Arena arena,Owner owner) {assert(arena==Arena::WORKSPACE && owner==mapped);return vm_cache_on;}
void* data(Arena arena,Owner owner) {assert(arena==Arena::WORKSPACE && owner==mapped);return vm_cache_on?&storage:nullptr;}
}
namespace workspace_swap {
bool acquire(shared_memory::Owner owner,usize size,AcquireMode mode,shared_memory::Lease&) {
  assert(owner==mapped && size==4176 && mode==AcquireMode::REQUIRED);
  ++acquires;return vm_cache_on;
}
}
int main() {
  {
    language_workspace::Lease lease;
    assert(lease.acquire(language_workspace::Owner::LANGUAGE_VM,4176)==vm_cache_on);
    assert(acquires==1);
    const auto expected=vm_cache_on?language_workspace::Owner::LANGUAGE_VM:language_workspace::Owner::NONE;
    assert(language_workspace::active_owner()==expected && language_workspace::resident_owner()==expected);
    assert(language_workspace::discard(language_workspace::Owner::LANGUAGE_VM)==vm_cache_on);
    assert((language_workspace::data(language_workspace::Owner::LANGUAGE_VM)!=nullptr)==vm_cache_on);
  }
  assert(releases==1);
  std::puts(vm_cache_on?"VM workspace implicit production policy: enabled PASS":"VM workspace disabled/no-cache policy: PASS");
}
