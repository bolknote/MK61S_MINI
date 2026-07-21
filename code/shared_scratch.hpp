#ifndef SHARED_SCRATCH_HPP
#define SHARED_SCRATCH_HPP

#include "rust_types.h"

namespace shared_scratch {

enum class Owner : u8 {
  NONE,
  EXPLORER_VIEW,
  IMAGE_VIEWER,
  M61_FORMAT,
  PROGRAM_STORE_RENAME,
  PROGRAM_STORE_GC,
  PROGRAM_STORE_READ_RANGE,
  VFAT_COMMIT,
  USB_CACHE
};

// Наибольший временный буфер содержимого файла. Меню файлов считывает видимые
// имена непосредственно из компактного индекса и не использует этот пул.
static constexpr usize SIZE = 1600;

class [[nodiscard]] Lease {
  public:
    constexpr Lease(void)
      : owner(Owner::NONE), buffer(0), requested(0), token(0) {}
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return buffer != 0; }
    u8* data(void) const { return buffer; }
    usize size(void) const { return requested; }
    bool acquire(Owner owner, usize required);
    void reset(void);

  private:
    Owner owner;
    u8* buffer;
    usize requested;
    u32 token;
};

Owner current_owner(void);

} // пространство имён shared_scratch

#endif
