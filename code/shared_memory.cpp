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

// Имя остаётся частью ABI упаковщика System APP: адрес этого символа берётся
// из resident ELF и передаётся отдельной линковке модулей. Физически окно
// теперь принадлежит общему диспетчеру и может безопасно служить C5 staging.
extern "C" {
#if defined(__ELF__)
__attribute__((used, aligned(8), section(".bss.mk61_module_overlay")))
#else
__attribute__((used, aligned(8)))
#endif
u8 mk61_module_overlay[OVERLAY_SIZE];
}

struct ArenaPolicy {
  bool retain_resident;
  bool allow_nested;
  bool zero_new_owner;
};

static constexpr ArenaPolicy arena_policies[] = {
  {true, true, true},
  {false, false, false},
  {false, false, false},
  {false, false, false}
};

static constexpr OwnerPolicy owner_policies[] = {
#define MK61_SHARED_MEMORY_OWNER(name, text, allowed, persistent, cache, evictable, schema) \
  {(u8) (allowed), (u8) (persistent), (u8) (cache), (u8) (evictable), \
   (u8) (schema)},
#include "shared_memory_owner_catalog.inc"
#undef MK61_SHARED_MEMORY_OWNER
};

static const char* const owner_names[] = {
#define MK61_SHARED_MEMORY_OWNER(name, text, allowed, persistent, cache, evictable, schema) text,
#include "shared_memory_owner_catalog.inc"
#undef MK61_SHARED_MEMORY_OWNER
};

static constexpr u8 ALL_ARENAS =
    arena_mask(Arena::WORKSPACE) |
    arena_mask(Arena::SCRATCH) |
    arena_mask(Arena::BULK) |
    arena_mask(Arena::OVERLAY);

static constexpr bool policy_catalog_valid(void) {
  if(sizeof(arena_policies) / sizeof(arena_policies[0]) !=
     (usize) Arena::COUNT) return false;
  if(sizeof(owner_policies) / sizeof(owner_policies[0]) !=
     (usize) Owner::COUNT) return false;
  if(owner_policies[0].allowed_arenas != 0 ||
     owner_policies[0].persistent_arenas != 0 ||
     owner_policies[0].cache_arenas != 0 ||
     owner_policies[0].evictable_arenas != 0 ||
     owner_policies[0].snapshot_schema != 0) return false;
  for(usize index = 1; index < (usize) Owner::COUNT; index++) {
    const OwnerPolicy policy = owner_policies[index];
    if(policy.allowed_arenas == 0 ||
       (policy.allowed_arenas & ~ALL_ARENAS) != 0 ||
       (policy.persistent_arenas & ~policy.allowed_arenas) != 0 ||
       (policy.cache_arenas & ~policy.allowed_arenas) != 0 ||
       (policy.evictable_arenas & ~policy.cache_arenas) != 0 ||
       (policy.persistent_arenas & policy.cache_arenas) != 0) return false;
    if(policy.snapshot_schema != 0 &&
       (policy.persistent_arenas & arena_mask(Arena::WORKSPACE)) == 0) {
      return false;
    }
    if((policy.persistent_arenas & ~arena_mask(Arena::WORKSPACE)) != 0) {
      return false;
    }
  }
  return true;
}

static_assert(policy_catalog_valid(),
              "shared-memory owner policy catalog is inconsistent");
static_assert(sizeof(owner_names) / sizeof(owner_names[0]) ==
              (usize) Owner::COUNT,
              "shared-memory owner name catalog is incomplete");

struct ArenaState {
  u8* memory;
  usize capacity;
  usize resident_size;
  usize high_water;
  EvictionPrepare eviction_prepare;
  Lease* eviction_lease;
  u32 token;
  u32 resident_epoch;
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
  u16 depth;
  u16 max_depth;
  Owner active;
  Owner resident;
  u8 enabled : 1;
  u8 reclaiming : 1;
  u8 discard_pending : 1;
};

#define MK61_ARENA_STATE(memory_value, capacity_value, enabled_value)       \
  {memory_value, capacity_value, 0, 0, nullptr, nullptr, 0, 0,             \
   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,                                  \
   0, 0, Owner::NONE, Owner::NONE, enabled_value, false, false}

