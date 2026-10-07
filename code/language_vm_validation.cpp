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
  *p->validated = {VALIDATED_MAGIC, v.size, v.code, v.source_size, v.end, (uint8_t)v.lines, v.stack,
                   (uint8_t)((v.expression ? 1 : 0) | (v.requires_rf ? 2 : 0) | (r.image[7] & 4)), v.language};
  if (p->action == OverlayAction::START) {
    initialize_validated_state(r, *p->validated, *p->state);
  }
  return 1;
}
}  // namespace language_vm
