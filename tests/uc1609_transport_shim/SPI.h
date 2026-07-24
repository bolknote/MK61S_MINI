#ifndef MK61_UC1609_TRANSPORT_SPI_H
#define MK61_UC1609_TRANSPORT_SPI_H

#include "Arduino.h"

#include <string.h>
#include <vector>

#define SPI_HAS_TRANSACTION 1
#define SPI_MODE0 0
#define SPI_CLOCK_DIV8 8

class SPISettings {
  public:
    SPISettings(uint32_t, uint8_t, uint8_t) {}
};

class SPIClass {
  public:
    std::vector<std::vector<uint8_t>> transfers;

    void begin(void) {}
    void end(void) {}
    void beginTransaction(const SPISettings&) {}
    void endTransaction(void) {}
    void setClockDivider(uint8_t) {}

    uint8_t transfer(uint8_t value) {
      transfers.push_back({value});
      return 0;
    }

    void transfer(const void* tx_buffer, void*, size_t count) {
      const auto* bytes = static_cast<const uint8_t*>(tx_buffer);
      transfers.emplace_back(bytes, bytes + count);
    }

    void clear(void) { transfers.clear(); }
};

inline SPIClass SPI;

#endif
