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
// A warm MCU reset leaves the separately powered OLED panel and its internal
// DC/DC alive.  Cycle PWR while D=0 after restoring the four-bit boundary;
// this is the only reset mechanism available on modules without a reset pin.
static constexpr u8 INTERNAL_POWER_CYCLE_MS = 10;
static constexpr u8 FOUR_BIT_FUNCTION_NIBBLE = 0x02;
static constexpr u8 BUS_SYNCHRONIZATION_WRITES = 5;
// In 4-bit mode the WS0010 timing diagram requires a complete BF/AC read
// (high and low nibble) after every complete command or data byte.
static constexpr u8 BUSY_READ_NIBBLES_PER_POLL = 2;

static constexpr u8 FUNCTION_SET_4BIT_2LINE_5X8_FT10 = 0x2A;
static constexpr u8 MODE_CHARACTER_POWER_ON = 0x17;
static constexpr u8 MODE_CHARACTER_POWER_OFF = 0x13;
static constexpr u8 MODE_GRAPHICS_POWER_ON = 0x1F;
static constexpr u8 MODE_GRAPHICS_POWER_OFF = 0x1B;
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
static constexpr u8 SET_CGRAM_ADDRESS = 0x40;
static constexpr u8 SET_DDRAM_ADDRESS = 0x80;

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

// Graphics is an exclusive controller address space, not merely a rendering
// preference.  Keep the owner in the same single byte previously occupied by
// the active flag so enforcing ownership costs no persistent RAM.
enum class GraphicsOwner : u8 {
  NONE = 0,
  API,
  QUALIFICATION,
};

constexpr bool graphicsOwned(GraphicsOwner owner) {
  return owner != GraphicsOwner::NONE;
}

inline const char* graphicsOwnerName(GraphicsOwner owner) {
  switch(owner) {
    case GraphicsOwner::NONE: return "none";
    case GraphicsOwner::API: return "api";
    case GraphicsOwner::QUALIFICATION: return "qualification";
  }
  return "unknown";
}

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

