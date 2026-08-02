#ifndef SHARED_SCRATCH_HPP
#define SHARED_SCRATCH_HPP

#include "shared_memory.hpp"

namespace shared_scratch {

enum class Owner : u8 {
  NONE,
  EXPLORER_VIEW,
  IMAGE_VIEWER,
  MARKDOWN_VIEWER,
  M61_FORMAT,
  PROGRAM_STORE_RENAME,
  PROGRAM_STORE_READ_RANGE,
  PROGRAM_STORE_COMPRESSION,
  VFAT_COMMIT,
  USB_CACHE,
  TERMINAL_TRANSFER
};

// Наибольший временный буфер содержимого файла. Меню файлов считывает видимые
// имена непосредственно из компактного индекса и не использует этот пул.
static constexpr usize SIZE = shared_memory::SCRATCH_SIZE;

class [[nodiscard]] Lease {
  public:
    constexpr Lease(void) : lease() {}
    Lease(Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool ok(void) const { return lease.ok(); }
    u8* data(void) const { return lease.data(); }
    usize size(void) const { return lease.size(); }
    bool acquire(Owner owner, usize required);
    void reset(void);

  private:
    shared_memory::Lease lease;
};

Owner current_owner(void);

} // пространство имён shared_scratch

#endif
