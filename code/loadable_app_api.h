#ifndef MK61_LOADABLE_APP_API_H
#define MK61_LOADABLE_APP_API_H

/* The public C ABI. Keep existing fields and enum values unchanged; append
 * new callbacks and check struct_size/capabilities before using them. */
#include <stddef.h>
#include <stdint.h>

#define MK61_APP_API_MAGIC 0x31505041UL
#define MK61_APP_API_VERSION 1U
#define MK61_APP_MAX_TEXT_BYTES 63U

enum mk61_app_capability {
  MK61_APP_CAP_TIME = 1U << 0,
  MK61_APP_CAP_TEXT_DISPLAY = 1U << 1,
  MK61_APP_CAP_KEYBOARD = 1U << 2,
  MK61_APP_CAP_LED = 1U << 3,
  MK61_APP_CAP_SOUND = 1U << 4,
  MK61_APP_CAP_FILES = 1U << 5,
  MK61_APP_CAP_GRAPHICS = 1U << 6,
  MK61_APP_CAP_KEY_STATE = 1U << 7
};

enum mk61_app_key {
  MK61_APP_KEY_NONE = -1,
  MK61_APP_KEY_DIGIT_0 = 0,
  MK61_APP_KEY_DIGIT_1,
  MK61_APP_KEY_DIGIT_2,
  MK61_APP_KEY_DIGIT_3,
  MK61_APP_KEY_DIGIT_4,
  MK61_APP_KEY_DIGIT_5,
  MK61_APP_KEY_DIGIT_6,
  MK61_APP_KEY_DIGIT_7,
  MK61_APP_KEY_DIGIT_8,
  MK61_APP_KEY_DIGIT_9,
  MK61_APP_KEY_DECIMAL,
  MK61_APP_KEY_ADD,
  MK61_APP_KEY_SUBTRACT,
  MK61_APP_KEY_MULTIPLY,
  MK61_APP_KEY_DIVIDE,
  MK61_APP_KEY_LEFT,
  MK61_APP_KEY_RIGHT,
  MK61_APP_KEY_SHIFT_LEFT,
  MK61_APP_KEY_SHIFT_RIGHT,
  MK61_APP_KEY_OK,
  MK61_APP_KEY_ESC,
  MK61_APP_KEY_RUN,
  MK61_APP_KEY_CLEAR,
  MK61_APP_KEY_K,
  MK61_APP_KEY_F,
  MK61_APP_KEY_USER,
  MK61_APP_KEY_PP,
  MK61_APP_KEY_BP,
  MK61_APP_KEY_X_TO_P,
  MK61_APP_KEY_P_TO_X,
  MK61_APP_KEY_RETURN,
  MK61_APP_KEY_FORWARD,
  MK61_APP_KEY_BACKWARD,
  MK61_APP_KEY_RAW_BASE = 0x100
};

typedef struct mk61_app_api {
  uint32_t magic;
  uint16_t version;
  uint16_t struct_size;
  uint32_t capabilities;

  uint32_t (*millis_ms)(void);
  void (*service)(void);
  void (*delay_ms)(uint32_t duration_ms);

  uint32_t (*display_columns)(void);
  uint32_t (*display_rows)(void);
  uint32_t (*display_clear)(void);
  uint32_t (*display_write_utf8)(uint32_t column, uint32_t row,
                            const char* text, uint32_t byte_length);

  int32_t (*key_poll)(void);
  int32_t (*key_wait)(void);

  void (*led_set)(uint32_t enabled);
  uint32_t (*led_blink)(uint32_t count, uint32_t on_ms, uint32_t off_ms);

  uint32_t (*beep)(uint32_t frequency_hz, uint32_t duration_ms, uint32_t volume_percent);
  void (*sound_stop)(void);

  // Расширение ABI v1: старые APP видят прежний 64-байтовый префикс,
  // новые проверяют struct_size перед использованием хвоста.
  uint32_t (*file_size)(uint32_t file_id);
  uint32_t (*file_read)(uint32_t file_id, uint32_t offset, uint8_t* output, uint32_t length);

  uint32_t (*graphics_available)(void);
  uint32_t (*graphics_width)(void);
  uint32_t (*graphics_height)(void);
  uint32_t (*graphics_revision)(void);
  uint32_t (*graphics_begin)(void);
  uint32_t (*graphics_present)(const uint8_t* bitmap, uint32_t size);
  void (*graphics_end)(void);

  uint32_t (*key_pressed)(int32_t key);
} mk61_app_api;

static inline int mk61_app_api_compatible(const mk61_app_api* api,
                                          uint16_t required_size,
                                          uint32_t capabilities) {
  return api != NULL && api->magic == MK61_APP_API_MAGIC &&
      api->version == MK61_APP_API_VERSION &&
      api->struct_size >= required_size &&
      (api->capabilities & capabilities) == capabilities;
}

#endif
