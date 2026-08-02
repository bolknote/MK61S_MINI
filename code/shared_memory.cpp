#include "shared_memory.hpp"

#include <stdint.h>
#include <string.h>

namespace shared_memory {
namespace {

alignas(8) static u8 workspace_storage[WORKSPACE_SIZE];
alignas(8) static u8 scratch_storage[SCRATCH_SIZE];
#if MK61_SHARED_MEMORY_BULK_ENABLED
alignas(8) static u8 bulk_storage[BULK_SIZE];
#endif

struct ArenaState {
  u8* memory;
  usize capacity;
  bool enabled;
  bool retain_resident;
  bool allow_nested;
  bool zero_new_owner;
  Owner active;
  Owner resident;
  usize resident_size;
  u16 depth;
  u16 max_depth;
  u32 token;
  Reclaimer reclaimer;
  void* reclaimer_context;
  bool reclaiming;
  bool discard_pending;
  usize high_water;
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
};

static ArenaState arenas[] = {
  {
    workspace_storage, WORKSPACE_SIZE, true,
    true, true, true,
    Owner::NONE, Owner::NONE, 0, 0, 0, 0,
    nullptr, nullptr, false, false,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  },
  {
    scratch_storage, SCRATCH_SIZE, true,
    false, false, false,
    Owner::NONE, Owner::NONE, 0, 0, 0, 0,
    nullptr, nullptr, false, false,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  },
  {
#if MK61_SHARED_MEMORY_BULK_ENABLED
    bulk_storage, BULK_SIZE, true,
#else
    nullptr, BULK_SIZE, false,
#endif
    false, false, false,
    Owner::NONE, Owner::NONE, 0, 0, 0, 0,
    nullptr, nullptr, false, false,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  }
};

static_assert(sizeof(arenas) / sizeof(arenas[0]) == (usize) Arena::COUNT,
              "shared-memory arena table is incomplete");

static ArenaState* state(Arena arena) {
  const usize index = (usize) arena;
  return index < (usize) Arena::COUNT ? &arenas[index] : nullptr;
}

static bool interrupt_context(void) {
#if defined(__arm__) || defined(__thumb__)
  u32 ipsr = 0;
  __asm__ volatile ("mrs %0, ipsr" : "=r" (ipsr));
  return ipsr != 0;
#else
  return false;
#endif
}

static void increment(u32& counter) {
  if(counter != UINT32_MAX) counter++;
}

static void note_invalid(ArenaState* arena) {
  if(arena != nullptr) increment(arena->invalid_failures);
}

static void add(u32& counter, usize value) {
  if(value >= UINT32_MAX || counter > UINT32_MAX - (u32) value) {
    counter = UINT32_MAX;
  } else {
    counter += (u32) value;
  }
}

static bool try_reclaim(ArenaState& arena) {
  if(arena.active == Owner::NONE || arena.reclaimer == nullptr ||
     arena.reclaiming || arena.depth != 1) return false;
  increment(arena.reclaim_attempts);
  arena.reclaiming = true;
  const Reclaimer callback = arena.reclaimer;
  void* const context = arena.reclaimer_context;
  const bool accepted = callback(context);
  arena.reclaiming = false;
  if(accepted && arena.active == Owner::NONE) {
    increment(arena.reclaims);
    return true;
  }
  increment(arena.reclaim_failures);
  return false;
}

static bool owner_retains_residency(Arena arena, Owner owner) {
  if(arena != Arena::WORKSPACE) return false;
  switch(owner) {
    // These clients intentionally release and reacquire the workspace while
    // one logical user operation remains in progress.
    case Owner::FOCAL:
    case Owner::TINYBASIC:
    case Owner::TERMINAL_TRANSFER:
      return true;
    default:
      return false;
  }
}

} // namespace

Lease::Lease(Arena arena, Owner owner, usize required) : Lease() {
  (void) acquire(arena, owner, required);
}

Lease::~Lease(void) {
  reset();
}

bool Lease::acquire(Arena next_arena, Owner next_owner,
                    usize required) {
  return acquire_impl(next_arena, next_owner, required, false);
}

bool Lease::acquire_cache(Arena next_arena, Owner next_owner,
                          usize required) {
  return acquire_impl(next_arena, next_owner, required, true);
}

bool Lease::acquire_impl(Arena next_arena, Owner next_owner,
                         usize required, bool opportunistic) {
  ArenaState* const arena = state(next_arena);
  if(arena == nullptr || !arena->enabled || next_owner == Owner::NONE ||
     next_owner >= Owner::COUNT || required == 0 ||
     required > (arena == nullptr ? 0 : arena->capacity) ||
     interrupt_context()) {
    note_invalid(arena);
    return false;
  }

  if(memory_ != nullptr) {
    return arena_ == next_arena && owner_ == next_owner &&
           required <= requested_;
  }

  // A reclaimer is a one-way, non-reentrant hand-off. It may reset the old
  // lease, but must not capture the arena again before returning.
  if(arena->reclaiming) {
    increment(arena->invalid_failures);
    return false;
  }

  if(arena->active != Owner::NONE && arena->active != next_owner) {
    if(!try_reclaim(*arena)) {
      increment(opportunistic ? arena->cache_deferrals
                              : arena->busy_failures);
      return false;
    }
  }

  if(opportunistic && arena->active == Owner::NONE &&
     arena->retain_resident && arena->resident != Owner::NONE &&
     arena->resident != next_owner) {
    increment(arena->cache_deferrals);
    return false;
  }

  bool is_nested = false;
  bool is_fresh = true;
  if(arena->active == next_owner) {
    if(!arena->allow_nested || arena->depth == 0 ||
       arena->depth == 0xFFFFU || arena->reclaimer != nullptr ||
       required > arena->resident_size) {
      increment(arena->busy_failures);
      return false;
    }
    arena->depth++;
    increment(arena->nested_acquisitions);
    is_nested = true;
    is_fresh = false;
  } else {
    if(arena->retain_resident) {
      is_fresh = arena->resident != next_owner;
      if(is_fresh) {
        if(arena->resident != Owner::NONE) increment(arena->owner_switches);
        arena->resident = next_owner;
        arena->resident_size = 0;
      }
      if(required > arena->resident_size && arena->zero_new_owner) {
        memset(arena->memory + arena->resident_size, 0,
               required - arena->resident_size);
        increment(arena->clears);
        add(arena->cleared_bytes, required - arena->resident_size);
      }
      if(required > arena->resident_size) arena->resident_size = required;
    } else {
      arena->resident = Owner::NONE;
      arena->resident_size = 0;
      is_fresh = true;
    }

    arena->active = next_owner;
    arena->depth = 1;
    arena->token++;
    if(arena->token == 0) arena->token++;
    increment(arena->acquisitions);
  }

  if(required > arena->high_water) arena->high_water = required;
  if(arena->depth > arena->max_depth) arena->max_depth = arena->depth;

  arena_ = next_arena;
  owner_ = next_owner;
  memory_ = arena->memory;
  requested_ = required;
  token_ = arena->token;
  fresh_ = is_fresh;
  nested_ = is_nested;
  return true;
}

void Lease::reset(void) {
  if(memory_ == nullptr) return;
  ArenaState* const arena = state(arena_);
  if(arena == nullptr || arena->active != owner_ || arena->depth == 0 ||
     arena->token != token_ || arena->memory != memory_) {
    __builtin_trap();
  }
  arena->depth--;
  increment(arena->releases);
  if(arena->depth == 0) {
    arena->active = Owner::NONE;
    arena->reclaimer = nullptr;
    arena->reclaimer_context = nullptr;
    if(arena->retain_resident &&
       (arena->discard_pending ||
        !owner_retains_residency(arena_, owner_))) {
      arena->resident = Owner::NONE;
      arena->resident_size = 0;
    }
    arena->discard_pending = false;
  }
  arena_ = Arena::COUNT;
  owner_ = Owner::NONE;
  memory_ = nullptr;
  requested_ = 0;
  token_ = 0;
  fresh_ = false;
  nested_ = false;
}

bool Lease::set_reclaimer(Reclaimer callback, void* context) {
  if(memory_ == nullptr || nested_ || callback == nullptr) return false;
  ArenaState* const arena = state(arena_);
  if(arena == nullptr || arena->active != owner_ || arena->depth != 1 ||
     arena->token != token_ || arena->reclaimer != nullptr ||
     arena->reclaiming) return false;
  arena->reclaimer = callback;
  arena->reclaimer_context = context;
  return true;
}

bool Lease::mark_restored(void) {
  if(memory_ == nullptr || nested_ || !fresh_) return false;
  const ArenaState* const arena = state(arena_);
  if(arena == nullptr || arena->active != owner_ || arena->depth != 1 ||
     arena->token != token_ || arena->memory != memory_) return false;
  fresh_ = false;
  return true;
}

usize capacity(Arena arena) {
  const ArenaState* const value = state(arena);
  return value == nullptr ? 0 : value->capacity;
}

bool enabled(Arena arena) {
  const ArenaState* const value = state(arena);
  return value != nullptr && value->enabled;
}

Owner active_owner(Arena arena) {
  const ArenaState* const value = state(arena);
  return value == nullptr ? Owner::NONE : value->active;
}

Owner resident_owner(Arena arena) {
  const ArenaState* const value = state(arena);
  return value == nullptr ? Owner::NONE : value->resident;
}

bool discard_resident(Arena arena, Owner owner) {
  ArenaState* const value = state(arena);
  if(value == nullptr || !value->enabled || owner == Owner::NONE ||
     owner >= Owner::COUNT || interrupt_context() || value->reclaiming) {
    note_invalid(value);
    return false;
  }
  // Cancellation and cleanup paths are intentionally repeatable. An absent
  // resident is already in the requested state and must not pollute the
  // invalid-operation counter on every unrelated terminal command.
  if(value->resident != owner && value->active != owner) return true;
  if(value->resident != owner ||
     (value->active != Owner::NONE && value->active != owner)) {
    note_invalid(value);
    return false;
  }
  if(value->active == owner) {
    value->discard_pending = true;
  } else {
    value->resident = Owner::NONE;
    value->resident_size = 0;
    value->discard_pending = false;
  }
  return true;
}

void* data(Arena arena, Owner owner) {
  ArenaState* const value = state(arena);
  return value != nullptr && owner != Owner::NONE &&
         value->active == owner && value->depth != 0
      ? value->memory : nullptr;
}

bool contains(Arena arena, const void* pointer, usize size) {
  const ArenaState* const value = state(arena);
  if(value == nullptr || !value->enabled || value->memory == nullptr ||
     pointer == nullptr || size == 0) return false;
  const uintptr_t begin = (uintptr_t) value->memory;
  const uintptr_t probe = (uintptr_t) pointer;
  if(value->capacity > UINTPTR_MAX - begin || probe < begin ||
     size > UINTPTR_MAX - probe) return false;
  return probe + size <= begin + value->capacity;
}

Snapshot snapshot(Arena arena) {
  const ArenaState* const value = state(arena);
  if(value == nullptr) {
    const Snapshot empty = {};
    return empty;
  }
  const Snapshot result = {
    arena,
    value->capacity,
    value->resident_size,
    value->high_water,
    value->active,
    value->resident,
    value->depth,
    value->max_depth,
    value->acquisitions,
    value->nested_acquisitions,
    value->releases,
    value->busy_failures,
    value->cache_deferrals,
    value->invalid_failures,
    value->owner_switches,
    value->clears,
    value->cleared_bytes,
    value->reclaim_attempts,
    value->reclaims,
    value->reclaim_failures,
    value->enabled,
    value->reclaimer != nullptr
  };
  return result;
}

void reset_statistics(void) {
  for(usize index = 0; index < (usize) Arena::COUNT; index++) {
    ArenaState& arena = arenas[index];
    arena.high_water = arena.active == Owner::NONE ? 0 : arena.resident_size;
    arena.max_depth = arena.depth;
    arena.acquisitions = 0;
    arena.nested_acquisitions = 0;
    arena.releases = 0;
    arena.busy_failures = 0;
    arena.cache_deferrals = 0;
    arena.invalid_failures = 0;
    arena.owner_switches = 0;
    arena.clears = 0;
    arena.cleared_bytes = 0;
    arena.reclaim_attempts = 0;
    arena.reclaims = 0;
    arena.reclaim_failures = 0;
  }
}

const char* arena_name(Arena arena) {
  switch(arena) {
    case Arena::WORKSPACE: return "workspace";
    case Arena::SCRATCH: return "scratch";
    case Arena::BULK: return "bulk";
    case Arena::COUNT: break;
  }
  return "invalid";
}

const char* owner_name(Owner owner) {
  switch(owner) {
    case Owner::NONE: return "none";
    case Owner::FOCAL: return "focal";
    case Owner::TINYBASIC: return "basic";
    case Owner::IMAGE_VIEWER: return "image";
    case Owner::MARKDOWN_VIEWER: return "markdown";
    case Owner::CHIP8: return "chip8";
    case Owner::USB_DISK: return "usb-disk";
    case Owner::TERMINAL_TRANSFER: return "terminal";
    case Owner::CORE_TABLES: return "core-tables";
    case Owner::EXPLORER_VIEW: return "explorer";
    case Owner::M61_FORMAT: return "m61-format";
    case Owner::PROGRAM_STORE_RENAME: return "store-rename";
    case Owner::PROGRAM_STORE_READ_RANGE: return "store-read";
    case Owner::PROGRAM_STORE_COMPRESSION: return "zx0";
    case Owner::VFAT_COMMIT: return "vfat-commit";
    case Owner::USB_CACHE: return "usb-cache";
    case Owner::DISPLAY_FONT: return "font";
    case Owner::WORKSPACE_SWAP: return "workspace-swap";
    case Owner::COUNT: break;
  }
  return "invalid";
}

} // namespace shared_memory
