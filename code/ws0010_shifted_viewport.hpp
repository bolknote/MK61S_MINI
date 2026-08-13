#ifndef MK61_WS0010_SHIFTED_VIEWPORT_HPP
#define MK61_WS0010_SHIFTED_VIEWPORT_HPP

#include "rust_types.h"

namespace ws0010_shifted_viewport {

// WS0010 N=1 character mode has two native 64-byte DDRAM rows.  The renderer
// deliberately writes the owner-provided layout straight into controller RAM:
// firmware does not allocate a permanent 128-byte duplicate merely to scroll.
static constexpr u8 ROWS = 2;
static constexpr u8 VISIBLE_COLS = 16;
static constexpr u8 DDRAM_COLS = 64;

static constexpr u8 COMMAND_RETURN_HOME = 0x02;
static constexpr u8 COMMAND_SET_DDRAM = 0x80;
static constexpr u8 COMMAND_SHIFT_LEFT = 0x18;
static constexpr u8 COMMAND_SHIFT_RIGHT = 0x1C;

struct ShiftPlan {
  u8 steps;
  bool left;
};

struct BusWrite {
  bool data;
  u8 value;
};

inline BusWrite command(u8 value) { return {false, value}; }
inline BusWrite data(u8 value) { return {true, value}; }

inline ShiftPlan shortestShift(u8 current, u8 target) {
  current = (u8) (current % DDRAM_COLS);
  target = (u8) (target % DDRAM_COLS);
  const u8 left_steps = (u8) ((target + DDRAM_COLS - current) % DDRAM_COLS);
  const u8 right_steps = (u8) ((current + DDRAM_COLS - target) % DDRAM_COLS);
  return left_steps <= right_steps ? ShiftPlan{left_steps, true}
                                   : ShiftPlan{right_steps, false};
}

constexpr u8 physicalAddress(u8 shift, u8 visible_column) {
  return (u8) ((shift + visible_column) % DDRAM_COLS);
}

// A hardware display shift is shared by both controller rows.  To scroll one
// row independently, keep that shared shift unchanged and rotate the selected
// row while streaming it into physical DDRAM.  At the visible physical
// address `shared_shift + column` this places the owner's logical
// `row_shift + column` byte.
constexpr u8 independentSourceAddress(u8 shared_shift, u8 row_shift,
                                      u8 physical_address) {
  return (u8) ((physical_address + row_shift + DDRAM_COLS - shared_shift) %
               DDRAM_COLS);
}

constexpr u8 setDdramAddressCommand(u8 row, u8 address) {
  const u8 row_address = row == 0 ? 0x00u : 0x40u;
  return (u8) (COMMAND_SET_DDRAM | row_address | address);
}

template<typename Emit>
bool begin(bool& active, u8& current_shift, Emit emit) {
  if(!active) {
    emit(command(COMMAND_RETURN_HOME));
    active = true;
    current_shift = 0;
  }
  return true;
}

template<typename Emit>
bool writeLayout(bool& active, u8& current_shift,
                 const u8 desired[ROWS][DDRAM_COLS], Emit emit) {
  if(desired == nullptr) return false;
  begin(active, current_shift, emit);

  // The layout normally lives on the caller's stack.  Streaming all 128 bytes
  // costs about 6.5 ms with the conservative write delay, but saves permanent
  // SRAM and leaves the complete 2x64 image in the controller's own DDRAM.
  for(u8 row = 0; row < ROWS; row++) {
    emit(command(setDdramAddressCommand(row, 0)));
    for(u8 column = 0; column < DDRAM_COLS; column++) {
      emit(data(desired[row][column]));
    }
  }

  return true;
}

template<typename Emit>
bool shiftTo(bool& active, u8& current_shift, u8 target_shift, Emit emit) {
  if(target_shift >= DDRAM_COLS) return false;
  begin(active, current_shift, emit);

  const ShiftPlan plan = shortestShift(current_shift, target_shift);
  const u8 shift_command = plan.left ? COMMAND_SHIFT_LEFT
                                     : COMMAND_SHIFT_RIGHT;
  for(u8 step = 0; step < plan.steps; step++) emit(command(shift_command));
  current_shift = target_shift;
  return true;
}

template<typename Emit>
bool writeRow(bool& active, u8& current_shift,
              const u8 desired[ROWS][DDRAM_COLS], u8 row,
              u8 row_shift, Emit emit) {
  if(desired == nullptr || row >= ROWS || row_shift >= DDRAM_COLS) {
    return false;
  }

  // Do not issue display-shift commands here: they would visibly move the
  // untouched row as well.  Rotate only this row's physical contents around
  // the already active common viewport.
  begin(active, current_shift, emit);
  emit(command(setDdramAddressCommand(row, 0)));
  for(u8 physical = 0; physical < DDRAM_COLS; physical++) {
    emit(data(desired[row][independentSourceAddress(
      current_shift, row_shift, physical)]));
  }
  return true;
}

template<typename Emit>
bool render(bool& active, u8& current_shift,
            const u8 desired[ROWS][DDRAM_COLS], u8 target_shift, Emit emit) {
  if(desired == nullptr || target_shift >= DDRAM_COLS) return false;
  return writeLayout(active, current_shift, desired, emit) &&
         shiftTo(active, current_shift, target_shift, emit);
}

template<typename Emit>
void end(bool& active, u8& current_shift, Emit emit) {
  if(!active) return;
  emit(command(COMMAND_RETURN_HOME));
  active = false;
  current_shift = 0;
}

static_assert(physicalAddress(63, 15) == 14,
              "WS0010 viewport must wrap across all 64 DDRAM cells");
static_assert(independentSourceAddress(17, 29, 17) == 29 &&
              independentSourceAddress(63, 0, 63) == 0,
              "WS0010 independent-row rotation regression");
static_assert(setDdramAddressCommand(0, 63) == 0xBF &&
              setDdramAddressCommand(1, 63) == 0xFF,
              "WS0010 DDRAM endpoint command regression");

} // namespace ws0010_shifted_viewport

#endif
