#ifndef MK61_BASIC_NATIVE_IO_HPP
#define MK61_BASIC_NATIVE_IO_HPP
#include "basic_graphics_protocol.hpp"
#include "language_bytecode.hpp"

namespace basic_graphics {
enum class NativeOperation : uint8_t { PRINT, GRAPH, ARGUMENTS, FLUSH };
// Native interpreter callbacks are strictly synchronous. The resident never
// retains source/workspace pointers or an address in an unloadable APP.
struct NativeRequest {
  const char *begin;
  const char *end;
  const char *error_at;
  char *output;
  uint8_t *cursor;
  uint8_t *row;
  bool *positioned;
  double *at_x;
  double *at_y;
  bool *pure;
  bool *pause_is_final;
  double *x_variable;
  bool (*evaluate)(NativeRequest &, const char *, const char *, double &, const char *&);
  void (*format)(double, char *, uint8_t);
  bool (*poll)(NativeRequest &);
  language_vm::Error error;
  NativeOperation operation;
  Operation primitive;
  bool execute, skip_domain;
};
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(NativeRequest) == 68, "native source service ARM ABI changed");
#endif
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
inline bool process_native(NativeRequest &request) {
  return portable_system::call(MK61_SERVICE_BASIC_FRONTEND, 0, 0, sizeof(request), &request) == 1;
}
#else
bool process_native(NativeRequest &request);
uint8_t native_text_rows();
int native_text_flow(const char *, uint16_t, uint8_t, uint8_t);
#endif
} // namespace basic_graphics
#endif
