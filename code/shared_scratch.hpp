#ifndef SHARED_SCRATCH_HPP
#define SHARED_SCRATCH_HPP

#include "rust_types.h"

namespace shared_scratch {

enum class Owner : u8 {
  NONE,
  EXPLORER_VIEW,
  M61_FORMAT,
  PROGRAM_STORE_RENAME,
  PROGRAM_STORE_GC,
  PROGRAM_STORE_READ_RANGE,
  VFAT_COMMIT,
  STORED_M61_MENU
};

// Largest transient file payload. Menu-only records use a compact view so
// they do not force this pool above the storage format's maximum file size.
static constexpr usize SIZE = 1536;

class [[nodiscard]] Lease {
  public:
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return buffer != 0; }
    u8* data(void) const { return buffer; }
    usize size(void) const { return requested; }

  private:
    Owner owner;
    u8* buffer;
    usize requested;
    u32 token;
};

Owner current_owner(void);

} // namespace shared_scratch

#endif
