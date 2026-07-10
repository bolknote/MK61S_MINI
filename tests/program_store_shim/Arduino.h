#ifndef PROGRAM_STORE_HOST_ARDUINO_H
#define PROGRAM_STORE_HOST_ARDUINO_H

#include <stdint.h>

enum {
  PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7, PA8, PA9, PA10, PA11, PA12, PA13, PA14, PA15,
  PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7, PB8, PB9, PB10, PB11, PB12, PB13, PB14, PB15,
  PC0, PC1, PC2, PC3, PC4, PC5, PC6, PC7, PC8, PC9, PC10, PC11, PC12, PC13, PC14, PC15
};

inline uint32_t program_store_host_millis;
inline uint32_t millis(void) { return program_store_host_millis++; }
inline void delay(uint32_t ms) { program_store_host_millis += ms; }

#endif
