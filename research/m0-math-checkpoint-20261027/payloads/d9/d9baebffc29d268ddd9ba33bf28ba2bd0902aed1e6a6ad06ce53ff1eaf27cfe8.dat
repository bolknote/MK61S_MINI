#ifndef MK61_LCD_6800_4BIT_BUS_HPP
#define MK61_LCD_6800_4BIT_BUS_HPP

#include "rust_types.h"

// Executable, platform-independent description of the 6800 four-bit bus. The
// firmware and host trace test instantiate the same templates, so GPIO order,
// E pulse width, write RW=LOW and the complete two-strobe BF/AC read cannot
// silently diverge.
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

// A 4-bit read is still one byte-wide bus transaction.  WS0010 explicitly
// requires both E strobes even when the caller only needs BF from DB7 of the
// first nibble; omitting the second strobe leaves the controller half a byte
// out of phase and is the root of several revision-dependent field failures.
template<typename Source>
inline bool readBusyFlagByte(Source& source) {
  source.enable(true);
  source.delayMicroseconds(ENABLE_US);
  const bool busy = source.busyBit();
  source.enable(false);
  source.delayMicroseconds(HOLD_US);

  source.enable(true);
  source.delayMicroseconds(ENABLE_US);
  source.enable(false);
  source.delayMicroseconds(HOLD_US);
  return busy;
}

// Full data reads use the same two-strobe 4-bit transaction, but sample all
// four bus lines on each edge.  Bus direction and RS/RW ownership stay in the
// hardware adapter so this primitive can be exhaustively trace-tested on the
// host without Arduino GPIO state.
template<typename Source>
inline u8 readByte(Source& source) {
  source.enable(true);
  source.delayMicroseconds(ENABLE_US);
  const u8 high = (u8) (source.nibble() & 0x0Fu);
  source.enable(false);
  source.delayMicroseconds(HOLD_US);

  source.enable(true);
  source.delayMicroseconds(ENABLE_US);
  const u8 low = (u8) (source.nibble() & 0x0Fu);
  source.enable(false);
  source.delayMicroseconds(HOLD_US);
  return (u8) ((high << 4) | low);
}

static_assert(SETUP_US * 1000u >= 40u && ENABLE_US * 1000u >= 250u,
              "6800 write timing must satisfy WS0010 minimums");

} // namespace lcd_6800_4bit_bus

#endif
