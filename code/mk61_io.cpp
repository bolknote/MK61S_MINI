#include "mk61_io.hpp"
namespace mk61_io {
char* format_unsigned(char* end, uint32_t value, uint8_t base) {
  if(base < 2 || base > 36) base = 10;
  do {
    const uint32_t digit = value % base;
    *--end = static_cast<char>(digit < 10 ? '0'+digit : 'A'+digit-10);
    value /= base;
  } while(value);
  return end;
}
}
