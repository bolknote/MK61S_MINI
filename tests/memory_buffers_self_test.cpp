#include "../code/language_workspace.hpp"
#include "../code/crc32.hpp"
#include "../code/exclusive_buffer.hpp"
#include "../code/shared_memory.hpp"
#include "../code/shared_scratch.hpp"
#include "../code/workspace_swap.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#ifndef MK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE
#error "MK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE is required"
#endif

struct ReclaimProbe {
  bool called;
  shared_memory::Lease* attempted_lease;
  bool reacquired;
  shared_memory::Lease* attempted_other_lease;
  bool reacquired_other;
  bool discarded_resident;
};

static ReclaimProbe* active_reclaim_probe = nullptr;

static shared_memory::EvictionDecision releasing_reclaim_probe(void) {
  assert(active_reclaim_probe != nullptr);
  active_reclaim_probe->called = true;
  return shared_memory::EvictionDecision::RELEASE;
}

static shared_memory::EvictionDecision rejecting_reclaim_probe(void) {
  assert(active_reclaim_probe != nullptr);
  active_reclaim_probe->called = true;
  return shared_memory::EvictionDecision::KEEP;
}

static shared_memory::EvictionDecision reentrant_reclaim_probe(void) {
  assert(active_reclaim_probe != nullptr);
  active_reclaim_probe->called = true;
  active_reclaim_probe->reacquired =
      active_reclaim_probe->attempted_lease->acquire(
      shared_memory::Arena::WORKSPACE,
      shared_memory::Owner::CORE_TABLES, 64);
  active_reclaim_probe->reacquired_other =
      active_reclaim_probe->attempted_other_lease->acquire(
      shared_memory::Arena::SCRATCH,
      shared_memory::Owner::EXPLORER_VIEW, 64);
  active_reclaim_probe->discarded_resident =
      shared_memory::discard_resident(
          shared_memory::Arena::WORKSPACE, shared_memory::Owner::FOCAL);
  assert(shared_memory::validate_invariants());
  return shared_memory::EvictionDecision::RELEASE;
}

static void reseal_swap_header(u8* bytes, usize header_crc_offset) {
  const u32 crc = mk61_crc32::calculate(bytes, header_crc_offset);
  memcpy(bytes + header_crc_offset, &crc, sizeof(crc));
}

struct ModelLease {
  bool held;
  shared_memory::Owner owner;
  usize requested;
};

struct WorkspaceModel {
  shared_memory::Owner active;
  shared_memory::Owner resident;
  usize resident_size;
  u16 depth;
  bool discard_pending;
  ModelLease leases[4];
};

static u32 model_random(u32& state) {
  state ^= state << 13;
  state ^= state >> 17;
  state ^= state << 5;
  return state;
}

static bool model_acquire(WorkspaceModel& model, usize slot,
                          shared_memory::Owner owner, usize required,
                          bool opportunistic, bool& fresh) {
  fresh = false;
  if(model.leases[slot].held || required == 0 ||
     required > shared_memory::WORKSPACE_SIZE ||
     !shared_memory::owner_allowed(shared_memory::Arena::WORKSPACE, owner) ||
     (opportunistic && !shared_memory::owner_cache_allowed(
         shared_memory::Arena::WORKSPACE, owner))) return false;
  if(model.active != shared_memory::Owner::NONE) {
    if(model.active != owner || required > model.resident_size) return false;
    model.depth++;
  } else {
    if(opportunistic && model.resident != shared_memory::Owner::NONE &&
       model.resident != owner) return false;
    fresh = model.resident != owner;
    if(fresh) {
      model.resident = owner;
      model.resident_size = 0;
    }
    if(required > model.resident_size) model.resident_size = required;
    model.active = owner;
    model.depth = 1;
  }
  model.leases[slot] = {true, owner, required};
  return true;
}

static void model_release(WorkspaceModel& model, usize slot) {
  if(!model.leases[slot].held) return;
  assert(model.active == model.leases[slot].owner && model.depth != 0);
  const shared_memory::Owner owner = model.leases[slot].owner;
  model.leases[slot] = {false, shared_memory::Owner::NONE, 0};
  model.depth--;
  if(model.depth == 0) {
    model.active = shared_memory::Owner::NONE;
    if(model.discard_pending || !shared_memory::owner_persistent(
         shared_memory::Arena::WORKSPACE, owner)) {
      model.resident = shared_memory::Owner::NONE;
      model.resident_size = 0;
    }
    model.discard_pending = false;
  }
}

static bool model_discard(WorkspaceModel& model,
                          shared_memory::Owner owner) {
  if(model.resident != owner && model.active != owner) return true;
  if(model.resident != owner ||
     (model.active != shared_memory::Owner::NONE &&
      model.active != owner)) return false;
  if(model.active == owner) {
    model.discard_pending = true;
  } else {
    model.resident = shared_memory::Owner::NONE;
    model.resident_size = 0;
    model.discard_pending = false;
  }
  return true;
}

