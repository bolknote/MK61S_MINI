#ifndef MK61_REGISTER_INIT_HPP
#define MK61_REGISTER_INIT_HPP

#include "terminal_core.hpp"

namespace mk61_register_init {

// Правая часть R<r>= разбирается отдельно от её применения. Поэтому ошибочная
// строка не успевает частично изменить кольцевую память или израсходовать число
// из потока энтропии.
enum class Kind : u8 {
  NUMBER,
  RANDOM,
  RAW
};

struct Value {
  Kind kind;
  double number;
  // Логический порядок тетрад регистра:
  // M0..M7, знак мантиссы, знак порядка, десятки и единицы порядка.
  u8 raw[12];
};

inline bool exact_word(const char* text, const char* word) {
  text = terminal_core::skip_spaces(text);
  if(text == nullptr || word == nullptr) return false;
  while(*word != 0) {
    if(*text++ != *word++) return false;
  }
  return terminal_core::at_end(text);
}

inline bool parse_raw(const char* text, u8 out[12]) {
  text = terminal_core::skip_spaces(text);
  if(text == nullptr || text[0] != 'r' || text[1] != 'a' || text[2] != 'w' ||
     !terminal_core::is_space(text[3])) return false;

  const char* cursor = terminal_core::skip_spaces(text + 3);
  for(usize index = 0; index < 12; index++) {
    const int digit = terminal_core::digit_value(cursor[index], 16);
    if(digit < 0) return false;
    out[index] = (u8) digit;
  }
  return terminal_core::at_end(cursor + 12);
}

inline bool parse(const char* text, Value& out) {
  Value parsed = {};
  if(exact_word(text, "random")) {
    parsed.kind = Kind::RANDOM;
  } else if(parse_raw(text, parsed.raw)) {
    parsed.kind = Kind::RAW;
  } else {
    if(!terminal_core::parse_single_decimal(text, parsed.number)) return false;
    parsed.kind = Kind::NUMBER;
  }
  out = parsed;
  return true;
}

} // namespace mk61_register_init

#endif
