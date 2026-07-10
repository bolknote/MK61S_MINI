#include "shared_scratch.hpp"

namespace shared_scratch {

alignas(8) static u8 scratch[SIZE];
static Owner active_owner = Owner::NONE;
static u32 active_token = 0;
static u32 next_token = 0;

static bool interrupt_context(void) {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr = 0;
  __asm__ volatile ("mrs %0, ipsr" : "=r" (ipsr));
  return ipsr != 0;
#else
  return false;
#endif
}

Lease::Lease(Owner next_owner, usize required)
  : owner(next_owner), buffer(0), requested(0), token(0) {
  if(next_owner == Owner::NONE || required == 0 || required > SIZE || active_owner != Owner::NONE || interrupt_context()) return;
  active_owner = next_owner;
  next_token++;
  if(next_token == 0) next_token++;
  active_token = next_token;
  token = active_token;
  requested = required;
  buffer = scratch;
}

Lease::~Lease(void) {
  if(buffer == 0) return;
  // Only this lease can release its reservation. With the raw release API
  // removed, a mismatch indicates memory corruption or a lifetime bug.
  if(active_owner != owner || active_token != token) __builtin_trap();
  active_owner = Owner::NONE;
  active_token = 0;
}

Owner current_owner(void) {
  return active_owner;
}

} // namespace shared_scratch
