#ifndef MK61_LOADABLE_APP_API_HPP
#define MK61_LOADABLE_APP_API_HPP

#include "rust_types.h"
#include "loadable_app_api.h"

namespace loadable_app {

// Таблица передаётся пользовательскому APPLICATION через argument0 команд
// INITIALIZE и APPLICATION_RUN. Все поля имеют фиксированные 32-битные
// аргументы; новые callbacks можно добавлять только в конец структуры.
static constexpr u32 API_MAGIC = MK61_APP_API_MAGIC; // "APP1" little-endian
static constexpr u16 API_VERSION = MK61_APP_API_VERSION;
static constexpr u32 MAX_TEXT_BYTES = MK61_APP_MAX_TEXT_BYTES;

enum Capability : u32 {
  CAP_TIME = MK61_APP_CAP_TIME,
  CAP_TEXT_DISPLAY = MK61_APP_CAP_TEXT_DISPLAY,
  CAP_KEYBOARD = MK61_APP_CAP_KEYBOARD,
  CAP_LED = MK61_APP_CAP_LED,
  CAP_SOUND = MK61_APP_CAP_SOUND,
  CAP_FILES = MK61_APP_CAP_FILES,
  CAP_GRAPHICS = MK61_APP_CAP_GRAPHICS,
  CAP_KEY_STATE = MK61_APP_CAP_KEY_STATE
};

// Независимые от физической раскладки логические коды. Неизвестная клавиша
// возвращается как KEY_RAW_BASE + её scan code и поэтому не теряется.
enum Key : i32 {
  KEY_NONE = MK61_APP_KEY_NONE,
  KEY_DIGIT_0 = MK61_APP_KEY_DIGIT_0,
  KEY_DIGIT_1 = MK61_APP_KEY_DIGIT_1,
  KEY_DIGIT_2 = MK61_APP_KEY_DIGIT_2,
  KEY_DIGIT_3 = MK61_APP_KEY_DIGIT_3,
  KEY_DIGIT_4 = MK61_APP_KEY_DIGIT_4,
  KEY_DIGIT_5 = MK61_APP_KEY_DIGIT_5,
  KEY_DIGIT_6 = MK61_APP_KEY_DIGIT_6,
  KEY_DIGIT_7 = MK61_APP_KEY_DIGIT_7,
  KEY_DIGIT_8 = MK61_APP_KEY_DIGIT_8,
  KEY_DIGIT_9 = MK61_APP_KEY_DIGIT_9,
  KEY_DECIMAL = MK61_APP_KEY_DECIMAL,
  KEY_ADD = MK61_APP_KEY_ADD,
  KEY_SUBTRACT = MK61_APP_KEY_SUBTRACT,
  KEY_MULTIPLY = MK61_APP_KEY_MULTIPLY,
  KEY_DIVIDE = MK61_APP_KEY_DIVIDE,
  KEY_LEFT = MK61_APP_KEY_LEFT,
  KEY_RIGHT = MK61_APP_KEY_RIGHT,
  KEY_SHIFT_LEFT = MK61_APP_KEY_SHIFT_LEFT,
  KEY_SHIFT_RIGHT = MK61_APP_KEY_SHIFT_RIGHT,
  KEY_OK = MK61_APP_KEY_OK,
  KEY_ESC = MK61_APP_KEY_ESC,
  KEY_RUN = MK61_APP_KEY_RUN,
  KEY_CLEAR = MK61_APP_KEY_CLEAR,
  KEY_K = MK61_APP_KEY_K,
  KEY_F = MK61_APP_KEY_F,
  KEY_USER = MK61_APP_KEY_USER,
  KEY_PP = MK61_APP_KEY_PP,
  KEY_BP = MK61_APP_KEY_BP,
  KEY_X_TO_P = MK61_APP_KEY_X_TO_P,
  KEY_P_TO_X = MK61_APP_KEY_P_TO_X,
  KEY_RETURN = MK61_APP_KEY_RETURN,
  KEY_FORWARD = MK61_APP_KEY_FORWARD,
  KEY_BACKWARD = MK61_APP_KEY_BACKWARD,
  KEY_RAW_BASE = MK61_APP_KEY_RAW_BASE
};

using Api = mk61_app_api;

static_assert(sizeof(void*) != 4 ||
              __builtin_offsetof(Api, file_size) == 64,
              "loadable APP API v1 must retain its 64-byte ARM ABI prefix");

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
