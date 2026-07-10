#ifndef LANGUAGE_WORKSPACE_HPP
#define LANGUAGE_WORKSPACE_HPP

#include "rust_types.h"

namespace language_workspace {

enum class Owner : u8 {
  NONE,
  FOCAL,
  TINYBASIC,
  USB_DISK
};

static constexpr usize SIZE = 8192;

// Exclusive lease for one of the large, mutually exclusive runtimes. Leases
// may be nested by the same owner, but a different owner cannot evict live
// state. The previous resident is cleared only when the outermost lease for a
// new owner is acquired.
class [[nodiscard]] Lease {
  public:
    Lease(void);
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return memory != 0; }
    bool fresh(void) const { return was_fresh; }
    void* data(void) const { return memory; }
    usize size(void) const { return requested; }

    bool acquire(Owner owner, usize required);
    void reset(void);

  private:
    Owner owner;
    void* memory;
    usize requested;
    bool was_fresh;
};

Owner resident_owner(void);
Owner active_owner(void);
void* data(Owner owner);

} // namespace language_workspace

#endif
