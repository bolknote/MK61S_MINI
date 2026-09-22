#ifndef MK61_LOADABLE_APP_SERVICES_H
#define MK61_LOADABLE_APP_SERVICES_H

#include "loadable_app_api.h"
#include <stdbool.h>
#include <stdarg.h>

/* Public extended services, obtained through mk61_app_api.query_service.
 * Canonical System APP and ordinary APP use this exact same table. */
#define MK61_APP_SERVICES_MAGIC 0x31535953UL
#define MK61_APP_SERVICES_VERSION 2U
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
  MK61_SERVICE_CAP_UI_FONT = 1U << 11,
  MK61_SERVICE_CAP_NUMBER_IO = 1U << 12,
  MK61_SERVICE_CAP_TEXT_FONT = 1U << 13,
  MK61_SERVICE_CAP_FLOAT_CONVERT = 1U << 14,
  /* Private storage primitives used only by the canonical USBDISK.APP. */
  MK61_SERVICE_CAP_USBDISK = 1U << 15
};
enum mk61_service_memory_arena {
  MK61_SERVICE_WORKSPACE = 0, MK61_SERVICE_SCRATCH = 1
};
/* The owner argument of MEMORY_ACQUIRE/MEMORY_DATA is an mk61_app_kind.
 * Most ordinary APP pass mk61_app_current_kind; this alias is convenient for
 * APP that can only ever be launched as APPLICATION. */
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
  MK61_SERVICE_UI_FONT,
  MK61_SERVICE_NUMBER_FORMAT,
  MK61_SERVICE_NUMBER_PARSE,
  MK61_SERVICE_REF_PARSE,
  MK61_SERVICE_TEXT_FONT,
  MK61_SERVICE_FLOAT_CONVERT,
  MK61_SERVICE_USBDISK
};

/* Narrow resident C6 backend for USBDISK.APP. FAT, LFN, conversion and commit
 * policy remain in the APP; these operations only expose atomic store facts
 * and mutations which cannot be implemented outside the resident driver. */
enum mk61_service_usbdisk_operation {
  MK61_USBDISK_READY,
  MK61_USBDISK_GEOMETRY,
  MK61_USBDISK_MAX_NODES,
  MK61_USBDISK_CHILD_COUNT,
  MK61_USBDISK_CHILD,
  MK61_USBDISK_CREATE_DIRECTORY,
  MK61_USBDISK_MOVE_RENAME,
  MK61_USBDISK_ALLOCATE_DIRECTORY_EXTENT,
  MK61_USBDISK_RELEASE_DIRECTORY_EXTENT,
  MK61_USBDISK_FIRST_DIRECTORY_EXTENT,
  MK61_USBDISK_NEXT_DIRECTORY_EXTENT,
  MK61_USBDISK_DIRECTORY_EXTENT_INFO,
  MK61_USBDISK_FIRST_FILE_EXTENT,
  MK61_USBDISK_NEXT_FILE_EXTENT,
  MK61_USBDISK_FILE_EXTENT_INFO,
  MK61_USBDISK_RELEASE_FILE_EXTENT,
  MK61_USBDISK_STAGE_WRITE,
  MK61_USBDISK_STAGE_READ,
  MK61_USBDISK_STAGE_EXISTS,
  MK61_USBDISK_STAGE_COUNT,
  MK61_USBDISK_STAGE_DISCARD_ALL,
  MK61_USBDISK_STAGE_CLEAR,
  MK61_USBDISK_STAGE_LOCK,
  MK61_USBDISK_STAGE_NARROW_MATCHING,
  MK61_USBDISK_STAGE_RESTORE_FULL,
  MK61_USBDISK_STAGE_UNLOCK,
  MK61_USBDISK_WRITE_FILE_SOURCE,
  MK61_USBDISK_VALIDATE_APP,
  MK61_USBDISK_MAX_FILE_SIZE,
  MK61_USBDISK_VOLUME_SERIAL,
  MK61_USBDISK_MEDIA_REVISION,
  /* Diagnostic breadcrumb emitted by USBDISK.APP during MSC startup. */
  MK61_USBDISK_STARTUP_STAGE,
  /* One bounded copy replaces hundreds of per-sector presence queries. */
  MK61_USBDISK_STAGE_SNAPSHOT,
  /* Perform one bounded, power-safe directory-tail trim transaction. */
  MK61_USBDISK_TRIM_DIRECTORY_EXTENTS,
  /* Drop AppleDouble data from the journal as soon as its name is known. */
  MK61_USBDISK_STAGE_FORGET
};
enum mk61_service_usbdisk_trim_result {
  MK61_USBDISK_TRIM_FAILED = 0,
  MK61_USBDISK_TRIM_COMPLETE = 1,
  MK61_USBDISK_TRIM_MORE = 2
};
typedef struct mk61_service_usbdisk_geometry {
  uint32_t capacity_bytes, physical_sectors;
  uint32_t locator_a_sector, locator_b_sector;
  uint32_t catalog_a_sector, catalog_b_sector;
  uint16_t catalog_table_sectors, catalog_bank_sectors;
  uint32_t data_first_sector, data_sector_count, stage_first_sector;
  uint16_t stage_sector_count;
  uint32_t settings_sector;
  uint16_t max_nodes;
  uint8_t sectors_per_cluster;
  uint16_t fat_sectors, root_entries, root_sectors;
  uint32_t logical_sectors;
} mk61_service_usbdisk_geometry;
typedef struct mk61_service_usbdisk_name {
  uint32_t id, parent, preferred, out_id;
  const char* name;
} mk61_service_usbdisk_name;
typedef struct mk61_service_usbdisk_extent {
  uint32_t id, owner, next, cluster_index;
} mk61_service_usbdisk_extent;
typedef int (*mk61_service_usbdisk_reader)(void* context, uint32_t offset,
                                          uint8_t* output, uint32_t size);
