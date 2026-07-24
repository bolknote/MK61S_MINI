#ifndef MK61_UC1609_TRANSPORT_PRINT_H
#define MK61_UC1609_TRANSPORT_PRINT_H

#include "Arduino.h"

class Print {
  public:
    virtual ~Print() = default;
    virtual size_t write(uint8_t value) = 0;
};

#endif
