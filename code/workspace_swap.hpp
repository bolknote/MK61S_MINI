#ifndef MK61_WORKSPACE_SWAP_HPP
#define MK61_WORKSPACE_SWAP_HPP

#include "shared_memory.hpp"

// Opportunistic, RAM-only swap for persistent language runtimes. The backing
// store is the already existing BULK arena; no extra payload array and no flash
// writes are introduced. A foreground BULK owner may evict the image at any
// moment, so failure simply restores the pre-existing "fresh runtime" path.
namespace workspace_swap {

enum class RestoreResult : u8 {
  NOT_FOUND = 0,
  ACQUIRED,
  BUSY
};

struct Statistics {
  bool enabled;
  bool valid;
  bool compressed;
  shared_memory::Owner owner;
  usize raw_size;
  usize stored_size;
  u32 generation;
  u32 capture_attempts;
  u32 captures;
  u32 restores;
  u32 evictions;
  u32 busy_failures;
  u32 encode_failures;
  u32 integrity_failures;
};

// Called only before a normal WORKSPACE ownership transition. Returns true
// when there was no language state to preserve or a complete validated image
// of that state is now resident in BULK. A foreground transition may ignore
// false and retain the historical clean-start behavior; an optional cache must
// not overwrite the workspace unless this returned true.
bool capture_resident_before(shared_memory::Owner next_owner);

// If an image for owner exists, acquires destination and restores it. ACQUIRED
// also covers a rejected/corrupt image: destination then remains fresh/zeroed.
RestoreResult restore(shared_memory::Owner owner, usize required,
                      shared_memory::Lease& destination);

Statistics statistics(void);
void reset_statistics(void);
void discard(void);

} // namespace workspace_swap

#endif
