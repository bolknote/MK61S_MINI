#include "storage_workspace.hpp"
#if MK61_STORAGE_SHARED_TEMP
namespace storage_workspace {
namespace {
alignas(8) u8 bytes[SIZE];
u8 active_owners;
bool interrupt_context() {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr;
  __asm__ volatile ("mrs %0, ipsr" : "=r" (ipsr));
  return ipsr != 0;
#else
  return false;
#endif
}
}
Lease::Lease(Owner owner, usize required) : owner_(Owner::NONE) {
  usize capacity = SIZE;
  u8 conflicts = 7;
  switch(owner) {
    case Owner::FILE_WRITE: capacity = WRITE_BYTES; conflicts = 3; break;
    case Owner::IMPORT_BATCH: capacity = BATCH_BYTES; conflicts = 6; break;
    case Owner::SIDECAR_SCAN: break;
    default: return;
  }
  if(!required || required > capacity || (active_owners & conflicts) ||
     interrupt_context()) return;
  active_owners |= static_cast<u8>(owner);
  owner_ = owner;
}
Lease::~Lease() {
  if(owner_ == Owner::NONE) return;
  const u8 bit = static_cast<u8>(owner_);
  if(!(active_owners & bit)) __builtin_trap();
  active_owners &= static_cast<u8>(~bit);
}
u8* Lease::data() const {
  if(owner_ == Owner::NONE || !(active_owners & static_cast<u8>(owner_))) return nullptr;
  return bytes + (owner_ == Owner::IMPORT_BATCH ? WRITE_BYTES : 0);
}
}
#endif
