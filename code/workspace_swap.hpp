#ifndef MK61_WORKSPACE_SWAP_HPP
#define MK61_WORKSPACE_SWAP_HPP

#include "shared_memory.hpp"

// Opportunistic, RAM-only swap for persistent language runtimes. The backing
// store is the already existing BULK arena; no extra payload array and no flash
// writes are introduced. A foreground BULK owner may evict the image at any
// moment, so failure simply restores the pre-existing "fresh runtime" path.
namespace workspace_swap {

enum class AcquireMode : u8 {
  REQUIRED = 0,
  OPPORTUNISTIC
};

struct Statistics {
  bool enabled;
  bool valid;
  bool compressed;
  shared_memory::Owner owner;
  u8 schema;
  usize raw_size;
  usize stored_size;
  u32 generation;
  u32 capture_attempts;
  u32 captures;
  u32 restores;
  u32 exchange_attempts;
  u32 exchanges;
  u32 exchange_fallbacks;
  u32 evictions;
  u32 busy_failures;
  u32 encode_failures;
  u32 integrity_failures;
};

// Единая точка входа для WORKSPACE: reacquire, restore, transactional
// capture/handoff и только затем непосредственный acquire. Opportunistic
// клиент никогда не уничтожает несохранённого persistent-владельца.
bool acquire(shared_memory::Owner owner, usize required, AcquireMode mode,
             shared_memory::Lease& destination);

Statistics statistics(void);
void reset_statistics(void);
void discard(void);

} // namespace workspace_swap

#endif
