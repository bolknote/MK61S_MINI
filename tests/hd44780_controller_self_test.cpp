#include "hd44780_controller.hpp"
#include <cassert>
#include <vector>
struct Controller {
  bool four_bit;
  int high;
  unsigned now = 0, ready_at = 0;
  bool two_lines = false, display = false, increment = false;
  unsigned clears = 0;
  void execute(unsigned value) {
    if ((value & 0xE0) == 0x20) {
      four_bit = (value & 0x10) == 0;
      two_lines = (value & 8) != 0;
      high = -1;
    } else if ((value & 0xF8) == 8)
      display = (value & 4) != 0;
    else if ((value & 0xFC) == 4)
      increment = (value & 2) != 0;
    if (value == 1)
      clears++;
    ready_at = now + (value == 1 || value == 2 || value == 3 ? 2000 : 40);
  }
  void nibble(u8 value) {
    assert(now >= ready_at);
    if (!four_bit)
      execute(value << 4);
    else if (high < 0)
      high = value;
    else {
      const unsigned byte = (unsigned)(high << 4) | value;
      high = -1;
      execute(byte);
    }
  }
  void command(u8 value) {
    assert(four_bit && high < 0);
    nibble(value >> 4);
    // A byte consists of two E strobes; a half-byte does not start execution.
    nibble(value & 15);
    delayMicroseconds(value == 1 ? 2000 : 50);
  }
  void delayMilliseconds(unsigned value) { now += value * 1000; }
  void delayMicroseconds(unsigned value) { now += value; }
};
int main() {
  Controller eight_bit = {false, -1};
  hd44780::initialize(eight_bit);
  assert(eight_bit.four_bit && eight_bit.high < 0 && eight_bit.two_lines &&
         eight_bit.display && eight_bit.increment && eight_bit.clears == 1);
  for (int pending = -1; pending < 16; ++pending) {
    Controller warm = {true, pending};
    hd44780::initialize(warm);
    assert(warm.four_bit && warm.high < 0 && warm.two_lines && warm.display &&
           warm.increment && warm.clears >= 1);
  }
}
