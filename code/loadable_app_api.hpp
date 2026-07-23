#ifndef MK61_LOADABLE_APP_API_HPP
#define MK61_LOADABLE_APP_API_HPP

#include "rust_types.h"
#include <stdint.h>

namespace loadable_app {

// Таблица передаётся пользовательскому APPLICATION через argument0 команд
// INITIALIZE и APPLICATION_RUN. Все поля имеют фиксированные 32-битные
// аргументы; новые callbacks можно добавлять только в конец структуры.
static constexpr u32 API_MAGIC = 0x31505041UL; // "APP1" little-endian
static constexpr u16 API_VERSION = 1;
static constexpr u32 MAX_TEXT_BYTES = 63;

enum Capability : u32 {
  CAP_TIME = 1U << 0,
  CAP_TEXT_DISPLAY = 1U << 1,
  CAP_KEYBOARD = 1U << 2,
  CAP_LED = 1U << 3,
  CAP_SOUND = 1U << 4
};

// Независимые от физической раскладки логические коды. Неизвестная клавиша
// возвращается как KEY_RAW_BASE + её scan code и поэтому не теряется.
enum Key : i32 {
  KEY_NONE = -1,
  KEY_DIGIT_0 = 0,
  KEY_DIGIT_1,
  KEY_DIGIT_2,
  KEY_DIGIT_3,
  KEY_DIGIT_4,
  KEY_DIGIT_5,
  KEY_DIGIT_6,
  KEY_DIGIT_7,
  KEY_DIGIT_8,
  KEY_DIGIT_9,
  KEY_DECIMAL,
  KEY_ADD,
  KEY_SUBTRACT,
  KEY_MULTIPLY,
  KEY_DIVIDE,
  KEY_LEFT,
  KEY_RIGHT,
  KEY_SHIFT_LEFT,
  KEY_SHIFT_RIGHT,
  KEY_OK,
  KEY_ESC,
  KEY_RUN,
  KEY_CLEAR,
  KEY_K,
  KEY_F,
  KEY_USER,
  KEY_PP,
  KEY_BP,
  KEY_X_TO_P,
  KEY_P_TO_X,
  KEY_RETURN,
  KEY_FORWARD,
  KEY_BACKWARD,
  KEY_RAW_BASE = 0x100
};

struct Api {
  u32 magic;
  u16 version;
  u16 struct_size;
  u32 capabilities;

  u32 (*millis_ms)(void);
  void (*service)(void);
  void (*delay_ms)(u32 duration_ms);

  u32 (*display_columns)(void);
  u32 (*display_rows)(void);
  u32 (*display_clear)(void);
  u32 (*display_write_utf8)(u32 column, u32 row,
                            const char* text, u32 byte_length);

  i32 (*key_poll)(void);
  i32 (*key_wait)(void);

  void (*led_set)(u32 enabled);
  u32 (*led_blink)(u32 count, u32 on_ms, u32 off_ms);

  u32 (*beep)(u32 frequency_hz, u32 duration_ms, u32 volume_percent);
  void (*sound_stop)(void);
};

static_assert(sizeof(void*) != 4 || sizeof(Api) == 64,
              "loadable APP API v1 must remain a 64-byte ARM ABI prefix");

inline const Api* from_argument(u32 argument0) {
  return (const Api*) (uintptr_t) argument0;
}

inline bool compatible(const Api* api) {
  return api != nullptr && api->magic == API_MAGIC &&
         api->version == API_VERSION && api->struct_size >= sizeof(Api);
}

// Доступ только со стороны resident. APP получает указатель через аргументы
// точки входа и не должен напрямую линковать этот символ.
const Api& resident_api(void);

} // namespace loadable_app

#endif
