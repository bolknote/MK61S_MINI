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

// Разбирает один заключённый в кавычки аргумент print и выводит его без
// неявного перевода строки. Заполнители регистров принимают и {R0}..{RF},
// и {0}..{F}. Необязательные форматы :m и :e выбирают старшую цифру мантиссы
// или абсолютное значение порядка.
Result render(const char* args, bool expanded,
              WriteByte write_byte, WriteValue write_value,
              void* user_data = nullptr);
const char* error_message(Error error);

} // пространство имён m61_print

#endif
