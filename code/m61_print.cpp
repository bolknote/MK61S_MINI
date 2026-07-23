#include "m61_print.hpp"

#include <string.h>

namespace m61_print {

static const char* skip_spaces(const char* p) {
  while(*p == ' ' || *p == '\t') p++;
  return p;
}

static i8 hex_digit(char c) {
  if(c >= '0' && c <= '9') return (i8) (c - '0');
  if(c >= 'a' && c <= 'f') return (i8) (c - 'a' + 10);
  if(c >= 'A' && c <= 'F') return (i8) (c - 'A' + 10);
  return -1;
}

static char upper(char c) {
  return (c >= 'a' && c <= 'z') ? (char) (c - 'a' + 'A') : c;
}

static bool at_end(const char* p) {
  p = skip_spaces(p);
  return *p == 0 || *p == '\r' || *p == '\n';
}

Control parse_control(const char* args) {
  if(args == nullptr) return Control::NONE;
  const char* p = skip_spaces(args);
  if(p[0] == 'o' && p[1] == 'f' && p[2] == 'f' && at_end(p + 3)) {
    return Control::OFF;
  }
  if(p[0] == 'o' && p[1] == 'n' && at_end(p + 2)) {
    return Control::ON;
  }
  return Control::NONE;
}

static Result parse_value(const char* begin, usize len, bool expanded,
                          ValueRef& value) {
  usize name_len = len;
  ValueFormat format = ValueFormat::INDICATOR;
  for(usize i = 0; i < len; i++) {
    if(begin[i] != ':') continue;
    if(name_len != len || i == 0 || i + 2 != len) {
      return {Error::INVALID_FORMAT};
    }
    name_len = i;
    switch(upper(begin[i + 1])) {
      case 'M': format = ValueFormat::MANTISSA_HEAD; break;
      case 'E': format = ValueFormat::ABS_EXPONENT; break;
      default: return {Error::INVALID_FORMAT};
    }
  }

  if(name_len == 1) {
    const char name = upper(begin[0]);
    switch(name) {
      case 'X': value = {ValueKind::STACK, (u8) StackValue::X, format}; return {Error::NONE};
      case 'Y': value = {ValueKind::STACK, (u8) StackValue::Y, format}; return {Error::NONE};
      case 'Z': value = {ValueKind::STACK, (u8) StackValue::Z, format}; return {Error::NONE};
      case 'T': value = {ValueKind::STACK, (u8) StackValue::T, format}; return {Error::NONE};
      default: break;
    }
    const i8 reg = hex_digit(name);
    if(reg >= 0) {
      if(reg == 15 && !expanded) return {Error::REGISTER_UNAVAILABLE};
      value = {ValueKind::REGISTER, (u8) reg, format};
      return {Error::NONE};
    }
  }

  if(name_len == 2) {
    const char first = upper(begin[0]);
    const char second = upper(begin[1]);
    if(first == 'X' && second == '1') {
      value = {ValueKind::STACK, (u8) StackValue::X1, format};
      return {Error::NONE};
    }
    if(first == 'X' && second == '2') {
      if(format != ValueFormat::INDICATOR) return {Error::INVALID_FORMAT};
      value = {ValueKind::STACK, (u8) StackValue::X2, format};
      return {Error::NONE};
    }
    if(first == 'R') {
      const i8 reg = hex_digit(second);
      if(reg < 0) return {Error::INVALID_PLACEHOLDER};
      if(reg == 15 && !expanded) return {Error::REGISTER_UNAVAILABLE};
      value = {ValueKind::REGISTER, (u8) reg, format};
      return {Error::NONE};
    }
  }
  return {Error::INVALID_PLACEHOLDER};
}

static Result parse(const char* args, bool expanded, bool emit,
                    WriteByte write_byte, WriteValue write_value,
                    void* user_data) {
  if(args == nullptr) return {Error::EXPECTED_STRING};
  const char* p = skip_spaces(args);
  if(*p != '"') return {Error::EXPECTED_STRING};
  p++;

  while(*p != 0 && *p != '\r' && *p != '\n') {
    if(*p == '"') {
      p = skip_spaces(p + 1);
      return *p == 0 ? Result{Error::NONE} : Result{Error::TRAILING_TEXT};
    }

    u8 byte = 0;
    if(*p == '\\') {
      p++;
      switch(*p) {
        case '\\': byte = '\\'; p++; break;
        case '"': byte = '"'; p++; break;
        case 'r': byte = '\r'; p++; break;
        case 'n': byte = '\n'; p++; break;
        case 't': byte = '\t'; p++; break;
        case 'b': byte = '\b'; p++; break;
        case 'x': {
          if(p[1] == 0 || p[2] == 0) return {Error::INVALID_ESCAPE};
          const i8 high = hex_digit(p[1]);
          const i8 low = hex_digit(p[2]);
          if(high < 0 || low < 0) return {Error::INVALID_ESCAPE};
          byte = (u8) (((u8) high << 4) | (u8) low);
          p += 3;
          break;
        }
        default:
          return {Error::INVALID_ESCAPE};
      }
      if(emit && (write_byte == nullptr || !write_byte(byte, user_data))) {
        return {Error::OUTPUT_FAILED};
      }
      continue;
    }

    if(*p == '{') {
      if(p[1] == '{') {
        if(emit && (write_byte == nullptr || !write_byte('{', user_data))) {
          return {Error::OUTPUT_FAILED};
        }
        p += 2;
        continue;
      }
      const char* name = p + 1;
      const char* end = strchr(name, '}');
      if(end == nullptr) return {Error::INVALID_PLACEHOLDER};
      ValueRef value = {};
      const Result parsed = parse_value(name, (usize) (end - name), expanded, value);
      if(!parsed.ok()) return parsed;
      if(emit && (write_value == nullptr || !write_value(value, user_data))) {
        return {Error::OUTPUT_FAILED};
      }
      p = end + 1;
      continue;
    }

    if(*p == '}') {
      if(p[1] != '}') return {Error::INVALID_PLACEHOLDER};
      if(emit && (write_byte == nullptr || !write_byte('}', user_data))) {
        return {Error::OUTPUT_FAILED};
      }
      p += 2;
      continue;
    }

    byte = (u8) *p++;
    if(emit && (write_byte == nullptr || !write_byte(byte, user_data))) {
      return {Error::OUTPUT_FAILED};
    }
  }
  return {Error::UNTERMINATED_STRING};
}

Result render(const char* args, bool expanded,
              WriteByte write_byte, WriteValue write_value,
              void* user_data) {
  // Сначала проверяем всё выражение, чтобы ошибочный суффикс не оставил
  // в терминале частично напечатанное сообщение.
  const Result validated = parse(args, expanded, false, nullptr, nullptr, nullptr);
  if(!validated.ok()) return validated;
  return parse(args, expanded, true, write_byte, write_value, user_data);
}

const char* error_message(Error error) {
  switch(error) {
    case Error::NONE: return "";
    case Error::EXPECTED_STRING: return "expected one quoted string";
    case Error::TRAILING_TEXT: return "unexpected text after quoted string";
    case Error::UNTERMINATED_STRING: return "unterminated quoted string";
    case Error::INVALID_ESCAPE: return "invalid escape sequence";
    case Error::INVALID_PLACEHOLDER: return "invalid register placeholder";
    case Error::INVALID_FORMAT: return "invalid register format (use :m or :e)";
    case Error::REGISTER_UNAVAILABLE: return "RF requires expanded mode";
    case Error::OUTPUT_FAILED: return "screen output failed";
  }
  return "print failed";
}

} // пространство имён m61_print
