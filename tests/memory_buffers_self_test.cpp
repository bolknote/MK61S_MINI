#include "../code/language_workspace.hpp"
#include "../code/shared_scratch.hpp"

#include <assert.h>
#include <stdio.h>

int main(void) {
  using language_workspace::Owner;

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

    language_workspace::Lease competing(Owner::TINYBASIC, 64);
    assert(!competing.ok());
    assert(language_workspace::active_owner() == Owner::FOCAL);
    assert(focal_data[0] == 0x61);
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
  shared_scratch::Lease scratch_oversized(
    shared_scratch::Owner::VFAT_COMMIT,
    shared_scratch::SIZE + 1
  );
  assert(!scratch_oversized.ok());
  shared_scratch::Lease empty_scratch(shared_scratch::Owner::VFAT_COMMIT, 0);
  assert(!empty_scratch.ok());

  printf("memory_buffers_self_test: ok\n");
  return 0;
}
