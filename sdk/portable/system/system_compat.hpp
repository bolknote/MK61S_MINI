#ifndef MK61_PORTABLE_SYSTEM_COMPAT_HPP
#define MK61_PORTABLE_SYSTEM_COMPAT_HPP

/* Adapter for the existing built-in feature sources. A canonical System APP
 * uses exactly the same public mk61_app_api/services and SDK startup as every
 * other APP; these facades only avoid rewriting the feature implementation. */
#define CONFIG
#define CLASS_KEYBOARD
#define LCD_FONT_PACK
#define MK61_DISPLAY_HPP
#define TOOLS
#define MENU_CLASS
#define MK61_MK52_CROSS_HAL
#define DEVELOPMENT_HPP
#define PROGRAM_STORE_HPP
#define LANGUAGE_WORKSPACE_HPP
#define SHARED_SCRATCH_HPP
#define LCD_RU_ENCODER

#define MK61_SETUP_IS_LOADABLE 1
#define MK61_ENABLE_FOCAL 1
#define MK61_ENABLE_TINYBASIC 1
#define MK61_FOCAL_IS_LOADABLE 1
#define MK61_TINYBASIC_IS_LOADABLE 1
#define MK61_WBMP_VIEWER_IS_LOADABLE 1
#define MK61_MARKDOWN_VIEWER_IS_LOADABLE 1
#define MK61_CHIP8_IS_LOADABLE 1
#define MK61_USBDISK_IS_LOADABLE 1
#define MK61_MARKDOWN_VIEWER_IS_BUILTIN 0
#define MK61_CHIP8_IS_BUILTIN 0
#define MK61_WBMP_DECODER_IS_BUILTIN 0
#ifndef MK61_PORTABLE_TEXT_ONLY
#define MK61_PORTABLE_TEXT_ONLY 0
#endif
#ifndef MK61_PORTABLE_UI_FONTS
#define MK61_PORTABLE_UI_FONTS 1
#endif
#if MK61_PORTABLE_UI_FONTS != 0 && MK61_PORTABLE_UI_FONTS != 1
#error "MK61_PORTABLE_UI_FONTS must be 0 or 1"
#endif
#define MK61_UI_FONT_CLIENT MK61_PORTABLE_UI_FONTS
#define MK61_MARKDOWN_USES_WBMP (!MK61_PORTABLE_TEXT_ONLY)
#define MK61_HAS_COMPILED_GRAPHICS 1
#ifndef MK61_APP_LOCAL_FLOAT_MATH
#define MK61_APP_LOCAL_FLOAT_MATH 0
#endif
#if MK61_APP_LOCAL_FLOAT_MATH != 0 && MK61_APP_LOCAL_FLOAT_MATH != 1
#error "MK61_APP_LOCAL_FLOAT_MATH must be 0 or 1"
#endif
#define MK61_APP_FLOAT_SIN   (1U << 0)
#define MK61_APP_FLOAT_COS   (1U << 1)
#define MK61_APP_FLOAT_TAN   (1U << 2)
#define MK61_APP_FLOAT_ASIN  (1U << 3)
#define MK61_APP_FLOAT_ACOS  (1U << 4)
#define MK61_APP_FLOAT_ATAN  (1U << 5)
#define MK61_APP_FLOAT_LN    (1U << 6)
#define MK61_APP_FLOAT_LOG10 (1U << 7)
#define MK61_APP_FLOAT_EXP   (1U << 8)
#define MK61_APP_FLOAT_SQRT  (1U << 9)
#define MK61_APP_FLOAT_POW   (1U << 10)
#define MK61_APP_FLOAT_ALL   ((1U << 11) - 1U)
#ifndef MK61_APP_LOCAL_FLOAT_MATH_MASK
  #if MK61_APP_LOCAL_FLOAT_MATH
    /* The compact newlib group that fits together with FOCAL in the 20 KiB
     * APP arena. Trigonometric functions are substantially larger and keep
     * using the resident math API. */
    #define MK61_APP_LOCAL_FLOAT_MATH_MASK \
      (MK61_APP_FLOAT_LN | MK61_APP_FLOAT_LOG10 | MK61_APP_FLOAT_EXP | \
       MK61_APP_FLOAT_SQRT)
  #else
    #define MK61_APP_LOCAL_FLOAT_MATH_MASK 0U
  #endif
