#ifndef MK61_SHARED_MEMORY_HPP
#define MK61_SHARED_MEMORY_HPP

#include "rust_types.h"

// Один диспетчер управляет всеми крупными статическими аренами прошивки.
// Физически арены остаются раздельными: некоторые режимы намеренно используют
// workspace и scratch/bulk одновременно. Общими являются правила владения,
// проверка контекста, поколение lease, вытеснение и диагностика.
namespace shared_memory {

static constexpr usize WORKSPACE_SIZE = 8192;
static constexpr usize SCRATCH_SIZE = 1600;

#if defined(STM32F401xC) || defined(STM32F401xE)
static constexpr usize BULK_SIZE = 1536;
#else
static constexpr usize BULK_SIZE = 8192;
#endif

#if defined(MK61_DISPLAY_UC1609) || defined(DISPLAY_UC1609) || \
    defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3) || \
    defined(MK61_BOARD_40TH) || \
    (defined(MK61_ENABLE_USB_SCREEN) && MK61_ENABLE_USB_SCREEN)
  #define MK61_SHARED_MEMORY_BULK_ENABLED 1
static constexpr bool BULK_ENABLED = true;
#else
  #define MK61_SHARED_MEMORY_BULK_ENABLED 0
static constexpr bool BULK_ENABLED = false;
#endif

enum class Arena : u8 {
  WORKSPACE = 0,
  SCRATCH,
  BULK,
  COUNT
};

// Owner един для всех арен. Один логический компонент может одновременно
// владеть несколькими аренами (например, Markdown: WORKSPACE + SCRATCH).
enum class Owner : u8 {
  NONE = 0,
  FOCAL,
  TINYBASIC,
  IMAGE_VIEWER,
  MARKDOWN_VIEWER,
  CHIP8,
  USB_DISK,
  TERMINAL_TRANSFER,
  CORE_TABLES,
  EXPLORER_VIEW,
  M61_FORMAT,
  PROGRAM_STORE_RENAME,
  PROGRAM_STORE_READ_RANGE,
  PROGRAM_STORE_COMPRESSION,
  VFAT_COMMIT,
  USB_CACHE,
  DISPLAY_FONT,
  WORKSPACE_SWAP,
  COUNT
};

using Reclaimer = bool (*)(void* context);

struct Snapshot {
  Arena arena;
  usize capacity;
  usize resident_size;
  usize high_water;
  Owner active_owner;
  Owner resident_owner;
  u16 active_depth;
  u16 max_depth;
  u32 acquisitions;
  u32 nested_acquisitions;
  u32 releases;
  u32 busy_failures;
  u32 cache_deferrals;
  u32 invalid_failures;
  u32 owner_switches;
  u32 clears;
  u32 cleared_bytes;
  u32 reclaim_attempts;
  u32 reclaims;
  u32 reclaim_failures;
  bool enabled;
  bool reclaimable;
};

class [[nodiscard]] Lease {
  public:
    constexpr Lease(void)
      : arena_(Arena::COUNT), owner_(Owner::NONE), memory_(nullptr),
        requested_(0), token_(0), fresh_(false), nested_(false) {}
    Lease(Arena arena, Owner owner, usize required);
    ~Lease(void);

    Lease(const Lease&) = delete;
    Lease& operator=(const Lease&) = delete;

    bool acquire(Arena arena, Owner owner, usize required);
    // Opportunistic cache may evict another reclaimable cache, but never
    // overwrites an inactive persistent owner such as FOCAL/TinyBASIC.
    bool acquire_cache(Arena arena, Owner owner, usize required);
    void reset(void);

    bool ok(void) const { return memory_ != nullptr; }
    bool fresh(void) const { return fresh_; }
    bool nested(void) const { return nested_; }
    Arena arena(void) const { return arena_; }
    Owner owner(void) const { return owner_; }
    usize size(void) const { return requested_; }
    u8* data(void) const { return memory_; }

    template<typename T>
    T* as(void) const {
      static_assert(alignof(T) <= 8,
                    "shared-memory types require alignment above arena guarantee");
      return memory_ != nullptr && sizeof(T) <= requested_
          ? reinterpret_cast<T*>(memory_) : nullptr;
    }

    // Разрешает другому владельцу синхронно вытеснить эту аренду. Callback
    // обязан только переключить использующий память код на безопасный fallback
    // и вызвать reset() исходного lease; I/O и повторный acquire запрещены.
    bool set_reclaimer(Reclaimer callback, void* context = nullptr);

    // A validated snapshot has replaced the zeroed bytes of a newly acquired
    // persistent arena. Only the snapshot layer should call this.
    bool mark_restored(void);

  private:
    Arena arena_;
    Owner owner_;
    u8* memory_;
    usize requested_;
    u32 token_;
    bool fresh_;
    bool nested_;

    bool acquire_impl(Arena arena, Owner owner, usize required,
                      bool opportunistic);
};

usize capacity(Arena arena);
bool enabled(Arena arena);
Owner active_owner(Arena arena);
Owner resident_owner(Arena arena);
// Idempotently forget retained state once the current outer lease, if any,
// is released.
// This is used by multi-command clients such as fsput: their bytes must
// survive between chunks, but become disposable after end/cancel/error.
bool discard_resident(Arena arena, Owner owner);
void* data(Arena arena, Owner owner);
bool contains(Arena arena, const void* pointer, usize size = 1);
Snapshot snapshot(Arena arena);
void reset_statistics(void);
const char* arena_name(Arena arena);
const char* owner_name(Owner owner);

} // namespace shared_memory

#endif
