#ifndef MK61_SHARED_MEMORY_BUFFER_HPP
#define MK61_SHARED_MEMORY_BUFFER_HPP
#include "shared_memory.hpp"

namespace shared_memory {
// DIRECT preserves the ordinary SRAM pointer contract. BLOCK may use an
// indirect external device, falling back to SRAM. EXTERNAL_ONLY never uses heap.
enum class BufferAccess : u8 { DIRECT, BLOCK, EXTERNAL_ONLY };
enum class BufferStorage : u8 { NONE, INTERNAL, EXTERNAL_DEVICE };
struct BufferBackend {
  usize capacity = 0;
  bool (*available)() = nullptr;
  bool (*read)(u32 address, void* bytes, usize count) = nullptr;
  bool (*write)(u32 address, const void* bytes, usize count) = nullptr;
  bool (*foreground)() = nullptr;
};
struct BufferStatistics {
  usize internal_used, external_used, external_capacity, external_largest;
  usize internal_high_water, external_high_water;
  u32 active, external_active, pinned, acquisitions, releases, reclaims;
  u32 failures, io_errors;
};
// Install once, in foreground, before allocating buffers. Backend callbacks
// have firmware lifetime; configuration is copied. No external device is
// required on STM32 or in an ordinary host build.
bool configure_buffer_backend(const BufferBackend& backend);
BufferStatistics buffer_statistics();
bool validate_buffer_invariants();

class BufferWindow;
class [[nodiscard]] Buffer {
 public:
  constexpr Buffer() = default;
  ~Buffer();
  Buffer(const Buffer&) = delete;
  Buffer& operator=(const Buffer&) = delete;
  bool acquire(Owner owner, usize size, BufferAccess access = BufferAccess::DIRECT);
  // Optional external caches yield to required buffers. The callback prepares
  // a fallback and returns RELEASE; the manager itself revokes the lease.
  bool acquire_cache(Owner owner, usize size, EvictionPrepare prepare);
  bool reset(); // Refuses while a window is live; parent must outlive windows.
  bool ok() const;
  u8* data() const { return storage_ == BufferStorage::INTERNAL ? memory_ : nullptr; }
  usize size() const { return size_; }
  Owner owner() const { return owner_; }
  BufferStorage storage() const { return storage_; }
  u32 generation() const { return generation_; }
  bool read(usize offset, void* bytes, usize count) const;
  bool write(usize offset, const void* bytes, usize count);
  bool fill(u8 value = 0);
 private:
  u8* memory_ = nullptr;
  Buffer* next_ = nullptr;
  EvictionPrepare eviction_ = nullptr;
  usize size_ = 0, reserved_ = 0;
  u32 address_ = 0, generation_ = 0;
  unsigned pins_ = 0;
  Owner owner_ = Owner::NONE;
  BufferStorage storage_ = BufferStorage::NONE;
  bool acquire_impl(Owner, usize, BufferAccess, EvictionPrepare);
  void release_impl();
  static u32 gap(usize size);
  static bool reclaim_one();
  friend class BufferWindow;
  friend BufferStatistics buffer_statistics();
  friend bool validate_buffer_invariants();
};

// A bounded SRAM window for code requiring a pointer. External bytes are
// copied in on acquisition. writeback() reports I/O failure explicitly;
// destruction discards uncommitted edits and releases the pin. It never
// performs an unreportable write from a destructor or interrupt.
class [[nodiscard]] BufferWindow {
 public:
  constexpr BufferWindow() = default;
  ~BufferWindow();
  BufferWindow(const BufferWindow&) = delete;
  BufferWindow& operator=(const BufferWindow&) = delete;
  bool acquire(Buffer& parent, usize offset, usize size, bool writable = false);
  bool writeback();
  void reset();
  u8* data() const { return parent_ ? bytes_ : nullptr; }
  usize size() const { return parent_ ? size_ : 0; }
 private:
  Buffer staging_;
  Buffer* parent_ = nullptr;
  u8* bytes_ = nullptr;
  usize offset_ = 0, size_ = 0;
  u32 generation_ = 0;
  bool writable_ = false;
};
} // namespace shared_memory
#endif