#endif
#if (MK61_APP_LOCAL_FLOAT_MATH_MASK & ~MK61_APP_FLOAT_ALL) != 0
#error "MK61_APP_LOCAL_FLOAT_MATH_MASK contains an unsupported operation"
#endif
#define MK61_MATH_BACKEND 1

#include "rust_types.h"
#include "mk61_app.h"
#include "loadable_system_api.h"
#include "keyboard_core.hpp"
#include "keyboard_layout.hpp"
#include "entropy_pool.hpp"
#include "storage_geometry.hpp"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace portable_system {
extern const mk61_system_api* api;
extern const mk61_app_api* app;
extern u32 image_crc;
extern u32 kind;
bool bind(const mk61_app_api* app_api, u32 crc, u32 app_kind);
inline u32 call(u32 operation, u32 a = 0, u32 b = 0, u32 c = 0, void* data = nullptr) {
  return api->call(operation, a, b, c, data);
}
void text_rows(const char* const* rows, u32 count);
void editor(bool draw, const char* source, u16 len, u16 cursor, u16& top, bool sms = false);
bool format_number(double value, u8 significant_digits,
                   char* output, usize capacity);
bool parse_number(const char* input, double& value, const char*& end);
}

extern "C" u32 millis();
extern "C" u32 micros();
extern "C" void delay(u32 ms);
void idle_main_process();
void sound_stop();
void sound_scaled(u32 pin, isize frequency, usize duration, usize volume, usize percent);
static constexpr u32 PIN_BUZZER = 0; // sound callback selects the physical pin
enum class key_state { PRESSED = 0, RELEASED = 0x40 };
namespace kbd {
using Event = keyboard_core::Event;
Event poll_event();
isize scan();
i32 get_key();
i32 get_key(key_state state);
i32 get_key_wait();
i32 last_key();
bool is_key_pressed(i32 key);
bool take_immediate_press(i32 key);
void clear_immediate_presses();
void clear_hold_key();
void handoff(Event event);
bool handoff_pending();
bool any_key_pressed();
}

#define KEY_LEFT (keyboard_layout::active().left)
#define KEY_RIGHT (keyboard_layout::active().right)
#define KEY_OK (keyboard_layout::active().ok)
#define KEY_ESC (keyboard_layout::active().esc)
#define KEY_K (keyboard_layout::active().k)
#define KEY_ALPHA (keyboard_layout::active().alpha)
#define KEY_CX (keyboard_layout::active().cx)
#define KEY_PP (keyboard_layout::active().pp)
#define KEY_LEFT_PRESS KEY_LEFT
#define KEY_RIGHT_PRESS KEY_RIGHT
#define KEY_OK_PRESS KEY_OK
#define KEY_ESC_PRESS KEY_ESC
#define KEY_SHG_LEFT_PRESS (keyboard_layout::active().shg_left)
#define KEY_SHG_RIGHT_PRESS (keyboard_layout::active().shg_right)

namespace lcd_display {
static constexpr u8 COLS = 16;
static constexpr u8 RUNTIME_MAX_ROWS = MK61_SYSTEM_MAX_ROWS;
}
class MK61Display {
 public:
  static constexpr u8 MAX_ROWS = MK61_SYSTEM_MAX_ROWS;
  void clear();
  void setCursor(u8 col, u8 row);
  void write(u8 value);
  void writeCodepoint(u16 value);
  void print(const char* text);
  void print(char value) { write((u8) value); }
  void cursorOn();
  void cursorOff();
  bool supportsCursor() const;
  void flush();
  void beginUpdate();
  void endUpdate();
  void endShiftedViewport();
  void endUiText();
  u8 printWrappedText(const char* text, u16 length, u8 first_row,
                      u8 max_rows, bool tail = false,
                      bool empty_line = false);
  u8 cols() const { return (u8) portable_system::app->display_columns(); }
  u8 rows() const { return (u8) portable_system::app->display_rows(); }
  bool supportsFullscreenBitmap() const;
  bool graphicsMode() const {
    return portable_system::call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_GRAPHICS_MODE);
  }
  u16 fullscreenBitmapWidth() const;
  u16 fullscreenBitmapHeight() const;
  u32 displayModeRevision() const { return portable_system::app->graphics_revision(); }
  bool beginFullscreenBitmap() { return portable_system::app->graphics_begin(); }
  bool showFullscreenBitmap(const u8* data, usize size) { return portable_system::app->graphics_present(data, size); }
  void endFullscreenBitmap() { portable_system::app->graphics_end(); }
};
MK61Display& main_lcd();
class MK61DisplayUpdate {
 public:
  explicit MK61DisplayUpdate(MK61Display& display) : lcd(display) { lcd.beginUpdate(); }
  ~MK61DisplayUpdate() { lcd.endUpdate(); }
 private:
  MK61Display& lcd;
};
namespace lcd_ru { void print_lines(const char* first, const char* second); }

