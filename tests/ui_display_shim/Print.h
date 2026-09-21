#ifndef MK61_UI_DISPLAY_TEST_PRINT_H
#define MK61_UI_DISPLAY_TEST_PRINT_H
#include "Arduino.h"
class Print {
 public:
  virtual ~Print() = default;
  virtual size_t write(uint8_t value) = 0;
  size_t print(const char* value) {
    size_t count = 0;
    if(value) while(*value) count += write((uint8_t) *value++);
    return count;
  }
  size_t print(char value) { return write((uint8_t) value); }
  size_t print(unsigned long value, int base = 10) {
    char reversed[8 * sizeof(value)];
    size_t digits = 0;
    const unsigned radix = base == 16 ? 16U : 10U;
    do {
      const unsigned digit = (unsigned) (value % radix);
      reversed[digits++] = (char) (digit < 10 ? '0' + digit
                                              : 'A' + digit - 10);
      value /= radix;
    } while(value != 0);
    size_t count = 0;
    while(digits != 0) count += write((uint8_t) reversed[--digits]);
    return count;
  }
  size_t print(long value, int base = 10) {
    size_t count = 0;
    if(value < 0 && base != 16) {
      count += write('-');
      value = -value;
    }
    return count + print((unsigned long) value, base);
  }
  size_t print(unsigned value, int base = 10) {
    return print((unsigned long) value, base);
  }
  size_t print(int value, int base = 10) {
    return print((long) value, base);
  }
  size_t println(const char* value) { return print(value) + write('\n'); }
};
#endif
