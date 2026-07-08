#ifndef SHARED_SCRATCH_HPP
#define SHARED_SCRATCH_HPP

#include "rust_types.h"

namespace shared_scratch {

enum class Owner : u8 {
  NONE,
  EXPLORER_VIEW,
  M61_SCRIPT,
  PROGRAM_STORE_RENAME,
  VFAT_COMMIT,
  STORED_M61_MENU
};

static constexpr usize SIZE = 1792;

class Lease {
  public:
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return buffer != 0; }
    u8* data(void) const { return buffer; }
    usize size(void) const { return SIZE; }

  private:
    Owner owner;
    u8* buffer;
};

u8* acquire(Owner owner, usize required);
void release(Owner owner);
u8* data(Owner owner);
Owner current_owner(void);

} // namespace shared_scratch

#endif
