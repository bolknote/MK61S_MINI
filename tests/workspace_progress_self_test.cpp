#include "workspace_swap.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace shared_memory;
using workspace_swap::AcquireMode;

static unsigned complete = 0;
static unsigned progress_calls = 0;
static Owner restored = Owner::NONE;
static Owner captured = Owner::NONE;
static u8 saved[WORKSPACE_SIZE], focal[128];
static bool observing = false;
static workspace_swap::Statistics prior{};
static std::vector<u8> prior_bytes;

static void remember() {
  prior = workspace_swap::statistics();
  prior_bytes.clear();
  if(prior.valid) {
    const auto* image = static_cast<const u8*>(data(Arena::BULK, Owner::WORKSPACE_SWAP));
    assert(image);
    // The canonical snapshot has a 28-byte header followed by stored_size bytes.
    prior_bytes.assign(image, image + 28 + prior.stored_size);
  }
}

void storage_io_process() {
  if(observing) return;
  observing = true;
  assert(validate_invariants());
  const Owner active = active_owner(Arena::WORKSPACE);
  if(active_owner(Arena::SCRATCH) == Owner::WORKSPACE_SWAP) {
    ++progress_calls;
    // During planning the source is pinned and the old canonical backup is
    // unchanged. No bytes from emit or header commit are visible yet.
    assert(active == Owner::LANGUAGE_VM || active == Owner::FOCAL);
    assert(!std::memcmp(data(Arena::WORKSPACE, active),
        active == Owner::LANGUAGE_VM ? saved : focal,
        active == Owner::LANGUAGE_VM ? sizeof(saved) : sizeof(focal)));
    const auto image = workspace_swap::statistics();
    assert(image.valid == prior.valid);
    if(image.valid) {
      assert(image.owner == prior.owner && image.generation == prior.generation);
      assert(image.stored_size == prior.stored_size);
      assert(!std::memcmp(data(Arena::BULK, Owner::WORKSPACE_SWAP),
                          prior_bytes.data(), prior_bytes.size()));
    }
    Lease denied;
    assert(!workspace_swap::acquire(Owner::SETUP, 32, AcquireMode::REQUIRED, denied));
    assert(active_owner(Arena::WORKSPACE) == active);
    assert(workspace_swap::statistics().generation == image.generation);
  } else {
    ++complete;
    if(captured != Owner::NONE) {
      const auto image = workspace_swap::statistics();
      assert(image.valid && image.owner == captured && active == Owner::NONE);
    }
    if(restored != Owner::NONE) {
      assert(active == restored);
      assert(!std::memcmp(data(Arena::WORKSPACE, active),
          active == Owner::LANGUAGE_VM ? saved : focal,
          active == Owner::LANGUAGE_VM ? sizeof(saved) : sizeof(focal)));
    }
  }
  observing = false;
}

static void reset_probe() {
  captured = restored = Owner::NONE;
}

int main() {
  assert(prepare_retained_buffers());
  for(usize i = 0; i < sizeof(saved); ++i) saved[i] = (u8) (i % 37);
  std::memset(focal, 0x61, sizeof(focal));
  {
    Lease vm;
    remember();
    assert(workspace_swap::acquire(Owner::LANGUAGE_VM, sizeof(saved), AcquireMode::REQUIRED, vm));
    std::memcpy(vm.data(), saved, sizeof(saved));
  }
  const unsigned first = complete;
  {
    Lease core;
    remember();
    captured = Owner::LANGUAGE_VM;
    assert(workspace_swap::acquire(Owner::CORE_TABLES, 1024, AcquireMode::OPPORTUNISTIC, core));
    assert(complete == first + 1);
    reset_probe();
  }
  {
    Lease vm;
    remember();
    restored = Owner::LANGUAGE_VM;
    assert(workspace_swap::acquire(Owner::LANGUAGE_VM, sizeof(saved), AcquireMode::REQUIRED, vm));
    assert(complete == first + 2 && !vm.fresh());
    reset_probe();
    const unsigned before = complete;
    Lease nested;
    assert(workspace_swap::acquire(Owner::LANGUAGE_VM, sizeof(saved), AcquireMode::REQUIRED, nested));
    assert(nested.data() == vm.data() && complete == before);
    Lease invalid;
    assert(!workspace_swap::acquire(Owner::NONE, 1, AcquireMode::REQUIRED, invalid));
    assert(complete == before);
  }
  {
    Lease compiler;
    remember();
    captured = Owner::LANGUAGE_VM;
    assert(workspace_swap::acquire(Owner::FOCAL, sizeof(focal), AcquireMode::REQUIRED, compiler));
    reset_probe();
    std::memcpy(compiler.data(), focal, sizeof(focal));
  }
  {
    Lease vm;
    remember();
    restored = Owner::LANGUAGE_VM;
    assert(workspace_swap::acquire(Owner::LANGUAGE_VM, sizeof(saved), AcquireMode::REQUIRED, vm));
    reset_probe();
    assert(workspace_swap::statistics().owner == Owner::FOCAL);
  }
  {
    Lease compiler;
    remember();
    restored = Owner::FOCAL;
    assert(workspace_swap::acquire(Owner::FOCAL, sizeof(focal), AcquireMode::REQUIRED, compiler));
    reset_probe();
    assert(!compiler.fresh());
    Lease denied;
    restored = Owner::FOCAL;
    assert(!workspace_swap::acquire(Owner::LANGUAGE_VM, sizeof(saved), AcquireMode::REQUIRED, denied));
    reset_probe();
  }
  assert(progress_calls > 0 && complete >= 6 && validate_invariants());
  std::printf("workspace planning progress PASS: %u pinned-source/unchanged-backup/"
              "reentry observations, %u complete-state checkpoints\n", progress_calls, complete);
}
