#ifndef MK61_UC1609_TRANSPORT_ARDUINO_H
#define MK61_UC1609_TRANSPORT_ARDUINO_H

#include <stddef.h>
#include <stdint.h>
#include <vector>

using boolean = bool;
using byte = uint8_t;

enum {
  LOW = 0,
  HIGH = 1,
  OUTPUT = 1,
  LSBFIRST = 0,
  MSBFIRST = 1,
};

namespace arduino_test {

struct PinWrite {
  int pin;
  int value;
};

inline std::vector<PinWrite> pin_writes;

inline void clear(void) { pin_writes.clear(); }

} // namespace arduino_test

inline void pinMode(int, int) {}
inline void digitalWrite(int pin, int value) {
  arduino_test::pin_writes.push_back({pin, value});
}
inline void delay(uint32_t) {}
inline void delayMicroseconds(uint32_t) {}
inline void yield(void) {}

#endif
