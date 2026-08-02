#include "../code/language_workspace.hpp"
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
  shared_memory::Lease* lease;
  bool called;
};

static bool reclaim_probe(void* context) {
  ReclaimProbe& probe = *(ReclaimProbe*) context;
  probe.called = true;
  probe.lease->reset();
  return true;
}

static bool rejecting_reclaim_probe(void* context) {
  ReclaimProbe& probe = *(ReclaimProbe*) context;
  probe.called = true;
  return false;
}

static bool lying_reclaim_probe(void* context) {
  ReclaimProbe& probe = *(ReclaimProbe*) context;
  probe.called = true;
  return true;
}

struct ReentrantProbe {
  shared_memory::Lease* old_lease;
  shared_memory::Lease* attempted_lease;
  bool called;
  bool reacquired;
};

static bool reentrant_reclaim_probe(void* context) {
  ReentrantProbe& probe = *(ReentrantProbe*) context;
  probe.called = true;
  probe.old_lease->reset();
  probe.reacquired = probe.attempted_lease->acquire(
      shared_memory::Arena::WORKSPACE,
      shared_memory::Owner::CORE_TABLES, 64);
  return true;
}

int main(void) {
  using language_workspace::Owner;

  static_assert(MK61_EXCLUSIVE_BUFFER_ENABLED,
                "graphical build must provide the exclusive buffer");
  static_assert(exclusive_buffer::SIZE == MK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE,
                "exclusive buffer size differs from the MCU policy");

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
    ReclaimProbe probe = {&cache, false};
    assert(cache.set_reclaimer(reclaim_probe, &probe));

    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::FOCAL, 256);
    assert(probe.called);
    assert(!cache.ok());
    assert(foreground.ok() && foreground.fresh());
    assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) ==
           shared_memory::Owner::FOCAL);
  }
  const shared_memory::Snapshot workspace =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  assert(workspace.reclaim_attempts == 1);
  assert(workspace.reclaims == 1);
  assert(workspace.reclaim_failures == 0);
  assert(workspace.high_water == 512);
  assert(workspace.acquisitions == 2);

  // Отказавший callback не разрешает конкуренту продолжить, даже если он был
  // вызван: подтверждение и фактическое освобождение проверяются раздельно.
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 64);
    assert(cache.ok());
    ReclaimProbe probe = {&cache, false};
    assert(cache.set_reclaimer(rejecting_reclaim_probe, &probe));
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 64);
    assert(probe.called && !foreground.ok() && cache.ok());
  }

  // A callback cannot merely claim success: the old lease must actually be
  // gone before ownership is transferred.
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 64);
    assert(cache.ok());
    ReclaimProbe probe = {&cache, false};
    assert(cache.set_reclaimer(lying_reclaim_probe, &probe));
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 64);
    assert(probe.called && !foreground.ok() && cache.ok());
  }

  // The callback may release its lease but cannot re-enter the same arena
  // before returning. The original foreground acquisition then completes.
  {
    shared_memory::Lease cache(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::CORE_TABLES, 64);
    shared_memory::Lease attempted;
    assert(cache.ok());
    ReentrantProbe probe = {&cache, &attempted, false, false};
    assert(cache.set_reclaimer(reentrant_reclaim_probe, &probe));
    shared_memory::Lease foreground(
        shared_memory::Arena::WORKSPACE,
        shared_memory::Owner::MARKDOWN_VIEWER, 64);
    assert(probe.called && !probe.reacquired && !attempted.ok());
    assert(!cache.ok() && foreground.ok());
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
  }
  workspace_swap::Statistics swap = workspace_swap::statistics();
  assert(swap.valid && swap.compressed &&
         swap.owner == shared_memory::Owner::FOCAL &&
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

  // A corrupt header is rejected before decoding and leaves a clean runtime.
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && !focal.fresh());
    memset(focal.data(), 0x33, focal.size());
  }
  {
    language_workspace::Lease viewer(Owner::MARKDOWN_VIEWER, 128);
    assert(viewer.ok());
  }
  assert(workspace_swap::statistics().valid);
  u8* swap_bytes = (u8*) shared_memory::data(
      shared_memory::Arena::BULK,
      shared_memory::Owner::WORKSPACE_SWAP);
  assert(swap_bytes != nullptr);
  swap_bytes[0] ^= 0x01;
  const u32 header_failures_before =
      workspace_swap::statistics().integrity_failures;
  {
    language_workspace::Lease focal(Owner::FOCAL, SWAP_RUNTIME_SIZE);
    assert(focal.ok() && focal.fresh());
    for(usize index = 0; index < focal.size(); index++) {
      assert(((const u8*) focal.data())[index] == 0);
    }
  }
  assert(workspace_swap::statistics().integrity_failures ==
         header_failures_before + 1);

  // Corruption after a valid header is caught by decode and/or data CRC.
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
  static constexpr usize SWAP_HEADER_SIZE = 24;
  swap_bytes[SWAP_HEADER_SIZE + swap.stored_size / 2U] ^= 0x80;
  const u32 payload_failures_before =
      workspace_swap::statistics().integrity_failures;
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

  printf("memory_buffers_self_test: ok\n");
  return 0;
}
