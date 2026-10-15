#ifndef MK61_STORAGE_WORKSPACE_HPP
#define MK61_STORAGE_WORKSPACE_HPP
#include "rust_types.h"
#include "shared_memory.hpp"

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
#if MK61_SCOPED_RESIDENT_BUFFERS
using BufferOperation = bool (*)(const void*, u8*);
bool with_buffer(Owner owner, usize required, BufferOperation operation,
                 const void* context);
#endif
template<class Operation>
bool with_buffer(Owner owner, usize required, const Operation& operation) {
#if MK61_SCOPED_RESIDENT_BUFFERS
  return with_buffer(owner, required, [](const void* context, u8* memory) {
    return (*static_cast<const Operation*>(context))(memory);
  }, &operation);
#else
  Lease memory(owner, required);
  return memory.ok() && operation(memory.data());
#endif
}
#endif
}
#endif
