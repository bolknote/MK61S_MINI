#include "language_vm_abi.hpp"

namespace language_vm {
uint32_t validate_execution(OverlayRequest* p) {
  if (!execution_compatible(p) ||
      (p->action != OverlayAction::START && p->action != OverlayAction::EXPRESSION))
    return 0;
  auto& r = *p->execution;
  *p->validated = {};
  View v;
  r.result = {inspect(r.image, (uint16_t)r.image_size, v), 0, 0, 0};
  if (r.result.error != Error::NONE) return 1;
  if (v.language != p->state->language ||
      v.expression != (p->action == OverlayAction::EXPRESSION)) {
    r.result.error = Error::INVALID_IMAGE;
    return 1;
  }
  *p->validated = {VALIDATED_MAGIC, v.size, v.code, v.lines, v.source_size, v.stack,
                   (uint8_t)((v.expression ? 1 : 0) | (v.requires_rf ? 2 : 0)), v.language, 0};
  if (p->action == OverlayAction::START) {
    auto& s = *p->state;
    s = {}; s.language = v.language; s.array_count = (uint16_t)r.array_count;
    if (v.language == Language::BASIC) {
      const uint16_t source_limit = (uint16_t)((3584 - v.source_size) / 2 + 1);
      if (s.array_count > source_limit) s.array_count = source_limit;
    }
  }
  return 1;
}
}  // namespace language_vm