static ArenaState arenas[] = {
  MK61_ARENA_STATE(workspace_storage, WORKSPACE_SIZE, true),
  MK61_ARENA_STATE(scratch_storage, SCRATCH_SIZE, true),
#if MK61_SHARED_MEMORY_BULK_ENABLED
  MK61_ARENA_STATE(bulk_storage, BULK_SIZE, true),
#else
  MK61_ARENA_STATE(nullptr, BULK_SIZE, false),
#endif
  MK61_ARENA_STATE(mk61_module_overlay, OVERLAY_SIZE, true)
};

#undef MK61_ARENA_STATE

static_assert(sizeof(arenas) / sizeof(arenas[0]) == (usize) Arena::COUNT,
              "shared-memory arena table is incomplete");

// Eviction is a global one-way transition, not merely a lock on one arena.
// Scanning the three existing states costs no RAM and prevents a callback from
// acquiring or mutating another shared arena before the manager has revoked
// the registered lease.
static bool transition_in_progress(void) {
  for(usize index = 0; index < (usize) Arena::COUNT; index++) {
    if(arenas[index].reclaiming) return true;
  }
  return false;
}

static ArenaState* state(Arena arena) {
  const usize index = (usize) arena;
  return index < (usize) Arena::COUNT ? &arenas[index] : nullptr;
}

static const ArenaPolicy* arena_policy(Arena arena) {
  const usize index = (usize) arena;
  return index < (usize) Arena::COUNT ? &arena_policies[index] : nullptr;
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

static void advance_resident_epoch(ArenaState& arena) {
  // Epoch is an identity, not a statistic: it must keep changing after the
  // diagnostic counters have saturated. Zero remains reserved for "none".
  arena.resident_epoch++;
  if(arena.resident_epoch == 0) arena.resident_epoch = 1;
}

static void clear_resident(ArenaState& arena) {
  if(arena.resident != Owner::NONE || arena.resident_size != 0) {
    arena.resident = Owner::NONE;
    arena.resident_size = 0;
    advance_resident_epoch(arena);
  }
}

} // namespace

OwnerPolicy owner_policy(Owner owner) {
  const usize index = (usize) owner;
  if(index >= (usize) Owner::COUNT) {
    const OwnerPolicy invalid = {};
    return invalid;
  }
  return owner_policies[index];
}

bool owner_allowed(Arena arena, Owner owner) {
  return owner != Owner::NONE && owner < Owner::COUNT &&
         (owner_policy(owner).allowed_arenas & arena_mask(arena)) != 0;
}

bool owner_persistent(Arena arena, Owner owner) {
  return owner != Owner::NONE && owner < Owner::COUNT &&
         (owner_policy(owner).persistent_arenas & arena_mask(arena)) != 0;
}

bool owner_cache_allowed(Arena arena, Owner owner) {
  return owner != Owner::NONE && owner < Owner::COUNT &&
         (owner_policy(owner).cache_arenas & arena_mask(arena)) != 0;
}

bool owner_evictable(Arena arena, Owner owner) {
  return owner != Owner::NONE && owner < Owner::COUNT &&
         (owner_policy(owner).evictable_arenas & arena_mask(arena)) != 0;
}

u8 owner_snapshot_schema(Owner owner) {
  return owner != Owner::NONE && owner < Owner::COUNT
      ? owner_policy(owner).snapshot_schema : 0;
}

