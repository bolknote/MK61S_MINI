#include "../code/shared_memory.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace shared_memory;

int main() {
  // Match the ELF checker constants and the tight F401 USB-screen profile.
  static_assert(APP_MAX_SIZE == 20480 && STAGE_INDEX_SIZE == 2560,
                "update the APP memory ELF gate when allocator limits change");
  assert(capacity(Arena::OVERLAY) == 21728);
  Lease staging, app;
  assert(staging.acquire_cache(Arena::OVERLAY, Owner::VFAT_STAGE, STAGE_INDEX_SIZE));
  memset(staging.data(), 0x5A, staging.size());
  assert(app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 18624));
  memset(app.data(), 0xA5, app.size());
  assert(staging.data() + staging.size() <= app.data());
  for(usize i = 0; i < staging.size(); ++i) assert(staging.data()[i] == 0x5A);
  assert(validate_invariants());
  app.reset();
  // A future, larger System APP must fail, not overwrite its staging index.
  assert(!app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, 19200));
  for(usize i = 0; i < staging.size(); ++i) assert(staging.data()[i] == 0x5A);
  staging.reset();
  assert(app.acquire_cache(Arena::APP, Owner::LOADABLE_MODULE, APP_MAX_SIZE));
  assert(validate_invariants());
  puts("Qualified APP RAM: F401 System APP + full staging, overflow rejection PASS");
}
