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
  size_t println(const char* value) { return print(value) + write('\n'); }
};
#endif
