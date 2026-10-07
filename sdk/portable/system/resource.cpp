#include "system_compat.hpp"
#include "language_resources.hpp"
namespace portable_system {
bool resource_read(void* raw, uint16_t offset, uint8_t* output, uint16_t length) {
  const auto* image = (const uint8_t*)raw;
  const uint16_t size = language_vm::resource_word(image + 14);
  if (offset > size || length > size - offset) return false;
  mk61_service_resource r = {};
  r.id = language_vm::resource_word(image + 24); r.offset = offset;
  r.revision = (uint32_t)language_vm::resource_word(image + 26) |
               ((uint32_t)language_vm::resource_word(image + 28) << 16);
  r.output = output; r.length = length;
  return call(MK61_SYS_RESOURCE_READ, 1, 0, 0, &r) != 0;
}
bool resource_print(const uint8_t* image, const uint8_t* recipe,
                    bool (*append)(void*, const char*, uint16_t, bool), void* context) {
  mk61_service_resource_stream r = {
    (uint32_t)language_vm::resource_word(image + 26) |
      ((uint32_t)language_vm::resource_word(image + 28) << 16),
    language_vm::resource_word(image + 24), language_vm::resource_word(image + 14),
    recipe, (uint16_t)(language_vm::resource_word(image + 8) - (recipe - image)),
    0, context, append
  };
  return call(MK61_SYS_RESOURCE_READ, 2, 0, 0, &r) != 0;
}
}
