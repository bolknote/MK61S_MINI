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
  if((name[0] == 'R' || name[0] == 'r') && name[2] == 0) {
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

inline void double_to_parts(double value, char& sign, char mantissa[8], isize& pow10) {
  if(value < 0) {
    sign = '-';
    value = -value;
  } else {
    sign = ' ';
  }

  if(value == 0.0) {
    memset(mantissa, '0', 8);
    pow10 = 0;
    return;
  }

  pow10 = (isize) mk_math::log10_floor(value);
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
  }

  for(int i = 7; i >= 0; i--) {
    mantissa[i] = (char) ('0' + (scaled % 10));
    scaled /= 10;
  }
}

#ifdef MK61_REF_HOST_TEST
extern double host_stack_value[5];
extern double host_register_value[16];
extern bool host_rf_enabled;

inline void host_reset(void) {
  memset(host_stack_value, 0, sizeof(double) * 5);
  memset(host_register_value, 0, sizeof(double) * 16);
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

inline bool read(const Ref& ref, double& value) {
  if(ref.kind == Kind::R && !register_available(ref.reg)) return false;
#ifdef MK61_REF_HOST_TEST
  if(ref.kind == Kind::R) value = host_get_register(ref.reg);
  else value = host_get_stack(ref.kind);
  return true;
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

#ifndef MK61_REF_HOST_TEST
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
  if(ref.kind == Kind::R && !register_available(ref.reg)) return false;
  if(mk_math::is_nan(value) || mk_math::is_inf(value)) return false;

  char sign;
  char mantissa[8];
  isize pow10;
  double_to_parts(value, sign, mantissa, pow10);

#ifdef MK61_REF_HOST_TEST
  if(ref.kind == Kind::R) host_register_value[ref.reg] = value;
  else host_stack_value[(int) stack_from_ref(ref.kind)] = value;
  return true;
#else
  if(ref.kind == Kind::R) {
    write_register(ref.reg, sign, mantissa, pow10);
    return true;
  }
  write_stack_register(stack_from_ref(ref.kind), sign, mantissa, pow10);
  return true;
#endif
}

} // namespace mk61_ref

#endif
