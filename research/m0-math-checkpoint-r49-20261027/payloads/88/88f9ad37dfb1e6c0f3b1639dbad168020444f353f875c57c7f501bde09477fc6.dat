#ifndef MK61_SPI1_TRANSPORT_HPP
#define MK61_SPI1_TRANSPORT_HPP
#include <Arduino.h>
#include "rust_types.h"
#if defined(ARDUINO_ARCH_STM32) &&                                                     \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
#define MK61_SPI1_DIRECT_SUPPORTED 1
#else
#define MK61_SPI1_DIRECT_SUPPORTED 0
#endif
namespace spi1_transport {
bool begin();
void end();
bool begin_transaction(u32 requested_hz);
bool end_transaction();
u8 transfer(u8 value);
bool transfer_buffer(const void *tx, void *rx, usize count, bool allow_dma = true);
u32 peripheral_clock_hz();
u8 br_code();
} // namespace spi1_transport
#endif