static void assert_workspace_model(const WorkspaceModel& model) {
  const shared_memory::Snapshot actual =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  assert(actual.active_owner == model.active);
  assert(actual.resident_owner == model.resident);
  assert(actual.resident_size == model.resident_size);
  assert(actual.active_depth == model.depth);
  assert(actual.resident_owner == shared_memory::Owner::NONE ||
         actual.resident_epoch != 0);
  assert(shared_memory::validate_invariants());
}

static void run_workspace_state_model(void) {
  workspace_swap::discard();
  assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) ==
         shared_memory::Owner::NONE);
  const shared_memory::Owner old_resident =
      shared_memory::resident_owner(shared_memory::Arena::WORKSPACE);
  if(old_resident != shared_memory::Owner::NONE) {
    assert(shared_memory::discard_resident(
        shared_memory::Arena::WORKSPACE, old_resident));
  }

  WorkspaceModel model = {};
  model.active = shared_memory::Owner::NONE;
  model.resident = shared_memory::Owner::NONE;
  shared_memory::Lease leases[4];
  static constexpr shared_memory::Owner normal_owners[] = {
    shared_memory::Owner::FOCAL,
    shared_memory::Owner::TINYBASIC,
    shared_memory::Owner::MARKDOWN_VIEWER,
    shared_memory::Owner::CORE_TABLES
  };
  static constexpr shared_memory::Owner cache_owners[] = {
    shared_memory::Owner::CORE_TABLES,
    shared_memory::Owner::PROGRAM_STORE_COMPRESSION
  };
  static constexpr shared_memory::Owner discard_owners[] = {
    shared_memory::Owner::FOCAL,
    shared_memory::Owner::TINYBASIC,
    shared_memory::Owner::TERMINAL_TRANSFER
  };

  u32 random = 0x61A4E10DUL;
  for(usize iteration = 0; iteration < 20000; iteration++) {
    const u32 choice = model_random(random);
    const usize slot = (usize) (choice & 3U);
    if(model.leases[slot].held) {
      if((choice & 4U) != 0) {
        const usize repeated = (usize) (model_random(random) % 384U) + 1U;
        const bool expected = repeated <= model.leases[slot].requested;
        assert(leases[slot].acquire(
                   shared_memory::Arena::WORKSPACE,
                   model.leases[slot].owner, repeated) == expected);
      } else {
        leases[slot].reset();
        model_release(model, slot);
      }
    } else if((choice % 10U) < 8U) {
      const bool opportunistic = (choice & 8U) != 0;
      const shared_memory::Owner owner = opportunistic
          ? cache_owners[model_random(random) %
                         (sizeof(cache_owners) / sizeof(cache_owners[0]))]
          : normal_owners[model_random(random) %
                          (sizeof(normal_owners) / sizeof(normal_owners[0]))];
      const usize required =
          (usize) (model_random(random) % 320U) + 1U;
      bool expected_fresh = false;
      const bool expected = model_acquire(
          model, slot, owner, required, opportunistic, expected_fresh);
      const bool acquired = opportunistic
          ? leases[slot].acquire_cache(shared_memory::Arena::WORKSPACE,
                                      owner, required)
          : leases[slot].acquire(shared_memory::Arena::WORKSPACE,
                                owner, required);
      assert(acquired == expected);
      if(acquired) assert(leases[slot].fresh() == expected_fresh);
    } else {
      const shared_memory::Owner owner =
          discard_owners[model_random(random) %
              (sizeof(discard_owners) / sizeof(discard_owners[0]))];
      assert(shared_memory::discard_resident(
                 shared_memory::Arena::WORKSPACE, owner) ==
             model_discard(model, owner));
    }
    assert_workspace_model(model);
  }

  for(usize slot = 0; slot < 4; slot++) {
    leases[slot].reset();
    model_release(model, slot);
  }
  if(model.resident != shared_memory::Owner::NONE) {
    const shared_memory::Owner owner = model.resident;
    assert(shared_memory::discard_resident(
        shared_memory::Arena::WORKSPACE, owner));
    assert(model_discard(model, owner));
  }
  assert_workspace_model(model);
}

