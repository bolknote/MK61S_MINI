#ifndef TERMINAL_CORE_HPP
#define TERMINAL_CORE_HPP

#include "mk_math.hpp"
#include "rust_types.h"

#include <string.h>

namespace terminal_core {

static constexpr usize INPUT_CAPACITY = 240;
static constexpr usize MAX_INPUT_TEXT = INPUT_CAPACITY - 1;

inline bool input_can_append(usize length) {
  return length < MAX_INPUT_TEXT;
}

inline bool is_space(char c) {
  return c == ' ' || c == '\t';
}

inline bool is_end(char c) {
  return c == 0 || c == '\r' || c == '\n';
}

inline const char* skip_spaces(const char* p) {
  while(p != 0 && is_space(*p)) p++;
  return p;
}

inline bool at_end(const char* p) {
  p = skip_spaces(p);
  return p == 0 || is_end(*p);
}

inline int digit_value(char c, usize base) {
  int digit = -1;
  if(c >= '0' && c <= '9') digit = c - '0';
  else if(c >= 'a' && c <= 'f') digit = c - 'a' + 10;
  else if(c >= 'A' && c <= 'F') digit = c - 'A' + 10;
  return digit >= 0 && (usize) digit < base ? digit : -1;
}

inline bool parse_unsigned(const char*& p, usize base, usize maximum, usize& out) {
  if(base < 2 || base > 16) return false;
  p = skip_spaces(p);
  if(p == 0) return false;
  const char* begin = p;
  usize value = 0;
  while(true) {
    const int digit = digit_value(*p, base);
    if(digit < 0) break;
    if((usize) digit > maximum) return false;
    if(value > (maximum - (usize) digit) / base) return false;
    value = value * base + (usize) digit;
    p++;
  }
  if(p == begin || (!is_space(*p) && !is_end(*p))) return false;
  out = value;
  return true;
}

inline bool parse_single_unsigned(const char* p, usize base, usize maximum, usize& out) {
  return parse_unsigned(p, base, maximum, out) && at_end(p);
}

inline bool exact_confirmation(const char* line, char answer) {
  line = skip_spaces(line);
  if(line == 0 || (*line != answer && *line != (char) (answer - 'a' + 'A'))) return false;
  return at_end(line + 1);
}

// Parse the calculator's finite decimal input. Limiting significant source
// digits and exponent magnitude also prevents the libm-free parser from doing
// unbounded work on hostile input.
inline bool parse_decimal(const char*& p, double& out) {
  p = skip_spaces(p);
  if(p == 0) return false;
  const char* begin = p;
  if(*p == '+' || *p == '-') p++;

  usize digits = 0;
  bool any = false;
  while(*p >= '0' && *p <= '9') { any = true; digits++; p++; }
  if(*p == '.') {
    p++;
    while(*p >= '0' && *p <= '9') { any = true; digits++; p++; }
  }
  if(!any || digits > 18) return false;

  if(*p == 'e' || *p == 'E') {
    p++;
    if(*p == '+' || *p == '-') p++;
    const char* exponent_begin = p;
    usize exponent = 0;
    while(*p >= '0' && *p <= '9') {
      const usize digit = (usize) (*p++ - '0');
      if(exponent > (99 - digit) / 10) return false;
      exponent = exponent * 10 + digit;
    }
    if(p == exponent_begin) return false;
  }

  const char* parsed_end = begin;
  const double value = mk_math::strtod(begin, &parsed_end);
  if(parsed_end != p || mk_math::is_nan(value) || mk_math::is_inf(value)) return false;
  out = value;
  return true;
}

inline bool parse_single_decimal(const char* p, double& out) {
  return parse_decimal(p, out) && at_end(p);
}

inline isize find_mnemonic(const char* isa, const char* token, usize token_len) {
  if(isa == 0 || token == 0 || token_len == 0) return -1;
  usize opcode = 0;
  const char* item = isa;
  while(true) {
    const char* end = item;
    while(*end != 0 && *end != ',') end++;
    const usize item_len = (usize) (end - item);
    if(item_len == token_len && memcmp(item, token, token_len) == 0) return (isize) opcode;
    if(*end == 0) break;
    item = end + 1;
    opcode++;
  }
  return -1;
}

enum class AssemblyError : u8 {
  NONE,
  EMPTY,
  BAD_ADDRESS,
  UNKNOWN_MNEMONIC,
  TOO_LONG
};

struct Assembly {
  usize address;
  usize count;
  u8 opcodes[112];
  AssemblyError error;
  const char* error_at;
};

inline bool token_is_decimal_address(const char* begin, const char* end) {
  if(end - begin != 4) return false;
  for(const char* p = begin; p < end; p++) if(*p < '0' || *p > '9') return false;
  return true;
}

inline Assembly parse_assembly(const char* args, isize current_address, const char* isa, usize max_steps) {
  Assembly result = {};
  result.error = AssemblyError::NONE;
  const char* p = skip_spaces(args);
  if(p == 0 || is_end(*p)) {
    result.error = AssemblyError::EMPTY;
    result.error_at = p;
    return result;
  }

  const char* first = p;
  while(!is_space(*p) && !is_end(*p)) p++;
  if(token_is_decimal_address(first, p)) {
    usize address = 0;
    for(const char* q = first; q < p; q++) address = address * 10 + (usize) (*q - '0');
    if(address >= max_steps) {
      result.error = AssemblyError::BAD_ADDRESS;
      result.error_at = first;
      return result;
    }
    result.address = address;
    p = skip_spaces(p);
  } else {
    if(current_address < 0 || (usize) current_address >= max_steps) {
      result.error = AssemblyError::BAD_ADDRESS;
      result.error_at = first;
      return result;
    }
    result.address = (usize) current_address;
    p = first;
  }

  while(!is_end(*p)) {
    p = skip_spaces(p);
    if(is_end(*p)) break;
    const char* token = p;
    while(!is_space(*p) && !is_end(*p)) p++;
    const isize opcode = find_mnemonic(isa, token, (usize) (p - token));
    if(opcode < 0 || opcode > 255) {
      result.error = AssemblyError::UNKNOWN_MNEMONIC;
      result.error_at = token;
      return result;
    }
    if(result.address + result.count >= max_steps || result.count >= sizeof(result.opcodes)) {
      result.error = AssemblyError::TOO_LONG;
      result.error_at = token;
      return result;
    }
    result.opcodes[result.count++] = (u8) opcode;
  }

  if(result.count == 0) {
    result.error = AssemblyError::EMPTY;
    result.error_at = p;
  }
  return result;
}

} // namespace terminal_core

#endif
