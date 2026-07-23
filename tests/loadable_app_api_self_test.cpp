#include <assert.h>
#include <string.h>

#include "loadable_app_api.hpp"

int main(void) {
  using namespace loadable_app;

  static_assert(API_VERSION == 1, "APP API version changed unexpectedly");
  static_assert(KEY_DIGIT_9 - KEY_DIGIT_0 == 9,
                "digit keys must remain contiguous");
  static_assert(KEY_RAW_BASE > KEY_BACKWARD,
                "raw key range overlaps normalized keys");

  Api api = {};
  assert(!compatible(nullptr));
  assert(!compatible(&api));

  api.magic = API_MAGIC;
  api.version = API_VERSION;
  api.struct_size = (u16) sizeof(api);
  api.capabilities = CAP_TIME | CAP_TEXT_DISPLAY;
  assert(compatible(&api));

  api.magic ^= 1U;
  assert(!compatible(&api));
  api.magic = API_MAGIC;
  api.version++;
  assert(!compatible(&api));
  api.version = API_VERSION;
  api.struct_size = (u16) (sizeof(api) - 1U);
  assert(!compatible(&api));

  const u32 fake_address = 0x20001000UL;
  assert((u32) (uintptr_t) from_argument(fake_address) == fake_address);

  return 0;
}