// A CGRAM transfer changes the controller address space.  Every public glyph
// operation must explicitly return to the logical character cursor before the
// next Print::write(), otherwise that byte is interpreted as another CGRAM
// row.  Keep the command construction here so production and host tests share
// the exact 2x64 WS0010 address policy.
constexpr u8 characterDdramAddressCommand(u8 row, u8 column) {
  return (u8) (SET_DDRAM_ADDRESS | (row == 0 ? 0x00u : 0x40u) |
               (column & 0x3Fu));
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
// WEH001602A is a 16x2 character panel: each character cell contains five
// emitting columns. The WS0010 still exposes all 100 GDRAM addresses, but the
// module connects only 16 * 5 of them to visible OLED dots in graphics mode.
static constexpr u8 GRAPHICS_VISIBLE_WIDTH =
  CHARACTER_VISIBLE_COLS * 5;
static constexpr u16 GRAPHICS_VISIBLE_FRAME_BYTES =
  (u16) GRAPHICS_VISIBLE_WIDTH * GRAPHICS_PAGES;

constexpr u8 graphicsXAddress(u8 x) {
  return (u8) (0x80u | x);
}

constexpr u8 graphicsPageAddress(u8 page) {
  return (u8) (0x40u | page);
}

template<typename Sink>
inline void emitControllerConfiguration(Sink& sink, bool display_on,
                                         bool cycle_internal_power) {
  // The synchronization procedure requires Function Set to be the first full
  // instruction after its raw 0010 transfer. A warm MCU reset, however, may
  // have left D=1, while WS0010 permits Function Set only with D=0. Complete
  // the mandatory bus transition, turn the panel off immediately, then repeat
  // Function Set in its documented state before changing G/C or touching RAM.
  sink.command(FUNCTION_SET_4BIT_2LINE_5X8_FT10);
  sink.command(DISPLAY_OFF);
  sink.command(FUNCTION_SET_4BIT_2LINE_5X8_FT10);
  if(cycle_internal_power) {
    sink.command(MODE_CHARACTER_POWER_OFF);
    sink.delayMilliseconds(INTERNAL_POWER_CYCLE_MS);
  }
  sink.command(MODE_CHARACTER_POWER_ON);
  if(cycle_internal_power) {
    sink.delayMilliseconds(INTERNAL_POWER_CYCLE_MS);
  }
  sink.command(CLEAR_DISPLAY);
  sink.command(ENTRY_INCREMENT_NO_SHIFT);
  sink.command(display_on ? DISPLAY_ON : DISPLAY_OFF);
}

template<typename EmitCommand>
inline void emitHiddenGraphicsMode(EmitCommand emit_command) {
  // G/C is changed only while D=0. The caller fills GDRAM before issuing its
  // final Display On, so stale or partially written graphics cannot flash.
  emit_command(DISPLAY_OFF);
  emit_command(MODE_GRAPHICS_POWER_ON);
}

template<typename EmitCommand>
inline void emitHiddenCharacterMode(EmitCommand emit_command) {
  emit_command(DISPLAY_OFF);
  emit_command(MODE_CHARACTER_POWER_ON);
}

template<typename Sink>
inline void emitSynchronizedFourBitInitialization(Sink& sink,
                                                   bool display_on,
                                                   bool cycle_internal_power) {
  // This is the controller's own "Repeated procedures for an 4-bit bus
  // interface" trace, not the superficially similar HD44780 reset recipe.
  // Five consecutive 0000 transfers trigger WS0010's synchronization
  // function. The controller specifies that the next transfer is the lower
  // four bits; raw 0010 completes that phase, and command(0x2A) supplies the
  // following complete Function Set as 0010,N/F/FT1/FT0.
  for(u8 i = 0; i < BUS_SYNCHRONIZATION_WRITES; i++) sink.nibble(0);
  sink.nibble(FOUR_BIT_FUNCTION_NIBBLE);
  emitControllerConfiguration(sink, display_on, cycle_internal_power);
}

template<typename Sink>
inline void emitFourBitInitialization(Sink& sink, bool display_on = true) {
  // The manufacturer's synchronization flow explicitly starts at Power ON,
  // so using it here also protects against a display supply which decays more
  // slowly than the MCU supply.
  emitSynchronizedFourBitInitialization(sink, display_on, false);
}

template<typename Sink>
inline void emitFourBitRecovery(Sink& sink, bool display_on = true) {
  // A warm MCU reset can interrupt either half of a 4-bit transfer while the
  // OLED remains powered. Restore the byte boundary first, then cycle the
  // controller's documented internal PWR bit while the display is hidden.
  emitSynchronizedFourBitInitialization(sink, display_on, true);
}

static_assert(GRAPHICS_FRAME_BYTES == 200,
              "WS0010 100x16 GDRAM must occupy exactly 200 bytes");
static_assert(GRAPHICS_VISIBLE_WIDTH == 80 &&
              GRAPHICS_VISIBLE_FRAME_BYTES == 160,
              "WEH001602A visible graphics matrix must be 80x16");
static_assert(CHARACTER_DDRAM_BYTES == 128,
              "WS0010 two-line DDRAM must occupy 128 bytes");
static_assert(normalizeCgramRow(0, 0xFF) == 0x1F &&
              normalizeCgramRow(CGRAM_CURSOR_ROW, 0x1F) == 0,
              "WS0010 CGRAM cursor-row policy regression");
static_assert(RETURN_HOME == 0x02 && ENTRY_INCREMENT_NO_SHIFT == 0x06 &&
              CURSOR_LEFT == 0x10 && CURSOR_RIGHT == 0x14 &&
              DISPLAY_SHIFT_LEFT == 0x18 && DISPLAY_SHIFT_RIGHT == 0x1C,
              "WS0010 character-control command regression");
static_assert(MODE_CHARACTER_POWER_OFF == 0x13 &&
              MODE_CHARACTER_POWER_ON == 0x17 &&
              MODE_GRAPHICS_POWER_OFF == 0x1B &&
              MODE_GRAPHICS_POWER_ON == 0x1F,
              "WS0010 G/C and PWR command regression");
static_assert(graphicsXAddress(0) == 0x80 &&
              graphicsXAddress(99) == 0xE3,
              "WS0010 graphics X command regression");
static_assert(graphicsPageAddress(0) == 0x40 &&
              graphicsPageAddress(1) == 0x41,
              "WS0010 graphics page command regression");
static_assert(characterDdramAddressCommand(0, 0) == 0x80 &&
              characterDdramAddressCommand(0, 63) == 0xBF &&
              characterDdramAddressCommand(1, 0) == 0xC0 &&
              characterDdramAddressCommand(1, 63) == 0xFF,
              "WS0010 character DDRAM command regression");

} // namespace ws0010

#endif
