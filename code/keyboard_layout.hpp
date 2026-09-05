#ifndef MK61_KEYBOARD_LAYOUT_HPP
#define MK61_KEYBOARD_LAYOUT_HPP

#include "rust_types.h"
#include "loadable_system_api.h"

namespace keyboard_layout {

// Физические scan-коды матрицы занимают диапазон 0..39. Байтовое хранение
// экономит по 126 байт в resident и в каждом языковом APP без изменения
// публичных i32-кодов клавиатурного API.
using Mapping = mk61_system_keyboard;

static_assert(sizeof(Mapping) == 42,
              "keyboard mapping must remain a compact scan-code table");

static constexpr Mapping MINI = {
  0, 1, 2, 3, 5, 6, 7, 8, 10, 15,
  {20, 21, 16, 11, 22, 17, 12, 23, 18, 13},
  25, 26, 27, 28, 30, 31, 32, 33, 37, 38,
  4, 9, 14, 19, 36, 35, 34, 24, 29, 39, 32, 33
};

static constexpr Mapping CLASSIC = {
  0, 5, 10, 15, 1, 6, 11, 16, 2, 3,
  {4, 9, 8, 7, 14, 13, 12, 19, 18, 17},
  20, 21, 22, 23, 25, 26, 28, 27, 24, 29,
  30, 31, 32, 35, 34, 33, 38, 36, 37, 39, 27, 28
};

// Плата 40TH использует ту же физическую матрицу 5x8, что и mk61s-mini.
// Для преобразования клавиш калькулятора также применяется таблица mini
// из cross_hal.cpp.
static constexpr Mapping FORTIETH = MINI;

#if defined(MK61_KEYBOARD_CLASSIC)
static constexpr Mapping ACTIVE = CLASSIC;
#elif defined(MK61_KEYBOARD_40TH)
static constexpr Mapping ACTIVE = FORTIETH;
#else
static constexpr Mapping ACTIVE = MINI;
#endif

static_assert(MINI.k != MINI.right, "mini K and Right must be distinct");
static_assert(MINI.alpha != MINI.ok, "mini F and OK must be distinct");
static_assert(CLASSIC.k != CLASSIC.right, "classic K and Right must be distinct");
static_assert(CLASSIC.alpha != CLASSIC.ok, "classic F and OK must be distinct");
static_assert(FORTIETH.k != FORTIETH.right, "40TH K and Right must be distinct");
static_assert(FORTIETH.alpha != FORTIETH.ok, "40TH F and OK must be distinct");

#if defined(MK61_BUILD_PORTABLE_SYSTEM)
const Mapping& active();
#else
constexpr const Mapping& active() { return ACTIVE; }
#endif

inline int digit_from_key(const Mapping& mapping, i32 key_code) {
  for(int digit = 0; digit <= 9; digit++) {
    if(key_code == mapping.digit[digit]) return digit;
  }
  return -1;
}

} // пространство имён keyboard_layout

#endif
