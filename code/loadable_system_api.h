#ifndef MK61_LOADABLE_SYSTEM_API_H
#define MK61_LOADABLE_SYSTEM_API_H

#include "loadable_app_api.h"
#include <stdbool.h>
#include <stdarg.h>

/* System APP services are a separate, versioned C ABI. No resident C++
 * objects, enum layouts or symbol addresses occur in the wire structures. */
#define MK61_SYSTEM_API_MAGIC 0x31535953UL
#define MK61_SYSTEM_API_VERSION 1U
#define MK61_SYSTEM_MAX_ROWS 10U
#define MK61_SYSTEM_LEASE_BYTES 32U

enum mk61_system_operation {
  MK61_SYS_DISPLAY = 1, MK61_SYS_KEYBOARD, MK61_SYS_SETTINGS,
  MK61_SYS_RANDOM, MK61_SYS_MICROS, MK61_SYS_FILE_COUNT,
  MK61_SYS_FILE_ENTRY, MK61_SYS_FILE_RESOLVE, MK61_SYS_FILE_WRITE,
  MK61_SYS_FILE_REMOVE, MK61_SYS_FILE_CHOOSE, MK61_SYS_FILE_SAVE_TARGET,
  MK61_SYS_MEMORY_ACQUIRE, MK61_SYS_MEMORY_RELEASE, MK61_SYS_MEMORY_DATA,
  MK61_SYS_TEXT_ROWS, MK61_SYS_EDITOR_DRAW, MK61_SYS_EDITOR_SCROLL,
  MK61_SYS_MENU, MK61_SYS_FONT, MK61_SYS_REF_READ, MK61_SYS_REF_WRITE,
  MK61_SYS_FILE_EXISTS, MK61_SYS_EDITOR_KEY, MK61_SYS_SETUP
};
enum mk61_system_display_operation {
  MK61_SYS_DISPLAY_CLEAR, MK61_SYS_DISPLAY_CURSOR, MK61_SYS_DISPLAY_WRITE,
  MK61_SYS_DISPLAY_PRINT, MK61_SYS_DISPLAY_CURSOR_ON,
  MK61_SYS_DISPLAY_CURSOR_OFF, MK61_SYS_DISPLAY_SUPPORTS_CURSOR,
  MK61_SYS_DISPLAY_FLUSH, MK61_SYS_DISPLAY_BEGIN_UPDATE,
  MK61_SYS_DISPLAY_END_UPDATE, MK61_SYS_DISPLAY_END_VIEWPORT,
  MK61_SYS_DISPLAY_GRAPHICS, MK61_SYS_DISPLAY_WIDTH, MK61_SYS_DISPLAY_HEIGHT,
  MK61_SYS_DISPLAY_GRAPHICS_MODE
};
enum mk61_system_keyboard_operation {
  MK61_SYS_KEY_POLL, MK61_SYS_KEY_GET, MK61_SYS_KEY_WAIT,
  MK61_SYS_KEY_PRESSED, MK61_SYS_KEY_IMMEDIATE, MK61_SYS_KEY_CLEAR_IMMEDIATE,
  MK61_SYS_KEY_SCAN, MK61_SYS_KEY_HANDOFF, MK61_SYS_KEY_HANDOFF_PENDING,
  MK61_SYS_KEY_ANY, MK61_SYS_KEY_CLEAR_HOLD, MK61_SYS_KEY_LAST
};
enum mk61_system_setting { MK61_SYS_LANGUAGE, MK61_SYS_VOLUME,
                           MK61_SYS_ANGLE, MK61_SYS_REGISTER_F };
enum mk61_system_math_operation { MK61_SYS_SIN, MK61_SYS_COS, MK61_SYS_TAN,
  MK61_SYS_ASIN, MK61_SYS_ACOS, MK61_SYS_ATAN, MK61_SYS_LN, MK61_SYS_LOG10,
  MK61_SYS_EXP, MK61_SYS_SQRT, MK61_SYS_POW };

