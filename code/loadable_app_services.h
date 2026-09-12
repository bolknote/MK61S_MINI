#ifndef MK61_LOADABLE_APP_SERVICES_H
#define MK61_LOADABLE_APP_SERVICES_H

#include "loadable_app_api.h"
#include <stdbool.h>
#include <stdarg.h>

/* Optional public services, obtained through mk61_app_api.query_service.
 * Wire layouts and numbers retain the former System API v1 prefix. */
#define MK61_APP_SERVICES_MAGIC 0x31535953UL
#define MK61_APP_SERVICES_VERSION 1U
#define MK61_SERVICE_MAX_ROWS 10U
#define MK61_SERVICE_LEASE_BYTES 32U

#define MK61_APP_SERVICE_COMMON 1U

enum mk61_service_capability {
  MK61_SERVICE_CAP_UI = 1U << 0,
  MK61_SERVICE_CAP_FILES = 1U << 1,
  MK61_SERVICE_CAP_DIALOGS = 1U << 2,
  MK61_SERVICE_CAP_MEMORY = 1U << 3,
  MK61_SERVICE_CAP_EDITOR = 1U << 4,
  MK61_SERVICE_CAP_FONT = 1U << 5,
  MK61_SERVICE_CAP_REGISTERS = 1U << 6,
  MK61_SERVICE_CAP_MATH = 1U << 7,
  MK61_SERVICE_CAP_RUNTIME = 1U << 8,
  MK61_SERVICE_CAP_SETUP = 1U << 9,
  MK61_SERVICE_CAP_FORMAT = 1U << 10,
  MK61_SERVICE_CAP_UI_FONT = 1U << 11
};
enum mk61_service_memory_arena {
  MK61_SERVICE_WORKSPACE = 0, MK61_SERVICE_SCRATCH = 1
};
/* Application owner; the other values are reserved for legacy adapters. */
#define MK61_SERVICE_OWNER_APP 4U

#define MK61_SERVICE_ROOT_ID 0xFFFFU
#define MK61_SERVICE_INVALID_ID 0xFFFFU
enum mk61_service_file_type {
  MK61_SERVICE_FILE_MK61 = 0, MK61_SERVICE_FILE_FOCAL = 2,
  MK61_SERVICE_FILE_BASIC = 3, MK61_SERVICE_FILE_TEXT = 4,
  MK61_SERVICE_FILE_STATE = 5, MK61_SERVICE_FILE_FONT = 6,
  MK61_SERVICE_FILE_WBMP = 7, MK61_SERVICE_FILE_APP = 8,
  MK61_SERVICE_FILE_CHIP8 = 9, MK61_SERVICE_FILE_MARKDOWN = 10
};
enum mk61_service_ref_kind {
  MK61_SERVICE_REF_X = 0, MK61_SERVICE_REF_Y, MK61_SERVICE_REF_Z,
  MK61_SERVICE_REF_T, MK61_SERVICE_REF_R
};

enum mk61_service_operation {
  MK61_SERVICE_DISPLAY = 1, MK61_SERVICE_KEYBOARD, MK61_SERVICE_SETTINGS,
  MK61_SERVICE_RANDOM, MK61_SERVICE_MICROS, MK61_SERVICE_FILE_COUNT,
  MK61_SERVICE_FILE_ENTRY, MK61_SERVICE_FILE_RESOLVE, MK61_SERVICE_FILE_WRITE,
  MK61_SERVICE_FILE_REMOVE, MK61_SERVICE_FILE_CHOOSE, MK61_SERVICE_FILE_SAVE_TARGET,
  MK61_SERVICE_MEMORY_ACQUIRE, MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_MEMORY_DATA,
  MK61_SERVICE_TEXT_ROWS, MK61_SERVICE_EDITOR_DRAW, MK61_SERVICE_EDITOR_SCROLL,
  MK61_SERVICE_MENU, MK61_SERVICE_FONT, MK61_SERVICE_REF_READ, MK61_SERVICE_REF_WRITE,
  MK61_SERVICE_FILE_EXISTS, MK61_SERVICE_EDITOR_KEY, MK61_SERVICE_SETUP,
  MK61_SERVICE_CAPABILITIES,
  MK61_SERVICE_UI_FONT
};
enum mk61_service_display_operation {
  MK61_SERVICE_DISPLAY_CLEAR, MK61_SERVICE_DISPLAY_CURSOR, MK61_SERVICE_DISPLAY_WRITE,
  MK61_SERVICE_DISPLAY_PRINT, MK61_SERVICE_DISPLAY_CURSOR_ON,
  MK61_SERVICE_DISPLAY_CURSOR_OFF, MK61_SERVICE_DISPLAY_SUPPORTS_CURSOR,
  MK61_SERVICE_DISPLAY_FLUSH, MK61_SERVICE_DISPLAY_BEGIN_UPDATE,
  MK61_SERVICE_DISPLAY_END_UPDATE, MK61_SERVICE_DISPLAY_END_VIEWPORT,
  MK61_SERVICE_DISPLAY_GRAPHICS, MK61_SERVICE_DISPLAY_WIDTH, MK61_SERVICE_DISPLAY_HEIGHT,
  MK61_SERVICE_DISPLAY_GRAPHICS_MODE,
  // Explicitly select the established cell renderer before language output.
  // Old residents safely ignore this append-only operation (they have no UI role).
  MK61_SERVICE_DISPLAY_END_UI_TEXT
};
enum mk61_service_keyboard_operation {
  MK61_SERVICE_KEY_POLL, MK61_SERVICE_KEY_GET, MK61_SERVICE_KEY_WAIT,
  MK61_SERVICE_KEY_PRESSED, MK61_SERVICE_KEY_IMMEDIATE, MK61_SERVICE_KEY_CLEAR_IMMEDIATE,
  MK61_SERVICE_KEY_SCAN, MK61_SERVICE_KEY_HANDOFF, MK61_SERVICE_KEY_HANDOFF_PENDING,
  MK61_SERVICE_KEY_ANY, MK61_SERVICE_KEY_CLEAR_HOLD, MK61_SERVICE_KEY_LAST
};
enum mk61_service_setting { MK61_SERVICE_LANGUAGE, MK61_SERVICE_VOLUME,
                           MK61_SERVICE_ANGLE, MK61_SERVICE_REGISTER_F };
