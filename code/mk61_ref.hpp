#ifndef MK61_REF_HPP
#define MK61_REF_HPP

#include "rust_types.h"
#include "mk_math.hpp"

#include <string.h>

namespace mk61_ref {

enum class Kind : u8 {
  X,
  Y,
  Z,
  T,
  R
};

struct Ref {
  Kind kind;
  u8 reg;
};

static const char DISPLAY_SYMBOLS[16] = {
  '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', 'L', 'C', 'G', 'E', ' '
};

inline bool streq(const char* a, const char* b) {
  while(*a != 0 && *b != 0) {
    char ca = *a++;
    char cb = *b++;
    if(ca >= 'a' && ca <= 'z') ca = (char) (ca - 'a' + 'A');
    if(cb >= 'a' && cb <= 'z') cb = (char) (cb - 'a' + 'A');
    if(ca != cb) return false;
  }
  return *a == 0 && *b == 0;
}

inline int hex_digit(char symbol) {
  if(symbol >= '0' && symbol <= '9') return symbol - '0';
  if(symbol >= 'A' && symbol <= 'F') return symbol - 'A' + 10;
  if(symbol >= 'a' && symbol <= 'f') return symbol - 'a' + 10;
  return -1;
}

inline bool parse_name(const char* name, Ref& out) {
  if(name == NULL || name[0] == 0) return false;
  if(streq(name, "X")) {
    out.kind = Kind::X;
    out.reg = 0;
    return true;
  }
  if(streq(name, "Y")) {
    out.kind = Kind::Y;
    out.reg = 0;
    return true;
  }
  if(streq(name, "Z")) {
    out.kind = Kind::Z;
    out.reg = 0;
    return true;
  }
  if(streq(name, "T")) {
    out.kind = Kind::T;
    out.reg = 0;
    return true;
  }
  if((name[0] == 'R' || name[0] == 'r') && name[1] != 0 && name[2] == 0) {
    const int reg = hex_digit(name[1]);
    if(reg >= 0 && reg <= 0x0F) {
      out.kind = Kind::R;
      out.reg = (u8) reg;
      return true;
    }
  }
  return false;
}

inline bool register_available(u8 reg) {
  if(reg < 15) return true;
#ifdef MK61_REF_HOST_TEST
  extern bool host_rf_enabled;
  return reg == 15 && host_rf_enabled;
#elif defined(MK61_BUILD_PORTABLE_SYSTEM)
  return reg == 15 && portable_system::call(MK61_SYS_SETTINGS, MK61_SYS_REGISTER_F);
#else
  return reg == 15 && core_61::expanded_program_is_on();
#endif
}

inline stack stack_from_ref(Kind kind) {
  switch(kind) {
    case Kind::X: return stack::X;
    case Kind::Y: return stack::Y;
    case Kind::Z: return stack::Z;
    case Kind::T: return stack::T;
    case Kind::R: break;
  }
  return stack::X;
}

inline double parse_display_number(const char* value) {
  char buffer[20];
  char* out = buffer;
  if(value[0] == '-') *out++ = '-';
  for(int i = 1; i <= 9; i++) {
    if(value[i] == ' ') continue;
    *out++ = (value[i] == 'O') ? '0' : value[i];
  }
  *out++ = 'e';
  *out++ = (value[11] == '-') ? '-' : '+';
  *out++ = (value[12] == 'O') ? '0' : value[12];
  *out++ = (value[13] == 'O') ? '0' : value[13];
  *out = 0;
  return mk_math::atof(buffer);
}

inline bool double_to_parts(double value, char& sign, char mantissa[8], isize& pow10) {
  if(!mk_math::is_finite(value)) return false;
  if(value < 0) {
    sign = '-';
    value = -value;
  } else {
    sign = ' ';
  }

  if(value == 0.0) {
    memset(mantissa, '0', 8);
    pow10 = 0;
    return true;
  }

  pow10 = (isize) mk_math::log10_floor(value);
  if(pow10 < -99 || pow10 > 99) return false;
  double normalized = value / mk_math::pow10_int((int) pow10);
  if(normalized >= 10.0) {
    normalized /= 10.0;
    pow10++;
  }
  if(normalized < 1.0) {
    normalized *= 10.0;
    pow10--;
  }

  long scaled = (long) mk_math::floor(normalized * 10000000.0 + 0.5);
  if(scaled >= 100000000L) {
    scaled /= 10;
    pow10++;
    if(pow10 > 99) return false;
  }

  for(int i = 7; i >= 0; i--) {
    mantissa[i] = (char) ('0' + (scaled % 10));
    scaled /= 10;
  }
  return true;
}

// Представляет равномерное семизначное слово как точную дробь 0.ddddddd,
// не проходя через double. Например, 1234 превращается в 1.2340000 E-04.
inline bool fraction7_to_parts(u32 value, char mantissa[8], isize& pow10) {
  if(value == 0 || value > 9999999UL || mantissa == nullptr) return false;

  char digits[7];
  for(int index = 6; index >= 0; index--) {
    digits[index] = (char) ('0' + value % 10U);
    value /= 10U;
  }

  usize first = 0;
  while(first < 6 && digits[first] == '0') first++;
  usize out = 0;
  for(usize index = first; index < 7; index++) mantissa[out++] = digits[index];
  while(out < 8) mantissa[out++] = '0';
  pow10 = -(isize) (first + 1U);
  return true;
}

#ifdef MK61_REF_HOST_TEST
extern double host_stack_value[5];
extern double host_register_value[16];
extern bool host_rf_enabled;

inline u8 (&host_register_raw(void))[16][12] {
  static u8 value[16][12] = {};
  return value;
}

inline bool (&host_register_is_raw(void))[16] {
  static bool value[16] = {};
  return value;
}

inline void host_reset(void) {
  memset(host_stack_value, 0, sizeof(double) * 5);
  memset(host_register_value, 0, sizeof(double) * 16);
  memset(host_register_raw(), 0, sizeof(u8) * 16 * 12);
  memset(host_register_is_raw(), 0, sizeof(bool) * 16);
  host_rf_enabled = false;
}

inline void host_set_rf_enabled(bool enabled) {
  host_rf_enabled = enabled;
}

inline double host_get_stack(Kind kind) {
  return host_stack_value[(int) stack_from_ref(kind)];
}

inline double host_get_register(u8 reg) {
  return reg < 16 ? host_register_value[reg] : 0.0;
}
#endif

// Точная запись одного логического слова регистра. В отличие от write(), эта
// форма намеренно допускает тетрады A..F: они используются некоторыми
// историческими играми МК-61 как упакованные данные. Все 12 тетрад проверены
// вызывающим parser-ом, а адреса остаются строго внутри выбранной дорожки R.
inline bool write_raw_register(u8 reg, const u8 raw[12]) {
  if(raw == nullptr || !register_available(reg)) return false;
  for(usize index = 0; index < 12; index++) {
    if(raw[index] > 0x0F) return false;
  }

#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  // Публичный portable ABI пока предоставляет только числовую запись.
  return false;
#elif defined(MK61_REF_HOST_TEST)
  memcpy(host_register_raw()[reg], raw, 12);
  host_register_is_raw()[reg] = true;
  return true;
#else
  const usize base = (usize) reg * 42;
  for(usize index = 0; index < 8; index++) {
    ringM[base + 21 - index * 3] = raw[index];
  }
  ringM[base + 24] = raw[8];
  ringM[base + 33] = raw[9];
  ringM[base + 30] = raw[10];
  ringM[base + 27] = raw[11];
  return true;
#endif
}

inline bool read(const Ref& ref, double& value) {
  if(ref.kind == Kind::R && !register_available(ref.reg)) return false;
#ifdef MK61_REF_HOST_TEST
  if(ref.kind == Kind::R) value = host_get_register(ref.reg);
  else value = host_get_stack(ref.kind);
  return true;
#elif defined(MK61_BUILD_PORTABLE_SYSTEM)
  return portable_system::call(MK61_SYS_REF_READ, (u32) ref.kind, ref.reg, 0, &value);
#else
  char text[15];
  text[14] = 0;
  if(ref.kind == Kind::R) {
    MK61Emu_ReadRegister(ref.reg, text, DISPLAY_SYMBOLS);
  } else {
    read_stack_register(stack_from_ref(ref.kind), text, DISPLAY_SYMBOLS);
  }
  value = parse_display_number(text);
  return true;
#endif
}

#if !defined(MK61_REF_HOST_TEST) && !defined(MK61_BUILD_PORTABLE_SYSTEM)
inline void write_register(u8 reg, char sign, const char mantissa[8], isize pow10) {
  const usize base = (usize) reg * 42;
  isize addr = (isize) base + 21;
  for(int i = 0; i < 8; i++) {
    ringM[addr] = (u8) (mantissa[i] - '0');
    addr -= 3;
  }

  isize stored_pow = pow10;
  ringM[base + 24] = (sign == '-') ? 9 : 0;
  if(stored_pow < 0) {
    stored_pow += 100;
    ringM[base + 33] = 9;
  } else {
    ringM[base + 33] = 0;
  }
  if(stored_pow < 0) stored_pow = 0;
  if(stored_pow > 99) stored_pow = 99;
  ringM[base + 30] = (u8) (stored_pow / 10);
  ringM[base + 27] = (u8) (stored_pow % 10);
}
#endif

inline bool write(const Ref& ref, double value) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  return portable_system::call(MK61_SYS_REF_WRITE, (u32) ref.kind, ref.reg, 0, &value);
#else
  if(ref.kind == Kind::R && !register_available(ref.reg)) return false;
  if(!mk_math::is_finite(value)) return false;