/* SETUP service v1. Explicit C fields, no native C++ layouts. */
enum mk61_setup_operation {
  MK61_SETUP_VERSION, MK61_SETUP_HARDWARE, MK61_SETUP_RTC_READ,
  MK61_SETUP_RTC_WRITE, MK61_SETUP_RTC_CALIBRATION, MK61_SETUP_FONT_READ,
  MK61_SETUP_FONT_APPLY, MK61_SETUP_FONT_PREVIEW, MK61_SETUP_FONT_PREVIEW_END,
  MK61_SETUP_LCD_CHAR, MK61_SETUP_FONT_RESTORE, MK61_SETUP_TEXT,
  MK61_SETUP_PHASE, MK61_SETUP_FEATURES
};
typedef struct mk61_setup_datetime {
  uint32_t year, month, day, hour, minute, second;
} mk61_setup_datetime;
typedef struct mk61_setup_hardware {
  uint32_t idcode, flash_kb, pin_code, valid, vdda, vbat;
  int32_t temperature;
  uint32_t battery_presence, battery_reason;
  char rtc_source[4], display[16];
} mk61_setup_hardware;
typedef struct mk61_setup_profile { uint8_t rows, width, height, gap; } mk61_setup_profile;

typedef struct mk61_system_file {
  uint32_t id, parent, size, type, kind;
  char name[32];
} mk61_system_file;
typedef struct mk61_system_write {
  const char* name;
  const uint8_t* data;
  uint32_t size, id;
} mk61_system_write;
typedef struct mk61_system_choice {
  mk61_system_file file;
  uint32_t parent;
} mk61_system_choice;
typedef struct mk61_system_save_target {
  char* name;
  uint32_t parent;
} mk61_system_save_target;
typedef struct mk61_system_lease {
  /* Opaque resident-owned storage, aligned for any supported native lease. */
  uint64_t opaque[MK61_SYSTEM_LEASE_BYTES / 8];
  uint8_t* data;
  uint32_t size, fresh, image_crc;
} mk61_system_lease;
typedef struct mk61_system_editor {
  const char* source;
  uint32_t length, cursor, top, sms;
} mk61_system_editor;
typedef struct mk61_system_menu_item {
  const char* text;
  bool (*action)(void);
  uint32_t display_size;
} mk61_system_menu_item;
typedef struct mk61_system_glyph {
  uint32_t width, height;
  uint8_t pixels[8]; /* canonical row-major MSB, at most 8x8 */
} mk61_system_glyph;

typedef struct mk61_system_edit_hook {
  char* source;
  uint32_t length, cursor, capacity, shift;
  int32_t key, delta;
  void* context;
} mk61_system_edit_hook;
enum mk61_system_edit_hook_operation {
  MK61_EDIT_INSERT, MK61_EDIT_ALPHA, MK61_EDIT_MOVE, MK61_EDIT_BACKSPACE
};
typedef struct mk61_system_edit_key {
  char* source;
  uint32_t capacity, length, cursor, top, shift;
  uint32_t sms_active, sms_index, sms_deadline;
  int32_t sms_key;
  int32_t keys[13]; /* left/press, right/press, ok/press, esc/press, step L/R, K, alpha, PP */
  const char* ok_text;
  uint32_t options; /* SMS=1, alpha symbols=2, alpha clear line=4 */
  int32_t backspace_key, key;
  uint32_t now, hook_mask;
  uint32_t (*hook)(uint32_t operation, mk61_system_edit_hook* event);
  void* context;
} mk61_system_edit_key;

typedef struct mk61_system_keyboard {
  uint8_t cx, bx, mul, div, power, xy, add, sub, neg, dot;
  uint8_t digit[10];
  uint8_t pp, bp, x_to_p, p_to_x, run, ret, frw, bkw, k, alpha;
  uint8_t degree, grade, radian, user, save, load;
  uint8_t left, right, ok, esc, shg_left, shg_right;
} mk61_system_keyboard;

/* Standard compiler helpers use their ARM EABI calling convention; string
 * functions use ISO C/AAPCS. See loadable_system_runtime.def for slot order. */
typedef void (*mk61_system_runtime_function)(void);
enum mk61_system_runtime_slot {
#define MK61_RUNTIME(name) MK61_RUNTIME_SLOT_##name,
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
  MK61_RUNTIME_COUNT
};

typedef struct mk61_system_api {
  uint32_t magic;
  uint16_t version, struct_size;
  const mk61_system_keyboard* keyboard_mapping;
  uint32_t (*call)(uint32_t operation, uint32_t a, uint32_t b,
                   uint32_t c, void* payload);
  double (*math)(uint32_t operation, double x, double y);
  int (*format)(char* output, uint32_t size, const char* format, va_list args);
  const mk61_system_runtime_function* runtime;
} mk61_system_api;

#endif
