#ifndef MK61_NUMBER_FORMAT_HPP
#define MK61_NUMBER_FORMAT_HPP

#include "rust_types.h"
#include "mk_math.hpp"

namespace number_format {

inline void append_char(char*& out, char* end, char value) {
  if(out < end) *out++ = value;
}

inline void append_uint(char*& out, char* end, unsigned long long value) {
  char digits[24];
  u8 count = 0;
  do {
    digits[count++] = (char) ('0' + value % 10ULL);
    value /= 10ULL;
  } while(value != 0 && count < sizeof(digits));
  while(count != 0) append_char(out, end, digits[--count]);
}

inline void copy(char* output, usize capacity, const char* text) {
  if(capacity == 0) return;
  usize i = 0;
  while(i + 1 < capacity && text[i] != 0) {
    output[i] = text[i];
    i++;
  }
  output[i] = 0;
}

inline void fixed(double value, int decimals, char* output, usize capacity) {
  if(capacity == 0) return;
  if(decimals < 0) decimals = 0;
  if(decimals > 17) decimals = 17;

  const bool negative = value < 0.0;
  const double absolute = negative ? -value : value;
  unsigned long long scale = 1ULL;
  for(int i = 0; i < decimals; i++) scale *= 10ULL;

  const unsigned long long scaled =
      (unsigned long long) (absolute * (double) scale + 0.5);
  const unsigned long long integer = scaled / scale;
  unsigned long long fraction = scaled % scale;

  char buffer[48];
  char* cursor = buffer;
  char* const end = buffer + sizeof(buffer) - 1;
  if(negative && scaled != 0) append_char(cursor, end, '-');
  append_uint(cursor, end, integer);
  if(decimals != 0) {
    append_char(cursor, end, '.');
    char fractional[18];
    for(int i = decimals - 1; i >= 0; i--) {
      fractional[i] = (char) ('0' + fraction % 10ULL);
      fraction /= 10ULL;
    }
    for(int i = 0; i < decimals; i++) {
      append_char(cursor, end, fractional[i]);
    }
    while(cursor > buffer && cursor[-1] == '0') cursor--;
    if(cursor > buffer && cursor[-1] == '.') cursor--;
  }
  *cursor = 0;
  copy(output, capacity, buffer);
}

// Format like printf("%.*g") for the precision range used by the embedded
// languages, without pulling floating-point printf into either APP.
inline bool general(double value, u8 significant_digits,
                    char* output, usize capacity) {
  if(output == nullptr || capacity == 0 ||
     significant_digits == 0 || significant_digits > 14) return false;
  if(mk_math::is_nan(value)) {
    copy(output, capacity, "NAN");
    return true;
  }
  if(mk_math::is_inf(value)) {
    copy(output, capacity, value < 0.0 ? "-INF" : "INF");
    return true;
  }
  if(value == 0.0) {
    copy(output, capacity, "0");
    return true;
  }

  const double absolute = mk_math::fabs(value);
  int exponent = mk_math::log10_floor(absolute);
  if(exponent >= significant_digits || exponent < -4) {
    double mantissa_value = absolute;
    if(exponent >= 0) {
      mantissa_value /= mk_math::pow10_int(exponent);
    } else {
      for(int i = 0; i < -exponent; i++) mantissa_value *= 10.0;
    }
    char mantissa[32];
    fixed(mantissa_value, significant_digits - 1, mantissa,
          sizeof(mantissa));
    if(mantissa[0] == '1' && mantissa[1] == '0') {
      exponent++;
      fixed(1.0, significant_digits - 1, mantissa, sizeof(mantissa));
    }

    char buffer[48];
    char* cursor = buffer;
    char* const end = buffer + sizeof(buffer) - 1;
    if(value < 0.0) append_char(cursor, end, '-');
    for(const char* source = mantissa; *source != 0; source++) {
      append_char(cursor, end, *source);
    }
    append_char(cursor, end, 'E');
    if(exponent < 0) {
      append_char(cursor, end, '-');
      append_uint(cursor, end, (unsigned long long) -exponent);
    } else {
      append_char(cursor, end, '+');
      append_uint(cursor, end, (unsigned long long) exponent);
    }
    *cursor = 0;
    copy(output, capacity, buffer);
    return true;
  }

  fixed(value, (int) significant_digits - 1 - exponent,
        output, capacity);
  return true;
}

} // namespace number_format

#endif