typedef int (*mk61_service_usbdisk_key_filter)(void* context, uint32_t key);
typedef struct mk61_service_usbdisk_source {
  uint32_t parent, preferred, type, size, out_id, extent_count;
  const char* name;
  void* context;
  mk61_service_usbdisk_reader read;
  const uint16_t* extents;
  uint8_t* compression_buffer;
  uint32_t compression_buffer_size;
  const uint8_t* contiguous_data;
} mk61_service_usbdisk_source;
typedef struct mk61_service_usbdisk_stage_filter {
  void* context;
  mk61_service_usbdisk_key_filter include;
  uint32_t* index_storage;
  uint32_t index_capacity;
} mk61_service_usbdisk_stage_filter;
typedef struct mk61_service_usbdisk_stage_snapshot {
  uint32_t* keys;
  uint32_t capacity;
  uint32_t count;
} mk61_service_usbdisk_stage_snapshot;
typedef struct mk61_service_usbdisk_app_validation {
  void* context;
  mk61_service_usbdisk_reader read;
  uint32_t size, status;
} mk61_service_usbdisk_app_validation;
enum mk61_service_float_convert_operation {
  MK61_FLOAT_FROM_DOUBLE,
  MK61_DOUBLE_FROM_FLOAT
};
typedef struct mk61_service_float_convert {
  double value;
  uint32_t bits;
} mk61_service_float_convert;
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
  MK61_SERVICE_DISPLAY_END_UI_TEXT,
  // Draw one explicit glyph codepoint. Text itself is always passed as M8.
  MK61_SERVICE_DISPLAY_WRITE_CODEPOINT,
  // Resident-owned M8 word flow. Languages hand the complete logical line
  // to the display owner instead of copying font metrics and wrap policy.
  MK61_SERVICE_DISPLAY_FLOW_TEXT
};
enum mk61_service_text_flow_flag {
  MK61_SERVICE_TEXT_FLOW_TAIL = 1U,
  MK61_SERVICE_TEXT_FLOW_EMPTY_LINE = 2U
};
typedef struct mk61_service_text_flow {
  const char* text;
  uint32_t length, first_row, max_rows, flags;
} mk61_service_text_flow;
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

/* Temporary external text-font session, append-only operation 31.
 * BEGIN snapshots the resident display font. LOAD receives a zero-terminated
 * Fonts/<name>.FMK stem; resident M61 orchestration asks SETUP to compile
 * it, then replaces the text face atomically. RESTORE returns to the snapshot
 * while keeping the session open; END restores it and closes the session.
 * ACTIVATE re-enters the already loaded runtime face after a language selected
 * its ordinary renderer. A running APP must only use ACTIVATE: on F401 it
 * cannot load SETUP.APP into the APP arena that it already occupies. Signed results are
 * transported in call()'s u32. */
enum mk61_service_text_font_operation {
  MK61_TEXT_FONT_BEGIN,
  MK61_TEXT_FONT_LOAD,
  MK61_TEXT_FONT_RESTORE,
  MK61_TEXT_FONT_END,
  MK61_TEXT_FONT_ACTIVATE
};
enum mk61_service_text_font_result {
  MK61_TEXT_FONT_NOT_FOUND = 0,
  MK61_TEXT_FONT_OK = 1,
  MK61_TEXT_FONT_INVALID = -1,
  MK61_TEXT_FONT_UNSUPPORTED = -2,
  MK61_TEXT_FONT_UNAVAILABLE = -3
};

/* SETUP service v2. Explicit C fields, no native C++ layouts. Version 2
 * makes FMK compilation an explicit SETUP -> resident transaction. */
enum { MK61_SETUP_API_VERSION = 2 };
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
  MK61_SETUP_UI_FONT_STEP,
  /* SETUP -> resident handoff for a fully compiled RAM font. */
  MK61_SETUP_PREPARED_FONT_INSTALL,
  /* Resolve a catalog key without recursively invoking SETUP. */
  MK61_SETUP_UI_FONT_SOURCE
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
enum mk61_setup_prepared_font_role {
  MK61_PREPARED_FONT_TEXT = 0,
  MK61_PREPARED_FONT_UI = 1
};
enum mk61_setup_prepared_font_flag {
  MK61_PREPARED_FONT_PERSIST = 1u << 0,
  MK61_PREPARED_FONT_SELECT_UI = 1u << 1
};
typedef struct mk61_setup_prepared_font {
  const uint8_t* data;
  uint32_t size, source_id, ui_key;
  uint8_t role, expected_height, flags, reserved;
} mk61_setup_prepared_font;
typedef struct mk61_setup_ui_font_source {
  uint32_t id;
  uint8_t size, reserved[3];
} mk61_setup_ui_font_source;

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
typedef struct mk61_service_number_format {
  double value;
  char* output;
  uint32_t capacity, significant_digits;
} mk61_service_number_format;
typedef struct mk61_service_number_parse {
  double value;
  const char* input;
  uint32_t consumed;
} mk61_service_number_parse;
typedef struct mk61_service_ref_parse {
  char name[4];
  uint32_t kind, reg;
} mk61_service_ref_parse;
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
  uint32_t options; /* SMS=1, alpha symbols=2, alpha clear line=4, default text=8,
                       resident key map=16 */
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
