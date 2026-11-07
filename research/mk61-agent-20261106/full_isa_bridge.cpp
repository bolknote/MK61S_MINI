// Private research ABI: the product's unmodified microcode core remains oracle.
#include "core_bridge.cpp"

extern "C" {
int fi_reset(unsigned angle) {
  if (mk_reset() != 0) return -1;
  if (angle < 10 || angle > 12) return -1;
  MK61Emu_SetAngleUnit(static_cast<AngleUnit>(angle));
  return 0;
}
int fi_save(unsigned char *out, unsigned capacity) {
  if (capacity < core_61::CONTEXT_BUFFER_SIZE) return -1;
  core_61::ContextBuffer state;
  if (!core_61::save_context(state)) return -1;
  std::memcpy(out, state.bytes, core_61::CONTEXT_BUFFER_SIZE);
  return 0;
}
int fi_restore(const unsigned char *bytes, unsigned length) {
  if (length != core_61::CONTEXT_BUFFER_SIZE) return -1;
  core_61::ContextBuffer state;
  std::memcpy(state.bytes, bytes, length);
  return core_61::restore_context(state) ? 0 : -1;
}
}
