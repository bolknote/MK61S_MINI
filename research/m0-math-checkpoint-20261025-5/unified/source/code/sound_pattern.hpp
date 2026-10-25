#ifndef MK61_SOUND_PATTERN_HPP
#define MK61_SOUND_PATTERN_HPP
#include "rust_types.h"

// Асинхронный звуковой паттерн (команда beep): частота 0 - пауза.
// Узкие типы намеренно: буфер паттерна живёт в ОЗУ постоянно (8 байт на ноту
// вместо 16), а 65 кГц / 65 с на ноту хватает с запасом.
struct SoundNote {
  u16 frequency_Hz;
  u16 duration_ms;
  u16 gap_ms;
  u8  volume_percent;
};
static constexpr usize SOUND_PATTERN_MAX = 16;
extern  bool  sound_pattern_start(const SoundNote* notes, usize count);

#endif
