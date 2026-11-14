#ifndef MK61_HD44780_CONTROLLER_HPP
#define MK61_HD44780_CONTROLLER_HPP
#include "rust_types.h"
// HD44780 commands shared by A00/A02 and the existing WS0010 adapter.
static constexpr u8 LCD_CLEARDISPLAY = 0x01;
static constexpr u8 LCD_RETURNHOME = 0x02;
static constexpr u8 LCD_DISPLAYCONTROL = 0x08;
static constexpr u8 LCD_CURSORSHIFT = 0x10;
static constexpr u8 LCD_SETCGRAMADDR = 0x40;
static constexpr u8 LCD_SETDDRAMADDR = 0x80;
static constexpr u8 LCD_DISPLAYON = 0x04;
static constexpr u8 LCD_CURSORON = 0x02;
static constexpr u8 LCD_CURSOROFF = 0x00;
static constexpr u8 LCD_BLINKON = 0x01;
static constexpr u8 LCD_BLINKOFF = 0x00;
static constexpr u8 LCD_DISPLAYMOVE = 0x08;
static constexpr u8 LCD_MOVERIGHT = 0x04;
static constexpr u8 LCD_MOVELEFT = 0x00;
namespace hd44780 {
// Valid even after a warm MCU reset in the middle of a 4-bit transfer. Raw
// synchronization nibbles precede complete bytes; BF is probed only afterward.
template <class Sink> void initialize(Sink &sink) {
  sink.delayMilliseconds(50);
  sink.nibble(3);
  sink.delayMicroseconds(4500);
  sink.nibble(3);
  sink.delayMicroseconds(4500);
  sink.nibble(3);
  sink.delayMicroseconds(150);
  sink.nibble(2);
  sink.delayMicroseconds(50);
  sink.command(0x28); // 4-bit, two lines, 5x8 characters.
  sink.command(0x0C); // Display on, cursor and blink off.
  sink.command(0x01); // Clear; sink uses the conservative 2 ms delay.
  sink.command(0x06); // Increment DDRAM address, no automatic display shift.
}
} // namespace hd44780
#endif
