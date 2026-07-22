#ifndef M61_PRINT_HPP
#define M61_PRINT_HPP

#include "rust_types.h"

namespace m61_print {

enum class ValueKind : u8 {
  STACK,
  REGISTER
};

enum class StackValue : u8 {
  X,
  Y,
  Z,
  T,
  X1,
  X2
};

enum class ValueFormat : u8 {
  INDICATOR,
  MANTISSA_HEAD,
  ABS_EXPONENT
};

struct ValueRef {
  ValueKind kind;
  u8 index;
  ValueFormat format = ValueFormat::INDICATOR;
};

enum class Error : u8 {
  NONE,
  EXPECTED_STRING,
  TRAILING_TEXT,
  UNTERMINATED_STRING,
  INVALID_ESCAPE,
  INVALID_PLACEHOLDER,
  INVALID_FORMAT,
  REGISTER_UNAVAILABLE,
  OUTPUT_FAILED
};

struct Result {
  Error error;
  bool ok(void) const { return error == Error::NONE; }
};

using WriteByte = bool (*)(u8 value, void* user_data);
using WriteValue = bool (*)(const ValueRef& value, void* user_data);

// Parses one quoted print argument and writes it without an implicit newline.
// Register placeholders accept both {R0}..{RF} and {0}..{F}. The optional
// :m and :e formats select the leading mantissa digit or absolute exponent.
Result render(const char* args, bool expanded,
              WriteByte write_byte, WriteValue write_value,
              void* user_data = nullptr);
const char* error_message(Error error);

} // namespace m61_print

#endif