using menu_action = bool (*)(void);
struct t_punct { u8 size; menu_action action; char text[]; };
class class_menu {
 public:
  class_menu(t_punct** entries, int count) : entries_(entries), count_(count) {}
  void select();
 private:
  t_punct** entries_;
  int count_;
};
namespace action { static constexpr bool MENU_EXIT = true, MENU_BACK = false; }
namespace library_mk61 { bool language_is_ru(); u8 sound_volume(); }
enum stack { X1 = 0, X = 1, Y = 2, Z = 3, T = 4 };
enum AngleUnit { RADIAN = 10, DEGREE = 11, GRADE = 12 };
AngleUnit read_grade_switch();

namespace program_store {
static constexpr usize NAME_SIZE = 32;
static constexpr u16 MAX_MK61_TEXT_SIZE = 1536, MAX_TINYBASIC_TEXT_SIZE = 3584,
                     MAX_FONT_SIZE = 8192, MAX_IMAGE1_SIZE = 1600,
                     MAX_CHIP8_SIZE = 3584,
                     MAX_APP_FILE_SIZE = 20U * 1024U + 64U;
static constexpr u8 MAX_FAT_EXTENTS_PER_FILE = 10;
static constexpr u8 MAX_DIRECTORY_DEPTH = 32;
static constexpr u16 ROOT_ID = 0xFFFF, INVALID_ID = 0xFFFF;
enum class ProgramType : u8 { MK61 = 0, FOCAL = 2, TINYBASIC = 3, TEXT = 4,
  MK61_STATE = 5, FONT = 6, IMAGE1 = 7, APP = 8, CHIP8 = 9, MARKDOWN = 10 };
enum class NodeKind : u8 { FILE = 0, DIRECTORY = 1, DIRECTORY_EXTENT = 2, FILE_EXTENT = 3 };
struct Entry { ProgramType type; char name[NAME_SIZE]; u16 data_len, id, parent_id; NodeKind kind; };
struct FileSource {
  void* context;
  bool (*read)(void* context, u32 offset, u8* output, usize size);
};
enum class WriteFailure : u8 {
  NONE = 0, ARGUMENTS = 1, VISIBLE_SIZE = 2, EXTENT_SHAPE = 3,
  PREFERRED_ID = 4, NAME_COLLISION = 5, EXTENT_SELECTION = 6,
  COMPRESSION = 7, RECORD = 8, CATALOG = 9, COMMIT = 10
};
enum class WriteFailureDetail : u8 {
  NONE = 0, TARGET_VISIBLE_NAME = 1, PARENT = 2, CHILD_CATALOG = 3,
  CHILD_NAME = 4, CHILD_VISIBLE_NAME = 5, ROOT_EXISTING_CAPACITY = 6,
  COLLISION = 7, CHAIN = 8, ROOT_TARGET_CAPACITY = 9,
  REPLACED_NAME = 10, REPLACED_EXTENTS = 11
};
constexpr bool text_content(ProgramType type) {
  return type == ProgramType::MK61 || type == ProgramType::FOCAL ||
      type == ProgramType::TINYBASIC || type == ProgramType::TEXT ||
      type == ProgramType::MK61_STATE || type == ProgramType::MARKDOWN;
}
constexpr bool transparent_compression_enabled(ProgramType type) {
  return type == ProgramType::FOCAL || type == ProgramType::TINYBASIC ||
      type == ProgramType::TEXT || type == ProgramType::MK61_STATE ||
      type == ProgramType::IMAGE1 || type == ProgramType::CHIP8 ||
      type == ProgramType::MARKDOWN;
}
bool ready();
const storage_geometry::Geometry& geometry();
u32 media_revision();
u16 max_nodes();
const char* file_extension(ProgramType type);
int count(ProgramType type);
bool entry(ProgramType type, int index, Entry& out);
bool entry_by_id(u16 id, Entry& out);
int child_count(u16 parent);
bool child(u16 parent, int index, Entry& out);
bool read_id(u16 id, u8* data, u16 capacity, u16* length);
bool read_range_id(u16 id, u16 offset, u8* data, u16 size, u16* length);
bool exists(ProgramType type, const char* name);
bool remove(ProgramType type, const char* name);
bool remove_id(u16 id);
bool write_file(u16 parent, u16 preferred, ProgramType type, const char* name,
                const u8* data, u16 size, u16* id = nullptr);
bool create_directory(u16 parent, const char* name, u16 preferred,
                      u16* id = nullptr);
bool write_file_from_source(u16 parent, u16 preferred, ProgramType type,
                            const char* name, u16 size,
                            const FileSource& source,
                            const u16* extents = nullptr,
                            u8 extent_count = 0, u16* id = nullptr,
                            u8* compression_buffer = nullptr,
                            usize compression_buffer_size = 0,
                            const u8* contiguous_data = nullptr);
WriteFailure last_write_failure(void);
WriteFailureDetail last_write_failure_detail(void);
bool move_rename(u16 id, u16 parent, const char* name);
bool allocate_directory_extent(u16 directory, u16 preferred);
bool release_directory_extent(u16 extent);
bool trim_directory_extents(u16 directory, u16 keep_count);
bool first_extent(u16 directory, u16& id);
bool next_extent(u16 extent, u16& id);
bool extent_info(u16 extent, u16& directory, u16& next);
bool first_file_extent(u16 file, u16& id);
bool next_file_extent(u16 extent, u16& id);
bool file_extent_info(u16 extent, u16& file, u8& cluster, u16& next);
bool release_file_extent(u16 extent);
bool vfat_stage_write(u32 block, const u8* data);
bool vfat_stage_read(u32 block, u8* data);
bool vfat_stage_exists(u32 block);
u16 vfat_stage_count();
bool vfat_stage_discard_all();
void vfat_stage_clear();
bool vfat_stage_lock();
using VfatStageKeyFilter = bool (*)(void*, u32);
bool vfat_stage_narrow_matching(VfatStageKeyFilter include, void* context,
                                u32* storage, u16 capacity);
bool vfat_stage_restore_full();
void vfat_stage_unlock();
}
enum class ProgramStoreFileDialogResult : u8 { CANCELLED = 0, EXISTING, NEW_FILE };
ProgramStoreFileDialogResult program_store_choose_file(program_store::ProgramType type,
    u16 parent, bool allow_new, program_store::Entry& entry, u16& new_parent);