int main(void) {
  using language_workspace::Owner;

  static_assert(MK61_EXCLUSIVE_BUFFER_ENABLED,
                "graphical build must provide the exclusive buffer");
  static_assert(exclusive_buffer::SIZE == MK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE,
                "exclusive buffer size differs from the MCU policy");

  assert(shared_memory::validate_invariants());
  const shared_memory::OwnerPolicy focal_policy =
      shared_memory::owner_policy(shared_memory::Owner::FOCAL);
  assert(focal_policy.allowed_arenas ==
         shared_memory::arena_mask(shared_memory::Arena::WORKSPACE));
  assert(focal_policy.persistent_arenas ==
         shared_memory::arena_mask(shared_memory::Arena::WORKSPACE));
  assert(focal_policy.cache_arenas == 0 &&
         focal_policy.evictable_arenas == 0 &&
         focal_policy.snapshot_schema == 1);
  const shared_memory::OwnerPolicy compression_policy =
      shared_memory::owner_policy(
          shared_memory::Owner::PROGRAM_STORE_COMPRESSION);
  assert(compression_policy.allowed_arenas ==
         (shared_memory::arena_mask(shared_memory::Arena::WORKSPACE) |
          shared_memory::arena_mask(shared_memory::Arena::SCRATCH) |
          shared_memory::arena_mask(shared_memory::Arena::BULK)));
  assert(compression_policy.cache_arenas ==
         shared_memory::arena_mask(shared_memory::Arena::WORKSPACE));
  assert(compression_policy.evictable_arenas == 0);
  const shared_memory::OwnerPolicy core_policy =
      shared_memory::owner_policy(shared_memory::Owner::CORE_TABLES);
  assert(core_policy.cache_arenas ==
         shared_memory::arena_mask(shared_memory::Arena::WORKSPACE));
  assert(core_policy.evictable_arenas ==
         shared_memory::arena_mask(shared_memory::Arena::WORKSPACE));
  assert(!shared_memory::owner_allowed(
      shared_memory::Arena::BULK, shared_memory::Owner::FOCAL));
  {
    shared_memory::Lease invalid_policy;
    assert(!invalid_policy.acquire(
        shared_memory::Arena::BULK, shared_memory::Owner::FOCAL, 1));
    assert(!invalid_policy.acquire_cache(
        shared_memory::Arena::WORKSPACE, shared_memory::Owner::FOCAL, 1));
  }
  {
    shared_memory::Lease compression_cache;
    assert(compression_cache.acquire_cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::PROGRAM_STORE_COMPRESSION, 64));
    // Opportunistic use and synchronous revocation are distinct promises.
    assert(!compression_cache.set_evictable(releasing_reclaim_probe));
  }

  assert(language_workspace::resident_owner() == Owner::NONE);
  assert(language_workspace::active_owner() == Owner::NONE);

  {
    language_workspace::Lease focal(Owner::FOCAL, 128);
    assert(focal.ok());
    assert(focal.fresh());
    assert(focal.size() == 128);
    assert(language_workspace::active_owner() == Owner::FOCAL);
    u8* focal_data = (u8*) focal.data();
    focal_data[0] = 0x61;

    language_workspace::Lease nested(Owner::FOCAL, 64);
    assert(nested.ok());
    assert(!nested.fresh());
    assert(nested.data() == focal.data());

    // A nested borrower may use only the extent already established by the
    // outer lease. Otherwise the tail was never initialized under that
    // ownership transaction.
    language_workspace::Lease growing_nested(Owner::FOCAL, 256);
    assert(!growing_nested.ok());

    language_workspace::Lease competing(Owner::TINYBASIC, 64);
    assert(!competing.ok());
    assert(language_workspace::active_owner() == Owner::FOCAL);
    assert(focal_data[0] == 0x61);
  }

  // Фоновая оптимизация не должна молча уничтожать сохранённую среду языка.
  {
    shared_memory::Lease cache;
    assert(!cache.acquire_cache(shared_memory::Arena::WORKSPACE,
                                shared_memory::Owner::CORE_TABLES, 512));
    assert(language_workspace::resident_owner() == Owner::FOCAL);
  }

  assert(language_workspace::active_owner() == Owner::NONE);
  assert(language_workspace::resident_owner() == Owner::FOCAL);
  {
    language_workspace::Lease focal(Owner::FOCAL, 128);
    assert(focal.ok());
    assert(!focal.fresh());
    assert(((u8*) focal.data())[0] == 0x61);
  }

  {
    language_workspace::Lease tiny(Owner::TINYBASIC, 128);
    assert(tiny.ok());
    assert(tiny.fresh());
    assert(((u8*) tiny.data())[0] == 0);
  }

  {
    language_workspace::Lease image(Owner::IMAGE_VIEWER, 1536);
    assert(image.ok());
    assert(image.fresh());
    assert(language_workspace::active_owner() == Owner::IMAGE_VIEWER);
    language_workspace::Lease usb(Owner::USB_DISK, 512);
    assert(!usb.ok());
  }
  // Одноразовый viewer, напротив, не закрепляет workspace после выхода.
  assert(language_workspace::resident_owner() == Owner::NONE);

  // Многошаговый fsput сохраняет staging-блок между командами, но после
  // end/cancel/error может пометить его одноразово даже изнутри живого lease.
  {
    language_workspace::Lease upload(Owner::TERMINAL_TRANSFER, 512);
    assert(upload.ok() && upload.fresh());
    ((u8*) upload.data())[0] = 0x5A;
  }
  {
    language_workspace::Lease upload(Owner::TERMINAL_TRANSFER, 512);
    assert(upload.ok() && !upload.fresh());
    assert(((u8*) upload.data())[0] == 0x5A);
    assert(language_workspace::discard(Owner::TERMINAL_TRANSFER));
    assert(language_workspace::resident_owner() ==
           Owner::TERMINAL_TRANSFER);
  }
  assert(language_workspace::resident_owner() == Owner::NONE);
  {
    language_workspace::Lease upload(Owner::TERMINAL_TRANSFER, 512);
    assert(upload.ok() && upload.fresh());
  }
  assert(language_workspace::discard(Owner::TERMINAL_TRANSFER));
  assert(language_workspace::resident_owner() == Owner::NONE);
  // Cleanup is deliberately idempotent; normal non-fsput commands call it
  // even when no upload was active.
  const shared_memory::Snapshot before_noop_discard =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  assert(language_workspace::discard(Owner::TERMINAL_TRANSFER));
  const shared_memory::Snapshot after_noop_discard =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  assert(after_noop_discard.invalid_failures ==
         before_noop_discard.invalid_failures);

  language_workspace::Lease oversized(Owner::USB_DISK, language_workspace::SIZE + 1);
  assert(!oversized.ok());
  language_workspace::Lease empty_runtime(Owner::USB_DISK, 0);
  assert(!empty_runtime.ok());

  assert(shared_scratch::current_owner() == shared_scratch::Owner::NONE);
  {
    shared_scratch::Lease view(shared_scratch::Owner::EXPLORER_VIEW, 100);
    assert(view.ok());
    assert(view.size() == 100);
    assert(shared_scratch::current_owner() == shared_scratch::Owner::EXPLORER_VIEW);

    shared_scratch::Lease competing(shared_scratch::Owner::PROGRAM_STORE_RENAME, 80);
    assert(!competing.ok());
    assert(shared_scratch::current_owner() == shared_scratch::Owner::EXPLORER_VIEW);
  }
  assert(shared_scratch::current_owner() == shared_scratch::Owner::NONE);

  {
    shared_scratch::Lease full(shared_scratch::Owner::VFAT_COMMIT, shared_scratch::SIZE);
    assert(full.ok());
    assert(full.size() == shared_scratch::SIZE);
  }
  {
    shared_scratch::Lease cache;
    assert(cache.acquire(shared_scratch::Owner::USB_CACHE,
                         shared_scratch::SIZE));
    assert(cache.acquire(shared_scratch::Owner::USB_CACHE, 512));
    assert(!cache.acquire(shared_scratch::Owner::USB_CACHE, 0));
    assert(!cache.acquire(shared_scratch::Owner::USB_CACHE,
                          shared_scratch::SIZE + 1));
    cache.reset();
    assert(!cache.ok());
    assert(shared_scratch::current_owner() == shared_scratch::Owner::NONE);
    assert(cache.acquire(shared_scratch::Owner::VFAT_COMMIT, 512));
  }
  shared_scratch::Lease scratch_oversized(
    shared_scratch::Owner::VFAT_COMMIT,
    shared_scratch::SIZE + 1
  );
  assert(!scratch_oversized.ok());
  shared_scratch::Lease empty_scratch(shared_scratch::Owner::VFAT_COMMIT, 0);
  assert(!empty_scratch.ok());

  assert(exclusive_buffer::current_owner() == exclusive_buffer::Owner::NONE);
  assert(exclusive_buffer::SIZE == MK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE);
  assert(exclusive_buffer::acquire(exclusive_buffer::Owner::DISPLAY_FONT, 1536));
  assert(exclusive_buffer::data(exclusive_buffer::Owner::DISPLAY_FONT) != NULL);
  assert(!exclusive_buffer::acquire(exclusive_buffer::Owner::USB_CACHE, 512));
  assert(exclusive_buffer::acquire(exclusive_buffer::Owner::DISPLAY_FONT, 1024));
  assert(!exclusive_buffer::acquire(
    exclusive_buffer::Owner::DISPLAY_FONT,
    exclusive_buffer::SIZE + 1
  ));
  assert(!exclusive_buffer::acquire(
    exclusive_buffer::Owner::DISPLAY_FONT, 0
  ));
  exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  assert(exclusive_buffer::current_owner() == exclusive_buffer::Owner::NONE);
  assert(exclusive_buffer::acquire(exclusive_buffer::Owner::USB_CACHE, exclusive_buffer::SIZE));
  exclusive_buffer::release(exclusive_buffer::Owner::USB_CACHE);

  // Все три прежних API теперь являются фасадами одного диспетчера.
  assert(shared_memory::capacity(shared_memory::Arena::WORKSPACE) ==
         language_workspace::SIZE);
  assert(shared_memory::capacity(shared_memory::Arena::SCRATCH) ==
         shared_scratch::SIZE);
  assert(shared_memory::capacity(shared_memory::Arena::BULK) ==
         exclusive_buffer::SIZE);

  shared_memory::reset_statistics();
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 512);
    assert(cache.ok() && cache.fresh());
    assert(shared_memory::contains(shared_memory::Arena::WORKSPACE,
                                   cache.data(), cache.size()));
    ReclaimProbe probe = {false, nullptr, false, nullptr, false, false};
    active_reclaim_probe = &probe;
    assert(cache.set_evictable(releasing_reclaim_probe));

    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::FOCAL, 256);
    assert(probe.called);
    assert(!cache.ok());
    assert(foreground.ok() && foreground.fresh());
    assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) ==
           shared_memory::Owner::FOCAL);
    active_reclaim_probe = nullptr;
  }
  const shared_memory::Snapshot workspace =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  assert(workspace.reclaim_attempts == 1);
  assert(workspace.reclaims == 1);
  assert(workspace.reclaim_failures == 0);
  assert(workspace.high_water == 512);
  assert(workspace.acquisitions == 2);

  // KEEP не разрешает конкуренту продолжить и не меняет исходную аренду.
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 64);
    assert(cache.ok());
    ReclaimProbe probe = {false, nullptr, false, nullptr, false, false};
    active_reclaim_probe = &probe;
    assert(cache.set_evictable(rejecting_reclaim_probe));
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 64);
    assert(probe.called && !foreground.ok() && cache.ok());
    active_reclaim_probe = nullptr;
  }

  // Только policy-помеченный cache может стать вытесняемым.
  {
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::FOCAL, 64);
    assert(foreground.ok());
    assert(!foreground.set_evictable(releasing_reclaim_probe));
  }

  // Callback не получает Lease и не может повторно захватить арену; после его
  // RELEASE менеджер сам отзывает ровно зарегистрированный cache Lease.
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 64);
    shared_memory::Lease attempted;
    shared_memory::Lease attempted_other;
    assert(cache.ok());
    ReclaimProbe probe = {
      false, &attempted, false, &attempted_other, false, false
    };
    active_reclaim_probe = &probe;
    assert(cache.set_evictable(reentrant_reclaim_probe));
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 64);
    assert(probe.called && !probe.reacquired && !attempted.ok());
    assert(!probe.reacquired_other && !attempted_other.ok());
    assert(!probe.discarded_resident);
    assert(!cache.ok() && foreground.ok());
    active_reclaim_probe = nullptr;
  }

  // При расширении сохранённой области того же владельца новая часть также
  // гарантированно обнулена, хотя все 8 КиБ больше не чистятся без нужды.
  {
    shared_memory::Lease small(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::TINYBASIC, 32);
    assert(small.ok() && small.fresh());
    small.data()[31] = 0xA5;
  }
  {
    shared_memory::Lease larger(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::TINYBASIC, 64);
    assert(larger.ok() && !larger.fresh());
    assert(larger.data()[31] == 0xA5);
    for(usize index = 32; index < 64; index++) {
      assert(larger.data()[index] == 0);
    }
  }

  // ResidentToken связывает commit не только с owner/size, но и с конкретной
  // завершённой транзакцией. Повторный acquire делает старый token непригодным.
  const shared_memory::ResidentToken stale_token =
      shared_memory::resident_token(shared_memory::Arena::WORKSPACE);
  assert(stale_token.valid() &&
         stale_token.owner() == shared_memory::Owner::TINYBASIC &&
         stale_token.size() == 64);
  {
    shared_memory::Lease tiny(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::TINYBASIC, 64);
    assert(tiny.ok() && !tiny.fresh());
    tiny.data()[0] = 0x42;
    assert(!shared_memory::resident_token(
        shared_memory::Arena::WORKSPACE).valid());
  }
  const shared_memory::ResidentToken current_token =
      shared_memory::resident_token(shared_memory::Arena::WORKSPACE);
  assert(current_token.valid() &&
         current_token.epoch() != stale_token.epoch());
  assert(!shared_memory::commit_resident_handoff(stale_token));
  assert(shared_memory::resident_owner(shared_memory::Arena::WORKSPACE) ==
         shared_memory::Owner::TINYBASIC);
  assert(shared_memory::commit_resident_handoff(current_token));
  assert(shared_memory::resident_owner(shared_memory::Arena::WORKSPACE) ==
         shared_memory::Owner::NONE);
  {
    shared_memory::Lease tiny(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::TINYBASIC, 64);
    assert(tiny.ok() && tiny.fresh() && tiny.data()[0] == 0);
  }
  assert(shared_memory::validate_invariants());

  // If BULK is busy, an opportunistic client must leave an inactive language
  // byte-for-byte resident. A foreground transition is still allowed to use
  // the historical clean-start fallback: swap is an acceleration, never a
  // new availability dependency.
  workspace_swap::discard();
  assert(shared_memory::discard_resident(
      shared_memory::Arena::WORKSPACE, shared_memory::Owner::TINYBASIC));
  {
    language_workspace::Lease focal(Owner::FOCAL, 256);
    assert(focal.ok() && focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      ((u8*) focal.data())[index] = (u8) (index ^ 0xA7U);
    }
  }
  assert(exclusive_buffer::acquire(exclusive_buffer::Owner::DISPLAY_FONT, 1));
  {
    shared_memory::Lease cache;
    assert(!workspace_swap::acquire(
        shared_memory::Owner::CORE_TABLES, 64,
        workspace_swap::AcquireMode::OPPORTUNISTIC, cache));
    assert(!cache.ok());
    assert(language_workspace::resident_owner() == Owner::FOCAL);
  }
  {
    language_workspace::Lease focal(Owner::FOCAL, 256);
    assert(focal.ok() && !focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      assert(((const u8*) focal.data())[index] == (u8) (index ^ 0xA7U));
    }
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 32);
    assert(viewer.ok() && viewer.fresh());
  }
  assert(language_workspace::resident_owner() == Owner::NONE);
  exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);

  assert(strcmp(shared_memory::arena_name(
             shared_memory::Arena::WORKSPACE), "workspace") == 0);
  assert(strcmp(shared_memory::owner_name(
             shared_memory::Owner::CORE_TABLES), "core-tables") == 0);

  // Реальный RAM-only swap: сжимаем сохранённую среду языка в уже существующую
  // BULK-арену, отдаём workspace viewer-у и восстанавливаем побайтно.
  workspace_swap::discard();
  workspace_swap::reset_statistics();
  {
    shared_memory::Lease clear_persistent(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::IMAGE_VIEWER, 1);
    assert(clear_persistent.ok());
  }
  static constexpr usize SWAP_RUNTIME_SIZE = 4152;
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
    memset(focal.data(), 0, focal.size());
    for(usize index = 0; index < focal.size(); index += 257) {
      ((u8*) focal.data())[index] = (u8) (index / 257U + 1U);
    }
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 1024);
    assert(viewer.ok() && viewer.fresh());
    // Restore cannot overwrite a live foreground owner. The complete image
    // remains in BULK and succeeds after that owner releases the workspace.
    language_workspace::Lease blocked_focal(Owner::FOCAL,
                                            SWAP_RUNTIME_SIZE);
    assert(!blocked_focal.ok());
    assert(workspace_swap::statistics().valid);
  }
  workspace_swap::Statistics swap = workspace_swap::statistics();
  assert(swap.valid && swap.compressed &&
         swap.owner == shared_memory::Owner::FOCAL &&
         swap.schema == 1 &&
         swap.raw_size == SWAP_RUNTIME_SIZE &&
         swap.stored_size < exclusive_buffer::SIZE);
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      const u8 expected = index % 257U == 0
          ? (u8) (index / 257U + 1U) : 0;
      assert(((const u8*) focal.data())[index] == expected);
    }
  }
  swap = workspace_swap::statistics();
  assert(!swap.valid && swap.captures == 1 && swap.restores == 1 &&
         swap.integrity_failures == 0);

  // Swap is only a cache: a real BULK client may reclaim it, after which the
  // existing fresh-runtime recovery path remains the source of correctness.
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 128);
    assert(viewer.ok());
  }
  assert(workspace_swap::statistics().valid);
  assert(exclusive_buffer::acquire(exclusive_buffer::Owner::DISPLAY_FONT, 1));
  exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  assert(!workspace_swap::statistics().valid);
  assert(workspace_swap::statistics().evictions == 1);
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
  }

  // Every byte of the envelope is covered by header CRC and rejected before
  // decoding. Each iteration rebuilds a valid image before the next fault.
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    memset(focal.data(), 0x33, focal.size());
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 128);
    assert(viewer.ok());
  }
  static constexpr usize SWAP_HEADER_SIZE = 28;
  u8* swap_bytes = nullptr;
  for(usize corrupt = 0; corrupt < SWAP_HEADER_SIZE; corrupt++) {
    assert(workspace_swap::statistics().valid);
    swap_bytes = (u8*) shared_memory::data(
        shared_memory::Arena::BULK,
        shared_memory::Owner::WORKSPACE_SWAP);
    assert(swap_bytes != nullptr);
    swap_bytes[corrupt] ^= (u8) (1U << (corrupt & 7U));
    const u32 header_failures_before =
        workspace_swap::statistics().integrity_failures;
    {
      language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
      assert(focal.ok() && focal.fresh());
      for(usize index = 0; index < focal.size(); index++) {
        assert(((const u8*) focal.data())[index] == 0);
      }
      memset(focal.data(), 0x33, focal.size());
    }
    assert(workspace_swap::statistics().integrity_failures ==
           header_failures_before + 1);
    if(corrupt + 1U < SWAP_HEADER_SIZE) {
      language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 128);
      assert(viewer.ok());
    }
  }

  // Payload CRC catches compressed-stream corruption before the decoder; raw
  // CRC independently validates the reconstructed runtime afterwards.
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    memset(focal.data(), 0, focal.size());
    for(usize index = 0; index < focal.size(); index += 127) {
      ((u8*) focal.data())[index] = (u8) (index + 7U);
    }
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 128);
    assert(viewer.ok());
  }
  swap = workspace_swap::statistics();
  assert(swap.valid && swap.compressed && swap.stored_size != 0);
  swap_bytes = (u8*) shared_memory::data(
      shared_memory::Arena::BULK,
      shared_memory::Owner::WORKSPACE_SWAP);
  assert(swap_bytes != nullptr);
  swap_bytes[SWAP_HEADER_SIZE + swap.stored_size / 2U] ^= 0x80;
  const u32 payload_failures_before =
      workspace_swap::statistics().integrity_failures;
  assert(!workspace_swap::statistics().valid);
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      assert(((const u8*) focal.data())[index] == 0);
    }
  }
  assert(workspace_swap::statistics().integrity_failures ==
         payload_failures_before + 1);

  // Incompressible but fitting data uses RAW rather than expanding through
  // ZX0; CRC and restoration semantics remain identical.
  static constexpr usize RAW_RUNTIME_SIZE = 512;
  {
    // Clear the previous persistent extent directly: using the language
    // facade here would correctly capture another swap image first.
    shared_memory::Lease viewer(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 1);
    assert(viewer.ok());
  }
  {
    language_workspace::Lease focal(Owner::FOCAL, RAW_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
    u32 random = 0x4D4B3631UL;
    for(usize index = 0; index < focal.size(); index++) {
      random ^= random << 13;
      random ^= random >> 17;
      random ^= random << 5;
      ((u8*) focal.data())[index] = (u8) random;
    }
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 1);
    assert(viewer.ok());
  }
  swap = workspace_swap::statistics();
  assert(swap.valid && !swap.compressed &&
         swap.raw_size == RAW_RUNTIME_SIZE &&
         swap.stored_size == RAW_RUNTIME_SIZE);
  {
    language_workspace::Lease focal(Owner::FOCAL, RAW_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    u32 random = 0x4D4B3631UL;
    for(usize index = 0; index < focal.size(); index++) {
      random ^= random << 13;
      random ^= random >> 17;
      random ^= random << 5;
      assert(((const u8*) focal.data())[index] == (u8) random);
    }
  }

  // A semantically wrong schema with a correctly recomputed header CRC must
  // be rejected independently of the envelope checksum.
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 1);
    assert(viewer.ok());
  }
  swap = workspace_swap::statistics();
  assert(swap.valid);
  swap_bytes = (u8*) shared_memory::data(
      shared_memory::Arena::BULK,
      shared_memory::Owner::WORKSPACE_SWAP);
  assert(swap_bytes != nullptr);
  static constexpr usize SWAP_SCHEMA_OFFSET = 23;
  static constexpr usize SWAP_HEADER_CRC_OFFSET = 24;
  swap_bytes[SWAP_SCHEMA_OFFSET]++;
  reseal_swap_header(swap_bytes, SWAP_HEADER_CRC_OFFSET);
  const u32 schema_failures_before =
      workspace_swap::statistics().integrity_failures;
  {
    language_workspace::Lease focal(Owner::FOCAL, RAW_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
  }
  assert(workspace_swap::statistics().integrity_failures ==
         schema_failures_before + 1);

  // Raw CRC is an independent end-to-end guard after successful payload CRC
  // and decoding. Re-sealing the envelope proves this is not another header
  // CRC test.
  {
    language_workspace::Lease focal(Owner::FOCAL, RAW_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    u32 random = 0x72415753UL;
    for(usize index = 0; index < focal.size(); index++) {
      random ^= random << 13;
      random ^= random >> 17;
      random ^= random << 5;
      ((u8*) focal.data())[index] = (u8) random;
    }
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 1);
    assert(viewer.ok());
  }
  swap = workspace_swap::statistics();
  assert(swap.valid && !swap.compressed);
  swap_bytes = (u8*) shared_memory::data(
      shared_memory::Arena::BULK,
      shared_memory::Owner::WORKSPACE_SWAP);
  assert(swap_bytes != nullptr);
  static constexpr usize SWAP_RAW_CRC_OFFSET = 8;
  swap_bytes[SWAP_RAW_CRC_OFFSET] ^= 0x01;
  reseal_swap_header(swap_bytes, SWAP_HEADER_CRC_OFFSET);
  const u32 raw_failures_before =
      workspace_swap::statistics().integrity_failures;
  {
    language_workspace::Lease focal(Owner::FOCAL, RAW_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      assert(((const u8*) focal.data())[index] == 0);
    }
  }
  assert(workspace_swap::statistics().integrity_failures ==
         raw_failures_before + 1);

  // With one BULK slot, switching languages is a true exchange: the requested
  // image is restored while the departing resident is encoded into the space
  // just vacated by that image. Repeated FOCAL <-> BASIC transitions therefore
  // preserve both environments without a second payload-sized array.
  workspace_swap::discard();
  assert(shared_memory::discard_resident(
      shared_memory::Arena::WORKSPACE, shared_memory::Owner::FOCAL));
  workspace_swap::reset_statistics();
  if(shared_memory::BULK_ENABLED) {
    static constexpr usize PING_FOCAL_SIZE = 512;
    static constexpr usize PING_BASIC_SIZE = 384;
    {
      language_workspace::Lease focal(Owner::FOCAL, PING_FOCAL_SIZE);
      assert(focal.ok() && focal.fresh());
      for(usize index = 0; index < focal.size(); index++) {
        ((u8*) focal.data())[index] =
            (u8) ((index * 37U + 11U) ^ (index >> 1U));
      }
    }
    {
      language_workspace::Lease basic(Owner::TINYBASIC, PING_BASIC_SIZE);
      assert(basic.ok() && basic.fresh());
      for(usize index = 0; index < basic.size(); index++) {
        ((u8*) basic.data())[index] =
            (u8) ((index * 53U + 0xA7U) ^ (index >> 2U));
      }
    }
    swap = workspace_swap::statistics();
    assert(swap.valid && swap.owner == shared_memory::Owner::FOCAL &&
           swap.captures == 1 && swap.exchanges == 0);
    {
      language_workspace::Lease focal(Owner::FOCAL, PING_FOCAL_SIZE);
      assert(focal.ok() && !focal.fresh());
      for(usize index = 0; index < focal.size(); index++) {
        assert(((const u8*) focal.data())[index] ==
               (u8) ((index * 37U + 11U) ^ (index >> 1U)));
      }
    }
    swap = workspace_swap::statistics();
    assert(swap.valid && swap.owner == shared_memory::Owner::TINYBASIC &&
           swap.captures == 2 && swap.restores == 1 &&
           swap.exchange_attempts == 1 && swap.exchanges == 1 &&
           swap.exchange_fallbacks == 0);
    {
      language_workspace::Lease basic(Owner::TINYBASIC, PING_BASIC_SIZE);
      assert(basic.ok() && !basic.fresh());
      for(usize index = 0; index < basic.size(); index++) {
        assert(((const u8*) basic.data())[index] ==
               (u8) ((index * 53U + 0xA7U) ^ (index >> 2U)));
      }
    }
    swap = workspace_swap::statistics();
    assert(swap.valid && swap.owner == shared_memory::Owner::FOCAL &&
           swap.capture_attempts == 3 && swap.captures == 3 &&
           swap.restores == 2 && swap.exchange_attempts == 2 &&
           swap.exchanges == 2 && swap.exchange_fallbacks == 0);

    // If two incompressible images cannot coexist transiently, restoring the
    // requested image retains historical foreground semantics and records the
    // deliberate loss of the departing cache as an observable fallback.
    workspace_swap::discard();
    assert(shared_memory::discard_resident(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::TINYBASIC));
    workspace_swap::reset_statistics();
    const usize large_size =
        (shared_memory::BULK_SIZE - SWAP_HEADER_SIZE) / 2U + 32U;
    u32 focal_random = 0x13579BDFUL;
    {
      language_workspace::Lease focal(Owner::FOCAL, large_size);
      assert(focal.ok() && focal.fresh());
      for(usize index = 0; index < focal.size(); index++) {
        focal_random ^= focal_random << 13;
        focal_random ^= focal_random >> 17;
        focal_random ^= focal_random << 5;
        ((u8*) focal.data())[index] = (u8) focal_random;
      }
    }
    {
      language_workspace::Lease basic(Owner::TINYBASIC, large_size);
      assert(basic.ok() && basic.fresh());
      u32 basic_random = 0x2468ACE1UL;
      for(usize index = 0; index < basic.size(); index++) {
        basic_random ^= basic_random << 13;
        basic_random ^= basic_random >> 17;
        basic_random ^= basic_random << 5;
        ((u8*) basic.data())[index] = (u8) basic_random;
      }
    }
    swap = workspace_swap::statistics();
    assert(swap.valid && !swap.compressed &&
           swap.owner == shared_memory::Owner::FOCAL);
    {
      language_workspace::Lease focal(Owner::FOCAL, large_size);
      assert(focal.ok() && !focal.fresh());
      focal_random = 0x13579BDFUL;
      for(usize index = 0; index < focal.size(); index++) {
        focal_random ^= focal_random << 13;
        focal_random ^= focal_random >> 17;
        focal_random ^= focal_random << 5;
        assert(((const u8*) focal.data())[index] == (u8) focal_random);
      }
    }
    swap = workspace_swap::statistics();
    assert(!swap.valid && swap.captures == 1 && swap.restores == 1 &&
           swap.exchange_attempts == 1 && swap.exchanges == 0 &&
           swap.exchange_fallbacks == 1);
  }

  run_workspace_state_model();

  printf("memory_buffers_self_test: ok\n");
  return 0;
}
