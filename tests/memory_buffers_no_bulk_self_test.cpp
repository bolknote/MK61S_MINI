#include "../code/exclusive_buffer.hpp"
#include "../code/language_workspace.hpp"
#include "../code/shared_memory.hpp"
#include "../code/workspace_swap.hpp"

#include <assert.h>
#include <stdio.h>

int main(void) {
  static_assert(!MK61_EXCLUSIVE_BUFFER_ENABLED,
                "plain LCD profile must not allocate BULK");
  static_assert(!shared_memory::BULK_ENABLED,
                "plain LCD profile unexpectedly enables BULK");

  assert(!shared_memory::enabled(shared_memory::Arena::BULK));
  assert(exclusive_buffer::current_owner() ==
         exclusive_buffer::Owner::NONE);
  assert(!exclusive_buffer::acquire(
      exclusive_buffer::Owner::DISPLAY_FONT, 1));
  assert(exclusive_buffer::data(
      exclusive_buffer::Owner::DISPLAY_FONT) == nullptr);

  {
    language_workspace::Lease focal(
        language_workspace::Owner::FOCAL, 256);
    assert(focal.ok() && focal.fresh());
    ((u8*) focal.data())[0] = 0x61;
  }
  {
    language_workspace::Lease viewer(
        language_workspace::Owner::MARKDOWN_VIEWER, 128);
    assert(viewer.ok() && viewer.fresh());
  }
  // Without a physical BULK arena there is deliberately no automatic swap;
  // the established clean-runtime fallback remains deterministic.
  const workspace_swap::Statistics swap = workspace_swap::statistics();
  assert(!swap.enabled && !swap.valid && swap.capture_attempts == 0);
  {
    language_workspace::Lease focal(
        language_workspace::Owner::FOCAL, 256);
    assert(focal.ok() && focal.fresh());
    assert(((const u8*) focal.data())[0] == 0);
  }

  printf("memory_buffers_no_bulk_self_test: ok\n");
  return 0;
}
