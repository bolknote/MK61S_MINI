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

constexpr u8 arena_mask(Arena arena) {
  return arena < Arena::COUNT ? (u8) (1U << (u8) arena) : 0;
}

namespace snapshot_schema {
static constexpr u8 FOCAL_RUNTIME = 1;
static constexpr u8 TINYBASIC_RUNTIME = 1;
} // namespace snapshot_schema

// Owner един для всех арен. Один логический компонент может одновременно
// владеть несколькими аренами (например, Markdown: WORKSPACE + SCRATCH).
enum class Owner : u8 {
#define MK61_SHARED_MEMORY_OWNER(name, text, allowed, persistent, cache, evictable, schema) name,
#include "shared_memory_owner_catalog.inc"
#undef MK61_SHARED_MEMORY_OWNER
  COUNT
};

struct OwnerPolicy {
  u8 allowed_arenas;
  u8 persistent_arenas;
  u8 cache_arenas;
  u8 evictable_arenas;
  u8 snapshot_schema;
};

static_assert(sizeof(OwnerPolicy) == 5,
              "shared-memory owner policy must remain a packed byte table");

enum class EvictionDecision : u8 {
  KEEP = 0,
  RELEASE
};

// Callback лишь переводит клиента на безопасный fallback. Lease отзывает сам
// менеджер после RELEASE, поэтому callback не получает ни Lease, ни context.
using EvictionPrepare = EvictionDecision (*)(void);

class ResidentToken {
  public:
    constexpr ResidentToken(void)
      : arena_(Arena::COUNT), owner_(Owner::NONE), size_(0), epoch_(0) {}

    bool valid(void) const {
      return arena_ < Arena::COUNT && owner_ != Owner::NONE && epoch_ != 0;
    }
    Arena arena(void) const { return arena_; }
    Owner owner(void) const { return owner_; }
    usize size(void) const { return size_; }
    u32 epoch(void) const { return epoch_; }

  private:
    Arena arena_;
    Owner owner_;
    usize size_;
    u32 epoch_;

    constexpr ResidentToken(Arena arena, Owner owner, usize size, u32 epoch)
      : arena_(arena), owner_(owner), size_(size), epoch_(epoch) {}

    friend ResidentToken resident_token(Arena arena);
    friend bool commit_resident_handoff(const ResidentToken& token);
};

struct Snapshot {
  Arena arena;
  usize capacity;
  usize resident_size;
  u32 resident_epoch;
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

    // Разрешает синхронное вытеснение opportunistic cache. Callback только
    // готовит fallback; после RELEASE менеджер сам отзывает именно этот Lease.
    bool set_evictable(EvictionPrepare prepare);

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
    void release_impl(bool from_manager);
    void revoke_from_manager(void);

    friend bool detail_try_reclaim(Arena arena);
};

usize capacity(Arena arena);
bool enabled(Arena arena);
Owner active_owner(Arena arena);
Owner resident_owner(Arena arena);
OwnerPolicy owner_policy(Owner owner);
bool owner_allowed(Arena arena, Owner owner);
bool owner_persistent(Arena arena, Owner owner);
bool owner_cache_allowed(Arena arena, Owner owner);
bool owner_evictable(Arena arena, Owner owner);
u8 owner_snapshot_schema(Owner owner);
ResidentToken resident_token(Arena arena);
// Commit succeeds only if no acquisition has changed the resident state since
// token creation. On success the caller's validated backing image is the sole
// retained copy and the in-arena resident marker is forgotten.
bool commit_resident_handoff(const ResidentToken& token);
// Idempotently forget retained state once the current outer lease, if any,
// is released.
// This is used by multi-command clients such as fsput: their bytes must
// survive between chunks, but become disposable after end/cancel/error.
bool discard_resident(Arena arena, Owner owner);
void* data(Arena arena, Owner owner);
bool contains(Arena arena, const void* pointer, usize size = 1);
Snapshot snapshot(Arena arena);
bool validate_invariants(void);
void reset_statistics(void);
const char* arena_name(Arena arena);
const char* owner_name(Owner owner);

} // namespace shared_memory

#endif
