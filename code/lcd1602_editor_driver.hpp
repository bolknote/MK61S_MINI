#ifndef MK61_LCD1602_EDITOR_DRIVER_HPP
#define MK61_LCD1602_EDITOR_DRIVER_HPP

#include "lcd1602_editor_viewport.hpp"

namespace lcd1602_editor_driver {

// Байты команд HD44780 вынесены в чистый модуль, чтобы host-тест выполнял
// ровно тот же поток команд, который отправляет production-драйвер.
static constexpr u8 COMMAND_RETURN_HOME = 0x02;
static constexpr u8 COMMAND_SET_DDRAM = 0x80;
static constexpr u8 COMMAND_SHIFT_LEFT = 0x18;
static constexpr u8 COMMAND_SHIFT_RIGHT = 0x1C;

struct BusWrite {
  bool data;
  u8 value;
};

inline BusWrite command(u8 value) {
  return {false, value};
}

inline BusWrite data(u8 value) {
  return {true, value};
}

inline u8 physical_address(u8 shift, u8 visible_column) {
  const u8 sum = (u8) (shift + visible_column);
  return sum < lcd1602_editor_viewport::DDRAM_COLS
       ? sum : (u8) (sum - lcd1602_editor_viewport::DDRAM_COLS);
}

inline u8 set_ddram_address_command(u8 row, u8 address) {
  const u8 row_address = row == 0 ? 0x00u : 0x40u;
  return (u8) (COMMAND_SET_DDRAM | row_address | address);
}

template<typename Emit>
bool render(u8 shadow[lcd1602_editor_viewport::ROWS]
                     [lcd1602_editor_viewport::DDRAM_COLS],
            bool& active, u8& current_shift,
            const u8 desired[lcd1602_editor_viewport::ROWS]
                            [lcd1602_editor_viewport::DDRAM_COLS],
            u8 target_shift, Emit emit) {
  if(shadow == nullptr || desired == nullptr ||
     target_shift >= lcd1602_editor_viewport::DDRAM_COLS) return false;

  if(!active) {
    emit(command(COMMAND_RETURN_HOME));
    active = true;
    current_shift = 0;
  }

  for(u8 row = 0; row < lcd1602_editor_viewport::ROWS; row++) {
    u8 column = 0;
    while(column < lcd1602_editor_viewport::DDRAM_COLS) {
      while(column < lcd1602_editor_viewport::DDRAM_COLS &&
            shadow[row][column] == desired[row][column]) column++;
      if(column >= lcd1602_editor_viewport::DDRAM_COLS) break;

      const u8 run_start = column;
      while(column < lcd1602_editor_viewport::DDRAM_COLS &&
            shadow[row][column] != desired[row][column]) column++;

      emit(command(set_ddram_address_command(row, run_start)));
      for(u8 address = run_start; address < column; address++) {
        emit(data(desired[row][address]));
        shadow[row][address] = desired[row][address];
      }
    }
  }

  const lcd1602_editor_viewport::ShiftPlan plan =
      lcd1602_editor_viewport::shortest_shift(current_shift, target_shift);
  const u8 shift_command = plan.left ? COMMAND_SHIFT_LEFT
                                     : COMMAND_SHIFT_RIGHT;
  for(u8 step = 0; step < plan.steps; step++) {
    emit(command(shift_command));
  }
  current_shift = target_shift;
  return true;
}

template<typename Emit>
void end(bool& active, u8& current_shift, Emit emit) {
  if(!active) return;
  emit(command(COMMAND_RETURN_HOME));
  active = false;
  current_shift = 0;
}

} // пространство имён lcd1602_editor_driver

#endif
