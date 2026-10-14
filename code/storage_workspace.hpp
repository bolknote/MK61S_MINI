#ifndef MK61_STORAGE_WORKSPACE_HPP
#define MK61_STORAGE_WORKSPACE_HPP
#include "rust_types.h"

#ifndef MK61_STORAGE_SHARED_TEMP
#if defined(ARDUINO_ARCH_STM32) && defined(STM32F411xE) && !defined(MK61_BUILD_USBDISK_MODULE)
#define MK61_STORAGE_SHARED_TEMP 1
#else
#define MK61_STORAGE_SHARED_TEMP 0
#endif
#endif

namespace storage_workspace {
#if MK61_STORAGE_SHARED_TEMP
// Sidecar discovery owns the whole pool. During import, file writes use the
// first 1024 bytes and the live short-file batch uses the remaining 512 bytes.
static constexpr usize SIZE = 1536;
static constexpr usize WRITE_BYTES = 1024;
static constexpr usize BATCH_BYTES = SIZE - WRITE_BYTES;
enum class Owner : u8 { NONE = 0, FILE_WRITE = 1, SIDECAR_SCAN = 2, IMPORT_BATCH = 4 };
class [[nodiscard]] Lease {
 public:
  Lease(Owner owner, usize required);
  ~Lease();
  Lease(const Lease&) = delete;
  Lease& operator=(const Lease&) = delete;
  bool ok() const { return owner_ != Owner::NONE; }
  u8* data() const;
 private:
  Owner owner_;
};
#endif
}
#endif
