#ifndef MK61_WS0010_CONTROLLER_HPP
#define MK61_WS0010_CONTROLLER_HPP

#include "rust_types.h"

namespace ws0010 {

// WS0010 IC specification, 4-bit 6800 interface.  Keep the controller policy
// independent from Arduino so the exact bus trace can be host-tested.
static constexpr u16 POWER_STABILIZATION_MS = 500;
// A controller-only recovery does not need the full cold power-on interval,
// but it must let a half-finished Clear finish before changing interface mode.
static constexpr u8 RECOVERY_STABILIZATION_MS = 10;
static constexpr u8 FOUR_BIT_FUNCTION_NIBBLE = 0x02;
static constexpr u8 BUS_SYNCHRONIZATION_WRITES = 5;

static constexpr u8 FUNCTION_SET_4BIT_2LINE_5X8_FT10 = 0x2A;
static constexpr u8 MODE_CHARACTER_POWER_ON = 0x17;
static constexpr u8 MODE_CHARACTER_POWER_OFF = 0x13;
static constexpr u8 MODE_GRAPHICS_POWER_ON = 0x1F;
static constexpr u8 DISPLAY_OFF = 0x08;
static constexpr u8 DISPLAY_ON = 0x0C;
static constexpr u8 CLEAR_DISPLAY = 0x01;
static constexpr u8 RETURN_HOME = 0x02;
static constexpr u8 ENTRY_DECREMENT_NO_SHIFT = 0x04;
static constexpr u8 ENTRY_DECREMENT_WITH_SHIFT = 0x05;
static constexpr u8 ENTRY_INCREMENT_NO_SHIFT = 0x06;
static constexpr u8 ENTRY_INCREMENT_WITH_SHIFT = 0x07;
static constexpr u8 CURSOR_LEFT = 0x10;
static constexpr u8 CURSOR_RIGHT = 0x14;
static constexpr u8 DISPLAY_SHIFT_LEFT = 0x18;
static constexpr u8 DISPLAY_SHIFT_RIGHT = 0x1C;

enum class InitializationPhase : u8 {
  IDLE = 0,
  GPIO_SAFE,
  POWER_WAIT,
  BUS_SYNC,
  CONTROLLER_CONFIGURED,
  RESTORING_CGRAM,
  RESTORING_DDRAM,
  READY,
};

inline const char* initializationPhaseName(InitializationPhase phase) {
  switch(phase) {
    case InitializationPhase::IDLE: return "idle";
    case InitializationPhase::GPIO_SAFE: return "gpio-safe";
    case InitializationPhase::POWER_WAIT: return "power-wait";
    case InitializationPhase::BUS_SYNC: return "bus-sync";
    case InitializationPhase::CONTROLLER_CONFIGURED: return "configured";
    case InitializationPhase::RESTORING_CGRAM: return "restore-cgram";
    case InitializationPhase::RESTORING_DDRAM: return "restore-ddram";
    case InitializationPhase::READY: return "ready";
  }
  return "unknown";
}

// The controller table specifies 6.2 ms worst case for Clear.  Other
// instructions are documented as zero at 250 kHz; 50 us retains the proven
// conservative character-display timing without attempting a 5 V BF read.
static constexpr u16 CLEAR_DELAY_US = 6200;
static constexpr u8 COMMAND_DELAY_US = 50;

static constexpr u8 CHARACTER_ROWS = 2;
// In N=1 mode the controller exposes two independent 64-byte DDRAM rows
// (0x00..0x3f and 0x40..0x7f), although the WEH001602A window shows 16 cells.
// The WS0010 profile uses the complete native ring; A00/A02 keep their own
// 40-column controller policy.
static constexpr u8 CHARACTER_VISIBLE_COLS = 16;
static constexpr u8 CHARACTER_DDRAM_COLS = 64;
static constexpr u16 CHARACTER_DDRAM_BYTES =
  (u16) CHARACTER_ROWS * CHARACTER_DDRAM_COLS;
static constexpr u8 CGRAM_GLYPHS_5X8 = 8;
static constexpr u8 CGRAM_ROWS_5X8 = 8;
static constexpr u8 CGRAM_CURSOR_ROW = 7;

enum class AddressSpace : u8 {
  DDRAM,
  CGRAM,
};

// Executable specification for the character-mode control state. It is used
// by host tests to cover every command transition without putting a model or a
// second DDRAM copy into firmware RAM.
struct CharacterState {
  AddressSpace space = AddressSpace::DDRAM;
  u8 address = 0;
  u8 display_shift = 0;
  bool increment = true;
  bool automatic_shift = false;
  bool display_on = false;
  bool cursor_on = false;
  bool blink_on = false;
  bool graphics = false;
  bool power_on = false;
};

constexpr u8 stepAddress(u8 address, u8 mask, bool increment) {
  return increment ? (u8) ((address + 1u) & mask)
                   : (u8) ((address - 1u) & mask);
}

inline void applyCharacterCommand(CharacterState& state, u8 command) {
  if(command == CLEAR_DISPLAY) {
    state.space = AddressSpace::DDRAM;
    state.address = 0;
    state.display_shift = 0;
    // WS0010 explicitly sets I/D=1 and leaves S unchanged on Clear.
    state.increment = true;
    return;
  }
  if((command & 0xFEu) == RETURN_HOME) {
    state.space = AddressSpace::DDRAM;
    state.address = 0;
    state.display_shift = 0;
    return;
  }
  if((command & 0xFCu) == 0x04u) {
    state.increment = (command & 0x02u) != 0;
    state.automatic_shift = (command & 0x01u) != 0;
    return;
  }
  if((command & 0xF8u) == 0x08u) {
    state.display_on = (command & 0x04u) != 0;
    state.cursor_on = (command & 0x02u) != 0;
    state.blink_on = (command & 0x01u) != 0;
    return;
  }
  if((command & 0xF0u) == 0x10u && (command & 0x03u) == 0x03u) {
    state.graphics = (command & 0x08u) != 0;
    state.power_on = (command & 0x04u) != 0;
    return;
  }
  if((command & 0xF3u) == 0x10u) {
    const bool right = (command & 0x04u) != 0;
    if((command & 0x08u) == 0) {
      state.space = AddressSpace::DDRAM;
      state.address = stepAddress(state.address, 0x7Fu, right);
    } else {
      state.display_shift = right
        ? stepAddress(state.display_shift, 0x3Fu, false)
        : stepAddress(state.display_shift, 0x3Fu, true);
    }
    return;
  }
  if((command & 0x80u) != 0) {
    state.space = AddressSpace::DDRAM;
    state.address = (u8) (command & 0x7Fu);
    return;
  }
  if((command & 0xC0u) == 0x40u) {
    state.space = AddressSpace::CGRAM;
    state.address = (u8) (command & 0x3Fu);
  }
}

inline void applyCharacterDataWrite(CharacterState& state) {
  if(state.space == AddressSpace::CGRAM) {
    state.address = stepAddress(state.address, 0x3Fu, state.increment);
    return;
  }
  state.address = stepAddress(state.address, 0x7Fu, state.increment);
  if(state.automatic_shift) {
    state.display_shift = state.increment
      ? stepAddress(state.display_shift, 0x3Fu, true)
      : stepAddress(state.display_shift, 0x3Fu, false);
  }
}

// In 5x8 mode the eighth CGRAM row is ORed with the hardware cursor.  The
// controller specification requires it to stay blank.  Normalising at the
// hardware boundary also makes the retained CGRAM shadow exactly reproducible.
constexpr u8 normalizeCgramRow(u8 row, u8 value) {
  return row == CGRAM_CURSOR_ROW ? 0 : (u8) (value & 0x1Fu);
}

static constexpr u8 GRAPHICS_WIDTH = 100;
static constexpr u8 GRAPHICS_HEIGHT = 16;
static constexpr u8 GRAPHICS_PAGES = GRAPHICS_HEIGHT / 8;
static constexpr u16 GRAPHICS_FRAME_BYTES =
  (u16) GRAPHICS_WIDTH * GRAPHICS_PAGES;

constexpr u8 graphicsXAddress(u8 x) {
  return (u8) (0x80u | x);
}

constexpr u8 graphicsPageAddress(u8 page) {
  return (u8) (0x40u | page);
}

template<typename Sink>
inline void emitControllerConfiguration(Sink& sink, bool display_on) {
  // Function Set is legal only while the display is off. Both cold and warm
  // callers arrive here immediately after selecting a known 4-bit boundary.
  // Recovery can deliberately leave D=0 while retained RAM is restored.
  sink.command(FUNCTION_SET_4BIT_2LINE_5X8_FT10);
  sink.command(MODE_CHARACTER_POWER_ON);
  sink.command(DISPLAY_OFF);
  sink.command(CLEAR_DISPLAY);
  sink.command(ENTRY_INCREMENT_NO_SHIFT);
  sink.command(display_on ? DISPLAY_ON : DISPLAY_OFF);
}

template<typename Sink>
inline void emitSynchronizedFourBitInitialization(Sink& sink,
                                                   bool display_on) {
  // This is the controller's own "Repeated procedures for an 4-bit bus
  // interface" trace, not the superficially similar HD44780 reset recipe.
  // Five consecutive 0000 transfers trigger WS0010's synchronization
  // function. The controller specifies that the next transfer is the lower
  // four bits; raw 0010 completes that phase, and command(0x2A) supplies the
  // following complete Function Set as 0010,N/F/FT1/FT0.
  for(u8 i = 0; i < BUS_SYNCHRONIZATION_WRITES; i++) sink.nibble(0);
  sink.nibble(FOUR_BIT_FUNCTION_NIBBLE);
  emitControllerConfiguration(sink, display_on);
}

template<typename Sink>
inline void emitFourBitInitialization(Sink& sink, bool display_on = true) {
  // The manufacturer's synchronization flow explicitly starts at Power ON,
  // so using it here also protects against a display supply which decays more
  // slowly than the MCU supply.
  emitSynchronizedFourBitInitialization(sink, display_on);
}

template<typename Sink>
inline void emitFourBitRecovery(Sink& sink, bool display_on = true) {
  // A warm MCU reset can interrupt either half of a 4-bit transfer. Use the
  // same documented synchronization function; only the preceding power-wait
  // duration differs between cold initialization and recovery.
  emitSynchronizedFourBitInitialization(sink, display_on);
}

static_assert(GRAPHICS_FRAME_BYTES == 200,
              "WS0010 100x16 GDRAM must occupy exactly 200 bytes");
static_assert(CHARACTER_DDRAM_BYTES == 128,
              "WS0010 two-line DDRAM must occupy 128 bytes");
static_assert(normalizeCgramRow(0, 0xFF) == 0x1F &&
              normalizeCgramRow(CGRAM_CURSOR_ROW, 0x1F) == 0,
              "WS0010 CGRAM cursor-row policy regression");
static_assert(RETURN_HOME == 0x02 && ENTRY_INCREMENT_NO_SHIFT == 0x06 &&
              CURSOR_LEFT == 0x10 && CURSOR_RIGHT == 0x14 &&
              DISPLAY_SHIFT_LEFT == 0x18 && DISPLAY_SHIFT_RIGHT == 0x1C,
              "WS0010 character-control command regression");
static_assert(graphicsXAddress(0) == 0x80 &&
              graphicsXAddress(99) == 0xE3,
              "WS0010 graphics X command regression");
static_assert(graphicsPageAddress(0) == 0x40 &&
              graphicsPageAddress(1) == 0x41,
              "WS0010 graphics page command regression");

} // namespace ws0010

#endif
