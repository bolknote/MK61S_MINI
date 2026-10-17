#include "input.hpp"
#include "cross_hal.h"
#include "keyboard_core.hpp"
#include "keyboard_layout.hpp"
#include "loadable_app_api.h"
#include <cstring>
namespace picocalc {
namespace controls {
namespace {
u8 held[2][32]{};
u32 pulse_until[256]{};
} // namespace
void clear() {
  std::memset(held, 0, sizeof(held));
  std::memset(pulse_until, 0, sizeof(pulse_until));
}
void event(KeyEvent e, Source source) {
  if (!e.code || e.state < 1 || e.state > 3)
    return;
  u8 &byte = held[(unsigned)source][e.code / 8];
  const u8 bit = (u8)(1U << (e.code % 8));
  if (e.state == 3)
    byte &= (u8)~bit;
  else
    byte |= bit;
}
void pulse(u8 code, u32 now) { pulse_until[code] = now + 180; }
bool pressed(u8 code, u32 now) {
  const u8 bit = (u8)(1U << (code % 8));
  return ((held[0][code / 8] | held[1][code / 8]) & bit) ||
         (pulse_until[code] && (i32)(pulse_until[code] - now) > 0);
}
int scan(u8 code) {
  const auto key = map_key(code);
  for (unsigned i = 0; i < sizeof(KeyPairs) / sizeof(KeyPairs[0]); ++i)
    if (key.valid() && key.angle == NONE && KeyPairs[i].x == key.x &&
        KeyPairs[i].y == key.y)
      return (int)i;
  return -1;
}
int logical(u8 c) {
  if (c >= '0' && c <= '9')
    return c - '0';
  switch (c) {
  case '.':
  case ',':
    return MK61_APP_KEY_DECIMAL;
  case '+':
    return MK61_APP_KEY_ADD;
  case '-':
    return MK61_APP_KEY_SUBTRACT;
  case '*':
    return MK61_APP_KEY_MULTIPLY;
  case '/':
    return MK61_APP_KEY_DIVIDE;
  case 0xB4:
    return MK61_APP_KEY_LEFT;
  case 0xB7:
    return MK61_APP_KEY_RIGHT;
  case 0xB5:
    return MK61_APP_KEY_BACKWARD;
  case 0xB6:
    return MK61_APP_KEY_FORWARD;
  case '\r':
  case '\n':
    return MK61_APP_KEY_OK;
  case 0x1B:
  case 0xB1:
    return MK61_APP_KEY_ESC;
  case 8:
    return MK61_APP_KEY_CLEAR;
  }
  const int s = scan(c);
  return s >= 0 ? keyboard_layout::logical_key(keyboard_layout::ACTIVE, s)
                : MK61_APP_KEY_RAW_BASE + c;
}
u8 from_scan(unsigned s) {
  // Preserve MINI's wire keyboard layout, including menu/step keys.
  if (s >= keyboard_core::KEY_COUNT)
    return 0;
  const int key = keyboard_layout::logical_key(keyboard_layout::ACTIVE, (i32)s);
  if (key >= 0 && key <= 9)
    return (u8)('0' + key);
  switch (key) {
  case MK61_APP_KEY_LEFT:
    return 0xB4;
  case MK61_APP_KEY_RIGHT:
    return 0xB7;
  case MK61_APP_KEY_SHIFT_LEFT:
    return 0xB5;
  case MK61_APP_KEY_SHIFT_RIGHT:
    return 0xB6;
  case MK61_APP_KEY_OK:
    return '\r';
  case MK61_APP_KEY_ESC:
    return 0x1B;
  case MK61_APP_KEY_DECIMAL:
    return '.';
  case MK61_APP_KEY_ADD:
    return '+';
  case MK61_APP_KEY_SUBTRACT:
    return '-';
  case MK61_APP_KEY_MULTIPLY:
    return '*';
  case MK61_APP_KEY_DIVIDE:
    return '/';
  case MK61_APP_KEY_RUN:
    return 0x83;
  case MK61_APP_KEY_CLEAR:
    return 8;
  case MK61_APP_KEY_K:
    return 0x82;
  case MK61_APP_KEY_F:
    return 0x81;
  case MK61_APP_KEY_USER:
    return '\t';
  case MK61_APP_KEY_PP:
    return 'C';
  case MK61_APP_KEY_BP:
    return 'G';
  case MK61_APP_KEY_X_TO_P:
    return 'S';
  case MK61_APP_KEY_P_TO_X:
    return 'L';
  case MK61_APP_KEY_RETURN:
    return 'B';
  case MK61_APP_KEY_FORWARD:
    return 0xD7;
  case MK61_APP_KEY_BACKWARD:
    return 0xD6;
  default:
    break;
  }
  for (unsigned c = 32; c < 256; ++c)
    if (scan((u8)c) == (int)s)
      return (u8)c;
  return 0;
}
u16 chip8_keys(u32 now) {
  static const char keys[] = "x123qweasdzc4rfv";
  u16 mask = 0;
  for (unsigned i = 0; i < 16; ++i)
    if (pressed((u8)keys[i], now) ||
        pressed((u8)(keys[i] >= 'a' && keys[i] <= 'z' ? keys[i] - 32 : keys[i]),
                now))
      mask |= (u16)(1U << i);
  for (unsigned i = 0; i < 10; ++i)
    if (i == 0 || i >= 5)
      if (pressed((u8)('0' + i), now))
        mask |= (u16)(1U << i);
  const u8 arrows[] = {0xB4, 0xB7, 0xB5, 0xB6, '\r', '\n'};
  const u8 hex[] = {4, 6, 2, 8, 5, 5};
  for (unsigned i = 0; i < 6; ++i)
    if (pressed(arrows[i], now))
      mask |= (u16)(1U << hex[i]);
  return mask;
}
} // namespace controls
} // namespace picocalc
