// Минимальная хостовая заглушка Arduino.h для сборки config.h, tools.hpp и
// mk61emu_core.cpp на хосте в самотесте CORE-подсистемы mk_math.
#ifndef MK_MATH_HOST_ARDUINO_H
#define MK_MATH_HOST_ARDUINO_H

#include <stdint.h>
#include <stdio.h>

enum { HEX = 16, DEC = 10 };

// Константы имён выводов STM32 из config.h (здесь их значения несущественны).
enum {
  PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7, PA8, PA9, PA10, PA11, PA12, PA13, PA14, PA15,
  PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7, PB8, PB9, PB10, PB11, PB12, PB13, PB14, PB15,
  PC0, PC1, PC2, PC3, PC4, PC5, PC6, PC7, PC8, PC9, PC10, PC11, PC12, PC13, PC14, PC15
};

struct HostSerial {
  void write(char) {}
  void write(const char*) {}
  void print(int) {}
  void print(int, int) {}
  void print(const char*) {}
  void print(char) {}
  void println(int) {}
  void println(int, int) {}
  void println(const char*) {}
  void println() {}
  void flush() {}
};

inline HostSerial Serial;

inline uint32_t millis(void) { return 0; }
inline void delay(uint32_t) {}

#endif
