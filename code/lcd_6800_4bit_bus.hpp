#ifndef MK61_LCD_6800_4BIT_BUS_HPP
#define MK61_LCD_6800_4BIT_BUS_HPP

#include "rust_types.h"

// Executable, platform-independent description of the 6800 write-only bus.
// The firmware and host trace test instantiate the same templates, so GPIO
// order, E pulse width and the permanent RW=LOW rule cannot silently diverge.
namespace lcd_6800_4bit_bus {

static constexpr u8 SETUP_US = 1;
static constexpr u8 ENABLE_US = 1;
static constexpr u8 HOLD_US = 1;

template<typename Sink>
inline void prepareWrite(Sink& sink) {
  // Preload every output latch before switching the corresponding GPIO mode.
  // In particular, E can never acquire a rising edge during initialization.
  sink.setRwOutputLow();
  sink.setRsOutputLow();
  sink.setEnableOutputLow();
  for(u8 bit = 0; bit < 4; bit++) sink.setDataOutputLow(bit);
}

template<typename Sink>
inline void writeNibble(Sink& sink, u8 nibble) {
  sink.enable(false);
  for(u8 bit = 0; bit < 4; bit++) {
    sink.data(bit, (nibble & ((u8) 1u << bit)) != 0);
  }
  sink.delayMicroseconds(SETUP_US);
  sink.enable(true);
  sink.delayMicroseconds(ENABLE_US);
  sink.enable(false);
  sink.delayMicroseconds(HOLD_US);
}

template<typename Sink>
inline void writeByte(Sink& sink, u8 value, bool data) {
  sink.rw(false);
  sink.rs(data);
  writeNibble(sink, (u8) (value >> 4));
  writeNibble(sink, (u8) (value & 0x0Fu));
}

static_assert(SETUP_US * 1000u >= 40u && ENABLE_US * 1000u >= 250u,
              "6800 write timing must satisfy WS0010 minimums");

} // namespace lcd_6800_4bit_bus

#endif
