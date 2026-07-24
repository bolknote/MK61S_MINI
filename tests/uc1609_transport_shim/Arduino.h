#ifndef MK61_UC1609_TRANSPORT_ARDUINO_H
#define MK61_UC1609_TRANSPORT_ARDUINO_H

#include <stddef.h>
#include <stdint.h>

using boolean = bool;
using byte = uint8_t;

enum {
  LOW = 0,
  HIGH = 1,
  OUTPUT = 1,
  LSBFIRST = 0,
  MSBFIRST = 1,
};

inline void pinMode(int, int) {}
inline void digitalWrite(int, int) {}
inline void delay(uint32_t) {}
inline void delayMicroseconds(uint32_t) {}
inline void yield(void) {}

#endif