enum mk61_service_math_operation { MK61_SERVICE_SIN, MK61_SERVICE_COS, MK61_SERVICE_TAN,
  MK61_SERVICE_ASIN, MK61_SERVICE_ACOS, MK61_SERVICE_ATAN, MK61_SERVICE_LN, MK61_SERVICE_LOG10,
  MK61_SERVICE_EXP, MK61_SERVICE_SQRT, MK61_SERVICE_POW };

/* SETUP service v1. Explicit C fields, no native C++ layouts. */
enum mk61_setup_operation {
  MK61_SETUP_VERSION, MK61_SETUP_HARDWARE, MK61_SETUP_RTC_READ,
  MK61_SETUP_RTC_WRITE, MK61_SETUP_RTC_CALIBRATION, MK61_SETUP_FONT_READ,
  MK61_SETUP_FONT_APPLY, MK61_SETUP_FONT_PREVIEW, MK61_SETUP_FONT_PREVIEW_END,
  MK61_SETUP_LCD_CHAR, MK61_SETUP_FONT_RESTORE, MK61_SETUP_TEXT,
  MK61_SETUP_PHASE, MK61_SETUP_FEATURES,
  MK61_SETUP_UI_FONT_READ, MK61_SETUP_UI_FONT_APPLY,
  MK61_SETUP_TEXT_MODE,
  MK61_SETUP_UI_FONT_COUNT, MK61_SETUP_UI_FONT_ITEM,
  MK61_SETUP_UI_FONT_CURRENT, MK61_SETUP_UI_FONT_APPLY_ITEM,
  MK61_SETUP_UI_FONT_STEP
};
enum mk61_setup_feature {
  MK61_SETUP_FEATURE_TEXT_PROFILE = 1u << 0,
  MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE = 1u << 1,
  MK61_SETUP_FEATURE_UI_FONT = 1u << 2,
  MK61_SETUP_FEATURE_UI_TEXT_MODE = 1u << 3,
  MK61_SETUP_FEATURE_FIXED_CALCULATOR_FACE = 1u << 4,
  MK61_SETUP_FEATURE_UI_FONT_CATALOG = 1u << 5
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
typedef struct mk61_setup_ui_font { uint8_t family, size; } mk61_setup_ui_font;
typedef struct mk61_setup_ui_font_item {
  uint32_t key;
  uint8_t size, reserved[3];
  char name[32];
} mk61_setup_ui_font_item;

typedef struct mk61_service_file {
  uint32_t id, parent, size, type, kind;
  char name[32];
} mk61_service_file;
typedef struct mk61_service_write {
  const char* name;
  const uint8_t* data;
  uint32_t size, id;
} mk61_service_write;
typedef struct mk61_service_choice {
  mk61_service_file file;
  uint32_t parent;
} mk61_service_choice;
typedef struct mk61_service_save_target {
  char* name;
  uint32_t parent;
} mk61_service_save_target;
typedef struct mk61_service_lease {
  /* Opaque resident-owned storage, aligned for any supported native lease. */
  uint64_t opaque[MK61_SERVICE_LEASE_BYTES / 8];
  uint8_t* data;
  uint32_t size, fresh, image_crc;
} mk61_service_lease;
typedef struct mk61_service_editor {
  const char* source;
  uint32_t length, cursor, top, sms;
} mk61_service_editor;
typedef struct mk61_service_menu_item {
  const char* text;
  bool (*action)(void);
  uint32_t display_size;
} mk61_service_menu_item;
typedef struct mk61_service_glyph {
  uint32_t width, height;
  uint8_t pixels[8]; /* canonical row-major MSB, at most 8x8 */
} mk61_service_glyph;

/* Optional UC1609 font service, append-only operation 27. Query capability
 * before use: old hosts return no capability and retain the monospaced UI.
 * call(UI_FONT, INFO/GLYPH, codepoint, sizeof(payload), &payload).
 * INFO returns 1 even when family=0 (disabled). GLYPH takes family/size as
 * inputs so one document keeps consistent metrics if settings change later.
 * Families: 1=resident Pixel, 2=legacy Pixel alias, 3=active external FMK.
 * All outputs contain values/bytes only, never resident Flash pointers. */
enum mk61_service_ui_font_operation { MK61_UI_FONT_INFO, MK61_UI_FONT_GLYPH };
typedef struct mk61_service_ui_font_info {
  /* height is the real line envelope; zero from an older resident means size. */
  uint8_t family, size, ascent, descent, line_gap, height;
} mk61_service_ui_font_info;
typedef struct mk61_service_ui_glyph {
  uint8_t family, size, width, height, bearing_x;
  int8_t bearing_y;
  uint8_t advance, fallback;
  uint8_t pixels[32]; /* row-major MSB, ceil(width/8) bytes/row, at most 16x16 */
} mk61_service_ui_glyph;

typedef struct mk61_service_edit_hook {
  char* source;
  uint32_t length, cursor, capacity, shift;
  int32_t key, delta;
  void* context;
} mk61_service_edit_hook;
enum mk61_service_edit_hook_operation {
  MK61_EDIT_INSERT, MK61_EDIT_ALPHA, MK61_EDIT_MOVE, MK61_EDIT_BACKSPACE
};
typedef struct mk61_service_edit_key {
  char* source;
  uint32_t capacity, length, cursor, top, shift;
  uint32_t sms_active, sms_index, sms_deadline;
  int32_t sms_key;
  int32_t keys[13]; /* left/press, right/press, ok/press, esc/press, step L/R, K, alpha, PP */
  const char* ok_text;
  uint32_t options; /* SMS=1, alpha symbols=2, alpha clear line=4 */
  int32_t backspace_key, key;
  uint32_t now, hook_mask;
  uint32_t (*hook)(uint32_t operation, mk61_service_edit_hook* event);
  void* context;
} mk61_service_edit_key;

typedef struct mk61_service_keyboard {
  uint8_t cx, bx, mul, div, power, xy, add, sub, neg, dot;
  uint8_t digit[10];
  uint8_t pp, bp, x_to_p, p_to_x, run, ret, frw, bkw, k, alpha;
  uint8_t degree, grade, radian, user, save, load;
  uint8_t left, right, ok, esc, shg_left, shg_right;
} mk61_service_keyboard;

/* Standard compiler helpers use their ARM EABI calling convention; string
 * functions use ISO C/AAPCS. See loadable_system_runtime.def for slot order. */
typedef void (*mk61_service_runtime_function)(void);
enum mk61_service_runtime_slot {
#define MK61_RUNTIME(name) MK61_RUNTIME_SLOT_##name,
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
  MK61_RUNTIME_COUNT
};

typedef struct mk61_app_services {
  uint32_t magic;
  uint16_t version, struct_size;
  const mk61_service_keyboard* keyboard_mapping;
  uint32_t (*call)(uint32_t operation, uint32_t a, uint32_t b,
                   uint32_t c, void* payload);
  double (*math)(uint32_t operation, double x, double y);
  int (*format)(char* output, uint32_t size, const char* format, va_list args);
  const mk61_service_runtime_function* runtime;
} mk61_app_services;

/* Check the base prefix before even reading the optional tail. Old firmware
 * and unavailable/version-mismatched services return NULL. */
static inline const mk61_app_services* mk61_app_get_services(
    const mk61_app_api* api, uint32_t required_capabilities) {
  if(!mk61_app_api_compatible(api,
        offsetof(mk61_app_api, query_service) + sizeof(api->query_service), 0) ||
      !api->query_service) return NULL;
  const mk61_app_services* services = (const mk61_app_services*)
      api->query_service(MK61_APP_SERVICE_COMMON, MK61_APP_SERVICES_VERSION);
  if(!services || services->magic != MK61_APP_SERVICES_MAGIC ||
      services->version != MK61_APP_SERVICES_VERSION ||
      services->struct_size < sizeof(*services) || !services->call) return NULL;
  if(required_capabilities &&
      (services->call(MK61_SERVICE_CAPABILITIES, 0, 0, 0, NULL) &
       required_capabilities) != required_capabilities) return NULL;
  return services;
}

#endif