bool program_store_choose_save_target(program_store::ProgramType type, u16 parent,
    char* name, usize capacity, u16& new_parent);

namespace shared_memory { namespace snapshot_schema {
static constexpr u8 FOCAL_RUNTIME = 1, TINYBASIC_RUNTIME = 2;
} }
namespace language_workspace {
static constexpr usize SIZE = 8192;
enum class Owner : u8 { NONE = 0, FOCAL = 1, TINYBASIC = 2,
  IMAGE_VIEWER = 3, CHIP8 = 5, MARKDOWN_VIEWER = 6, SETUP = 7,
  USB_DISK = 8 };
class Lease {
 public:
  constexpr Lease() : lease_{} {}
  Lease(Owner owner, usize size);
#if defined(MK61_BUILD_USBDISK_MODULE)
  ~Lease() = default;
#else
  ~Lease();
#endif
  bool ok() const { return lease_.data != nullptr; }
  bool fresh() const { return lease_.fresh != 0; }
  void* data() const { return lease_.data; }
  usize size() const { return lease_.size; }
  bool acquire(Owner owner, usize size);
  void reset();
  Lease(const Lease&) = delete;
  Lease& operator=(const Lease&) = delete;
 private:
  mk61_system_lease lease_;
};
void* data(Owner owner);
}
namespace shared_scratch {
static constexpr usize SIZE = 1600;
enum class Owner : u8 { IMAGE_VIEWER = 3, MARKDOWN_VIEWER = 6, USB_CACHE = 8 };
class Lease {
 public:
  constexpr Lease() : lease_{} {}
  Lease(Owner owner, usize size);
#if defined(MK61_BUILD_USBDISK_MODULE)
  ~Lease() = default;
#else
  ~Lease();
#endif
  void reset();
  bool ok() const { return lease_.data != nullptr; }
  u8* data() const { return lease_.data; }
  usize size() const { return lease_.size; }
  bool acquire(Owner owner, usize size);
  Lease(const Lease&) = delete;
  Lease& operator=(const Lease&) = delete;
 private:
  mk61_system_lease lease_;
};
}

#endif
