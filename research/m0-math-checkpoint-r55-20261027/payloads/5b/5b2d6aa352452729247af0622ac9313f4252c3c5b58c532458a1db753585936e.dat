#ifndef MK61_BASIC_GRAPHICS_PROTOCOL_HPP
#define MK61_BASIC_GRAPHICS_PROTOCOL_HPP
#include <stdint.h>

namespace basic_graphics {
// Synchronous data-only requests. No caller-owned pointer is retained.
enum class Operation : uint8_t {
  WIDTH,
  HEIGHT,
  RESET,
  END,
  CHECK,
  CLEAR,
  SHOW,
  PSET,
  POINT,
  LINE,
  BOX,
  CIRCLE,
  TEXT,
  TEXT_ROWS,
  SUSPEND,
  RESUME,
  ACTIVE,
  TEXT_FLOW,
  SAVE_PRINT,
  RESTORE_PRINT
};
enum class Result : uint8_t { OK, UNAVAILABLE, FULL, ARGUMENT, CHANGED, IO };
struct Request {
  double args[6];
  const char *text;
  double value;
  uint16_t length;
  uint8_t count;
  Operation operation;
};
static_assert(sizeof(Request) == 72, "graphics request ABI changed");
struct PrintPosition {
  double x, y;
  bool positioned, owns_context;
};
constexpr uint8_t minimum(Operation op) {
  return op == Operation::PSET || op == Operation::POINT || op == Operation::TEXT ? 2
         : op == Operation::LINE || op == Operation::BOX                          ? 4
         : op == Operation::CIRCLE                                                ? 3
                                                                                  : 0;
}
constexpr uint8_t maximum(Operation op) {
  return op == Operation::PSET     ? 3
         : op == Operation::LINE   ? 5
         : op == Operation::BOX    ? 6
         : op == Operation::CIRCLE ? 4
                                   : minimum(op);
}
} // namespace basic_graphics
#endif