bool detail_try_reclaim(Arena arena_id) {
  ArenaState* const arena = state(arena_id);
  if(arena == nullptr || arena->active == Owner::NONE ||
     arena->eviction_prepare == nullptr || arena->eviction_lease == nullptr ||
     transition_in_progress() || arena->depth != 1) return false;
  increment(arena->reclaim_attempts);
  arena->reclaiming = true;
  const EvictionPrepare prepare = arena->eviction_prepare;
  Lease* const registered = arena->eviction_lease;
  const EvictionDecision decision = prepare();
  bool released = false;
  if(decision == EvictionDecision::RELEASE &&
     arena->active != Owner::NONE && arena->depth == 1 &&
     arena->eviction_lease == registered) {
    registered->revoke_from_manager();
    released = arena->active == Owner::NONE && arena->depth == 0;
  }
  arena->reclaiming = false;
  if(released) {
    increment(arena->reclaims);
    return true;
  }
  increment(arena->reclaim_failures);
  return false;
}

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
  const ArenaPolicy* const policy = arena_policy(next_arena);
  if(arena == nullptr || !arena->enabled || next_owner == Owner::NONE ||
     next_owner >= Owner::COUNT || required == 0 ||
     required > (arena == nullptr ? 0 : arena->capacity) || policy == nullptr ||
     !owner_allowed(next_arena, next_owner) ||
     (opportunistic && !owner_cache_allowed(next_arena, next_owner)) ||
     interrupt_context()) {
    note_invalid(arena);
    return false;
  }

  if(memory_ != nullptr) {
    return arena_ == next_arena && owner_ == next_owner &&
           required <= requested_;
  }

  // Eviction preparation is a one-way, non-reentrant hand-off. The callback
  // cannot acquire this arena; on RELEASE the manager revokes the old lease.
  if(transition_in_progress()) {
    increment(arena->invalid_failures);
    return false;
  }

  if(arena->active != Owner::NONE && arena->active != next_owner) {
    if(!detail_try_reclaim(next_arena)) {
      increment(opportunistic ? arena->cache_deferrals
                              : arena->busy_failures);
      return false;
    }
  }

  if(opportunistic && arena->active == Owner::NONE &&
     policy->retain_resident && arena->resident != Owner::NONE &&
     arena->resident != next_owner) {
    increment(arena->cache_deferrals);
    return false;
  }

  bool is_nested = false;
  bool is_fresh = true;
  if(arena->active == next_owner) {
    if(!policy->allow_nested || arena->depth == 0 ||
       arena->depth == 0xFFFFU || arena->eviction_prepare != nullptr ||
       required > arena->resident_size) {
      increment(arena->busy_failures);
      return false;
    }
    arena->depth++;
    increment(arena->nested_acquisitions);
    is_nested = true;
    is_fresh = false;
  } else {
    if(policy->retain_resident) {
      is_fresh = arena->resident != next_owner;
      if(is_fresh) {
        if(arena->resident != Owner::NONE) increment(arena->owner_switches);
        arena->resident = next_owner;
        arena->resident_size = 0;
      }
      if(required > arena->resident_size && policy->zero_new_owner) {
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
    if(policy->retain_resident) advance_resident_epoch(*arena);
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
  release_impl(false);
}

void Lease::release_impl(bool from_manager) {
  if(memory_ == nullptr) return;
  ArenaState* const arena = state(arena_);
  const ArenaPolicy* const policy = arena_policy(arena_);
  if(arena == nullptr || arena->active != owner_ || arena->depth == 0 ||
     arena->token != token_ || arena->memory != memory_ || policy == nullptr ||
     (transition_in_progress() && !from_manager) ||
     (from_manager && (!arena->reclaiming || nested_ || arena->depth != 1 ||
                       arena->eviction_lease != this))) {
    __builtin_trap();
  }
  arena->depth--;
  increment(arena->releases);
  if(arena->depth == 0) {
    arena->active = Owner::NONE;
    arena->eviction_prepare = nullptr;
    arena->eviction_lease = nullptr;
    if(policy->retain_resident &&
       (arena->discard_pending ||
        !owner_persistent(arena_, owner_))) {
      clear_resident(*arena);
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

void Lease::revoke_from_manager(void) {
  release_impl(true);
}

bool Lease::set_evictable(EvictionPrepare prepare) {
  if(memory_ == nullptr || nested_ || prepare == nullptr ||
     !owner_evictable(arena_, owner_)) return false;
  ArenaState* const arena = state(arena_);
  if(arena == nullptr || arena->active != owner_ || arena->depth != 1 ||
     arena->token != token_ || arena->eviction_prepare != nullptr ||
     transition_in_progress()) return false;
  arena->eviction_prepare = prepare;
  arena->eviction_lease = this;
  return true;
}

bool Lease::mark_restored(void) {
  if(memory_ == nullptr || nested_ || !fresh_ ||
     transition_in_progress()) return false;
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

ResidentToken resident_token(Arena arena) {
  const ArenaState* const value = state(arena);
  const ArenaPolicy* const policy = arena_policy(arena);
  if(value == nullptr || policy == nullptr || !value->enabled ||
     !policy->retain_resident || value->active != Owner::NONE ||
     value->resident == Owner::NONE || value->resident_size == 0 ||
     value->resident_epoch == 0 || transition_in_progress() ||
     interrupt_context()) return ResidentToken();
  return ResidentToken(arena, value->resident, value->resident_size,
                       value->resident_epoch);
}

bool commit_resident_handoff(const ResidentToken& token) {
  ArenaState* const value = state(token.arena_);
  const ArenaPolicy* const policy = arena_policy(token.arena_);
  if(!token.valid() || value == nullptr || policy == nullptr ||
     !value->enabled || !policy->retain_resident ||
     value->active != Owner::NONE || value->resident != token.owner_ ||
     value->resident_size != token.size_ ||
     value->resident_epoch != token.epoch_ || transition_in_progress() ||
     interrupt_context()) {
    note_invalid(value);
    return false;
  }
  clear_resident(*value);
  value->discard_pending = false;
  return true;
}

bool discard_resident(Arena arena, Owner owner) {
  ArenaState* const value = state(arena);
  if(value == nullptr || !value->enabled || owner == Owner::NONE ||
     owner >= Owner::COUNT || !owner_allowed(arena, owner) ||
     interrupt_context() || transition_in_progress()) {
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
    clear_resident(*value);
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
    value->resident_epoch,
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
    value->enabled != 0,
    value->eviction_prepare != nullptr
  };
  return result;
}

bool validate_invariants(void) {
  usize reclaiming_count = 0;
  for(usize index = 0; index < (usize) Arena::COUNT; index++) {
    const Arena arena_id = (Arena) index;
    const ArenaState& arena = arenas[index];
    const ArenaPolicy& policy = arena_policies[index];
    if(arena.reclaiming) reclaiming_count++;
    if(arena.capacity == 0 || arena.high_water > arena.capacity ||
       arena.high_water < arena.resident_size ||
       arena.max_depth < arena.depth ||
       (arena.enabled && arena.memory == nullptr) ||
       (!arena.enabled && arena.memory != nullptr) ||
       ((arena.active == Owner::NONE) != (arena.depth == 0)) ||
       ((arena.resident == Owner::NONE) != (arena.resident_size == 0)) ||
       (arena.resident_size > arena.capacity) ||
       (!policy.retain_resident &&
        (arena.resident != Owner::NONE || arena.resident_size != 0)) ||
       ((arena.eviction_prepare == nullptr) !=
        (arena.eviction_lease == nullptr))) return false;
    if(!arena.enabled &&
       (arena.active != Owner::NONE || arena.resident != Owner::NONE ||
        arena.depth != 0 || arena.eviction_prepare != nullptr ||
        arena.reclaiming || arena.discard_pending)) return false;
    if(arena.active != Owner::NONE) {
      if(!owner_allowed(arena_id, arena.active) || arena.token == 0 ||
         arena.depth == 0) return false;
      if(policy.retain_resident &&
         (arena.resident != arena.active || arena.resident_size == 0 ||
          arena.resident_epoch == 0)) return false;
    } else if(arena.resident != Owner::NONE &&
              !owner_persistent(arena_id, arena.resident)) {
      return false;
    }
    if(arena.eviction_prepare != nullptr &&
       (arena.active == Owner::NONE || arena.depth != 1 ||
        !owner_evictable(arena_id, arena.active))) return false;
    if(arena.discard_pending &&
       (arena.active == Owner::NONE || arena.resident != arena.active ||
        !policy.retain_resident)) return false;
    if(arena.reclaiming && arena.eviction_prepare == nullptr) return false;
  }
  return reclaiming_count <= 1;
}

void reset_statistics(void) {
  for(usize index = 0; index < (usize) Arena::COUNT; index++) {
    ArenaState& arena = arenas[index];
    // Inactive persistent bytes still occupy the arena and therefore form the
    // correct baseline for a new high-water measurement interval.
    arena.high_water = arena.resident_size;
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
    case Arena::OVERLAY: return "overlay";
    case Arena::COUNT: break;
  }
  return "invalid";
}

const char* owner_name(Owner owner) {
  const usize index = (usize) owner;
  return index < (usize) Owner::COUNT ? owner_names[index] : "invalid";
}

} // namespace shared_memory