  char sign;
  char mantissa[8];
  isize pow10;
  if(!double_to_parts(value, sign, mantissa, pow10)) return false;

#ifdef MK61_REF_HOST_TEST
  if(ref.kind == Kind::R) {
    host_register_value[ref.reg] = value;
    host_register_is_raw()[ref.reg] = false;
  } else {
    host_stack_value[(int) stack_from_ref(ref.kind)] = value;
  }
  return true;
#else
  if(ref.kind == Kind::R) {
    write_register(ref.reg, sign, mantissa, pow10);
    return true;
  }
  return write_stack_register(stack_from_ref(ref.kind), sign, mantissa, pow10);
#endif
#endif
}

inline bool write_fraction7(const Ref& ref, u32 value) {
  if(ref.kind != Kind::R || !register_available(ref.reg)) return false;
  char mantissa[8];
  isize pow10 = 0;
  if(!fraction7_to_parts(value, mantissa, pow10)) return false;

#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  // Системный ABI принимает void*: операция только читает число, но локальная
  // переменная должна оставаться неконстантной для строгой C++-совместимости.
  double number = (double) value / 10000000.0;
  return portable_system::call(
      MK61_SYS_REF_WRITE, (u32) ref.kind, ref.reg, 0, &number);
#elif defined(MK61_REF_HOST_TEST)
  host_register_value[ref.reg] = (double) value / 10000000.0;
  host_register_is_raw()[ref.reg] = false;
  return true;
#else
  write_register(ref.reg, ' ', mantissa, pow10);
  return true;
#endif
}

} // пространство имён mk61_ref

#endif
