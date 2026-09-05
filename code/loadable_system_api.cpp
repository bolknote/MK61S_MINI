#include "config.h"

#if MK61_ENABLE_PORTABLE_APPS && (MK61_FOCAL_IS_LOADABLE || \
    MK61_TINYBASIC_IS_LOADABLE || MK61_WBMP_VIEWER_IS_LOADABLE || \
    MK61_MARKDOWN_VIEWER_IS_LOADABLE || MK61_CHIP8_IS_LOADABLE)

#include "loadable_system_api.hpp"
#include "loadable_app_api.hpp"
#include "loadable_module_format.hpp"
#include "cross_hal.h"
#include "development.hpp"
#include "menu.hpp"
#include "entropy_pool.hpp"
#include "language_workspace.hpp"
#include "shared_scratch.hpp"
#include "storage_path.hpp"
#include "text_editor.hpp"
#include "mk61_ref.hpp"
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
#include "loadable_system_editor.hpp"
#endif
#include <new>
#include <string.h>
#include <stdio.h>

namespace loadable_module {
namespace {

static_assert(sizeof(language_workspace::Lease) <= MK61_SYSTEM_LEASE_BYTES,
              "increase the versioned opaque lease storage");
static_assert(sizeof(shared_scratch::Lease) <= MK61_SYSTEM_LEASE_BYTES,
              "increase the versioned opaque lease storage");
static_assert(alignof(mk61_system_lease) >= alignof(language_workspace::Lease),
              "opaque lease alignment");
static u32 language_image_crc[2];
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
#define MK61_RUNTIME(name) extern "C" void service_##name() asm(#name);
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
static const mk61_system_runtime_function runtime[] = {
#define MK61_RUNTIME(name) service_##name,
#include "loadable_system_runtime.def"
#undef MK61_RUNTIME
};
#endif

static language_workspace::Owner owner(u32 kind) {
  switch((Kind) kind) {
    case Kind::FOCAL: return language_workspace::Owner::FOCAL;
    case Kind::TINYBASIC: return language_workspace::Owner::TINYBASIC;
    case Kind::WBMP_VIEWER: return language_workspace::Owner::IMAGE_VIEWER;
    case Kind::MARKDOWN_VIEWER: return language_workspace::Owner::MARKDOWN_VIEWER;
    case Kind::CHIP8: return language_workspace::Owner::CHIP8;
    default: return language_workspace::Owner::NONE;
  }
}

static void export_file(const program_store::Entry& entry, mk61_system_file& out) {
  out = {};
  out.id = entry.id; out.parent = entry.parent_id; out.size = entry.data_len;
  out.type = (u8) entry.type; out.kind = (u8) entry.kind;
  memcpy(out.name, entry.name, sizeof(out.name));
}

static u32 display_call(u32 operation, u32 b, u32 c, void* payload) {
  MK61Display& lcd = main_lcd();
  switch(operation) {
    case MK61_SYS_DISPLAY_CLEAR: lcd.clear(); break;
    case MK61_SYS_DISPLAY_CURSOR: lcd.setCursor((u8) b, (u8) c); break;
    case MK61_SYS_DISPLAY_WRITE: lcd.write((u8) b); break;
    case MK61_SYS_DISPLAY_PRINT: if(payload) lcd.print((const char*) payload); break;
    case MK61_SYS_DISPLAY_CURSOR_ON: lcd.cursorOn(); break;
    case MK61_SYS_DISPLAY_CURSOR_OFF: lcd.cursorOff(); break;
    case MK61_SYS_DISPLAY_SUPPORTS_CURSOR: return lcd.supportsCursor();
    case MK61_SYS_DISPLAY_FLUSH: lcd.flush(); break;
    case MK61_SYS_DISPLAY_BEGIN_UPDATE: lcd.beginUpdate(); break;
    case MK61_SYS_DISPLAY_END_UPDATE: lcd.endUpdate(); break;
    case MK61_SYS_DISPLAY_END_VIEWPORT:
#if defined(MK61_DISPLAY_LCD1602)
      lcd.endShiftedViewport();
#endif
      break;
    case MK61_SYS_DISPLAY_GRAPHICS: return lcd.supportsFullscreenBitmap();
    case MK61_SYS_DISPLAY_WIDTH: return lcd.fullscreenBitmapWidth();
    case MK61_SYS_DISPLAY_HEIGHT: return lcd.fullscreenBitmapHeight();
    case MK61_SYS_DISPLAY_GRAPHICS_MODE: return lcd.graphicsMode();
    default: return 0;
  }
  return 1;
}

static u32 key_call(u32 operation, u32 value) {
  switch(operation) {
    case MK61_SYS_KEY_POLL: return (u32) kbd::poll_event().code();
    case MK61_SYS_KEY_GET: return (u32) (value == 0xFFFFFFFFU
        ? kbd::get_key() : kbd::get_key((key_state) value));
    case MK61_SYS_KEY_WAIT: return (u32) kbd::get_key_wait();
    case MK61_SYS_KEY_PRESSED: return kbd::is_key_pressed((i32) value);
    case MK61_SYS_KEY_IMMEDIATE: return kbd::take_immediate_press((i32) value);
    case MK61_SYS_KEY_CLEAR_IMMEDIATE: kbd::clear_immediate_presses(); break;
    case MK61_SYS_KEY_SCAN: return (u32) kbd::scan();
    case MK61_SYS_KEY_HANDOFF: kbd::handoff(kbd::Event((i32) value)); break;
    case MK61_SYS_KEY_HANDOFF_PENDING: return kbd::handoff_pending();
    case MK61_SYS_KEY_ANY: return kbd::any_key_pressed();
    case MK61_SYS_KEY_CLEAR_HOLD: kbd::clear_hold_key(); break;
    case MK61_SYS_KEY_LAST: return (u32) kbd::last_key();
    default: return 0;
  }
  return 1;
}

static u32 system_call(u32 operation, u32 a, u32 b, u32 c, void* payload) {
  switch(operation) {
    case MK61_SYS_DISPLAY: return display_call(a, b, c, payload);
    case MK61_SYS_KEYBOARD: return key_call(a, b);
    case MK61_SYS_MICROS: return micros();
    case MK61_SYS_RANDOM:
      return a >= 1 && a <= 3 ? entropy_pool::next_u32((entropy_pool::Domain) a) : 0;
    case MK61_SYS_SETTINGS:
      switch(a) {
        case MK61_SYS_LANGUAGE: return library_mk61::language_is_ru();
        case MK61_SYS_VOLUME: return library_mk61::sound_volume();
        case MK61_SYS_ANGLE: return (u32) read_grade_switch();
        case MK61_SYS_REGISTER_F: return core_61::expanded_program_is_on();
      }
      return 0;
    case MK61_SYS_FILE_COUNT: return (u32) program_store::count((program_store::ProgramType) a);
    case MK61_SYS_FILE_ENTRY: {
      if(!payload) return 0;
      program_store::Entry entry = {};
      const bool ok = a == 0
          ? b <= 0xFFFFU && program_store::entry_by_id((u16) b, entry)
          : program_store::entry((program_store::ProgramType) c, (int) b, entry);
      if(ok) export_file(entry, *(mk61_system_file*) payload);
      return ok;
    }
    case MK61_SYS_FILE_RESOLVE: {
      if(!payload || !c || a > 0xFFFFU) return (u32) storage_path::Status::NOT_FOUND;
      program_store::Entry entry = {};
      const storage_path::Status status = storage_path::resolve_file(
          (u16) a, (const char*) (usize) c, (program_store::ProgramType) b, entry);
      if(status == storage_path::Status::OK) export_file(entry, *(mk61_system_file*) payload);
      return (u32) status;
    }
    case MK61_SYS_FILE_REMOVE:
      return payload ? program_store::remove((program_store::ProgramType) a, (const char*) payload)
                     : a <= 0xFFFFU && program_store::remove_id((u16) a);
    case MK61_SYS_FILE_EXISTS:
      return program_store::exists((program_store::ProgramType) a, (const char*) payload);
    case MK61_SYS_MEMORY_ACQUIRE: {
      if(!payload || owner(b) == language_workspace::Owner::NONE) return 0;
      auto& out = *(mk61_system_lease*) payload;
      out.data = nullptr; out.size = 0; out.fresh = 0;
      if(a == 0) {
        auto* lease = new(out.opaque) language_workspace::Lease(owner(b), c);
        if(!lease->ok()) { lease->~Lease(); return 0; }
        out.data = (u8*) lease->data(); out.size = lease->size(); out.fresh = lease->fresh();
        if(b == (u32) Kind::FOCAL || b == (u32) Kind::TINYBASIC) {
          u32& stamp = language_image_crc[b - 1U];
          if(stamp != out.image_crc) { out.fresh = 1; stamp = out.image_crc; }
        }
      } else if(a == 1 && (b == (u32) Kind::MARKDOWN_VIEWER || b == (u32) Kind::WBMP_VIEWER)) {
        auto* lease = new(out.opaque) shared_scratch::Lease(
            b == (u32) Kind::MARKDOWN_VIEWER ? shared_scratch::Owner::MARKDOWN_VIEWER
                                           : shared_scratch::Owner::IMAGE_VIEWER, c);
        if(!lease->ok()) { lease->~Lease(); return 0; }
        out.data = lease->data(); out.size = lease->size();
      } else return 0;
      return 1;
    }
    case MK61_SYS_MEMORY_RELEASE: {
      if(!payload) return 0;
      auto& lease = *(mk61_system_lease*) payload;
      if(a == 0) std::launder(reinterpret_cast<language_workspace::Lease*>((void*) lease.opaque))->~Lease();
      else if(a == 1) std::launder(reinterpret_cast<shared_scratch::Lease*>((void*) lease.opaque))->~Lease();
      lease.data = nullptr; lease.size = 0;
      return 1;
    }
    case MK61_SYS_MEMORY_DATA: return (u32) (usize) language_workspace::data(owner(a));
    case MK61_SYS_TEXT_ROWS: {
      if(!payload || a > MK61_SYSTEM_MAX_ROWS) return 0;
      const char* const* lines = (const char* const*) payload;
      lcd_ru::font_map_t map = {};
      const u32 count = a < main_lcd().rows() ? a : main_lcd().rows();
      for(u32 row = 0; row < count; ++row) lcd_ru::scan_text(map, lines[row], lcd_display::COLS);
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear(); lcd_ru::load_custom_font(map);
      for(u32 row = 0; row < count; ++row) {
        main_lcd().setCursor(0, (u8) row);
        lcd_ru::write_text(map, lines[row], lcd_display::COLS);
      }
      return 1;
    }
#if MK61_MARKDOWN_VIEWER_IS_LOADABLE && MK61_MARKDOWN_USES_WBMP
    case MK61_SYS_FONT: {
      if(!payload || a > 1 || b > 0xFFFFU) return 0;
      builtin_font::Raster glyph = {};
      if(!builtin_font::decode((builtin_font::FaceId) a, (u16) b, glyph) ||
         glyph.width > 8 || glyph.height > 8) return 0;
      auto& out = *(mk61_system_glyph*) payload;
      out.width = glyph.width; out.height = glyph.height;
      memcpy(out.pixels, glyph.data, sizeof(out.pixels));
      return 1;
    }
#endif
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
    case MK61_SYS_FILE_WRITE: {
      if(!payload || a > 0xFFFFU || b > 0xFFFFU) return 0;
      auto& request = *(mk61_system_write*) payload;
      if(request.size > 0xFFFFU) return 0;
      u16 id = program_store::INVALID_ID;
      const bool ok = program_store::write_file((u16) a, (u16) b,
          (program_store::ProgramType) c, request.name, request.data, (u16) request.size, &id);
      request.id = id; return ok;
    }
    case MK61_SYS_FILE_CHOOSE: {
      if(!payload || b > 0xFFFFU) return 0;
      auto& out = *(mk61_system_choice*) payload;
      program_store::Entry entry = {};
      u16 parent = program_store::ROOT_ID;
      const auto result = program_store_choose_file((program_store::ProgramType) a,
          (u16) b, c != 0, entry, parent);
      export_file(entry, out.file); out.parent = parent;
      return (u32) result;
    }
    case MK61_SYS_FILE_SAVE_TARGET: {
      if(!payload || b > 0xFFFFU || c > 0xFFFFU) return 0;
      auto& out = *(mk61_system_save_target*) payload;
      u16 parent = (u16) out.parent;
      const bool ok = program_store_choose_save_target((program_store::ProgramType) a,
          (u16) b, out.name, c, parent);
      out.parent = parent; return ok;
    }
    case MK61_SYS_EDITOR_DRAW:
    case MK61_SYS_EDITOR_SCROLL: {
      if(!payload) return 0;
      auto& editor = *(mk61_system_editor*) payload;
      if(editor.length > 0xFFFFU || editor.cursor > editor.length || editor.top > 0xFFFFU) return 0;
      if(operation == MK61_SYS_EDITOR_DRAW) {
        text_editor::draw(main_lcd(), editor.source, (u16) editor.length,
                           (u16) editor.cursor, (u16) editor.top, editor.sms != 0);
      } else {
        u16 top = (u16) editor.top;
        text_editor::ensure_cursor_visible(main_lcd(), editor.source,
            (u16) editor.length, (u16) editor.cursor, top);
        editor.top = top;
      }
      return 1;
    }
    case MK61_SYS_EDITOR_KEY:
      return payload ? system_editor::handle(*(mk61_system_edit_key*) payload) : 0;
    case MK61_SYS_MENU: {
      if(!payload || a == 0 || a > 4) return 0;
      const auto* source = (const mk61_system_menu_item*) payload;
      alignas(t_punct) u8 storage[4][offsetof(t_punct, text) + 32];
      t_punct* items[4];
      for(u32 i = 0; i < a; ++i) {
        items[i] = (t_punct*) storage[i];
        const usize size = strnlen(source[i].text, 31);
        items[i]->size = (u8) source[i].display_size; items[i]->action = source[i].action;
        memcpy(items[i]->text, source[i].text, size); items[i]->text[size] = 0;
      }
      class_menu menu(items, (int) a); menu.select(); return 1;
    }
    case MK61_SYS_REF_READ:
    case MK61_SYS_REF_WRITE: {
      if(!payload || a > (u32) mk61_ref::Kind::R || b > 15) return 0;
      const mk61_ref::Ref ref = {(mk61_ref::Kind) a, (u8) b};
      return operation == MK61_SYS_REF_READ ? mk61_ref::read(ref, *(double*) payload)
                                           : mk61_ref::write(ref, *(double*) payload);
    }
#endif
    default: return 0;
  }
}

static double system_math(u32 operation, double x, double y) {
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
  switch(operation) {
    case MK61_SYS_SIN: return mk_math::sin(x);
    case MK61_SYS_COS: return mk_math::cos(x);
    case MK61_SYS_TAN: return mk_math::tan(x);
    case MK61_SYS_ASIN: return mk_math::asin(x);
    case MK61_SYS_ACOS: return mk_math::acos(x);
    case MK61_SYS_ATAN: return mk_math::atan(x);
    case MK61_SYS_LN: return mk_math::ln(x);
    case MK61_SYS_LOG10: return mk_math::log10(x);
    case MK61_SYS_EXP: return mk_math::exp(x);
    case MK61_SYS_SQRT: return mk_math::sqrt(x);
    case MK61_SYS_POW: return mk_math::pow(x, y);
  }
#else
  (void) operation; (void) x; (void) y;
#endif
  return 0;
}

static int system_format(char* output, u32 size, const char* format, va_list args) {
  return vsnprintf(output, size, format, args);
}

} // namespace

const mk61_system_api& system_api() {
  static const mk61_system_api api = {
      MK61_SYSTEM_API_MAGIC, MK61_SYSTEM_API_VERSION, sizeof(mk61_system_api),
      &keyboard_layout::ACTIVE, system_call, system_math, system_format,
#if MK61_FOCAL_IS_LOADABLE || MK61_TINYBASIC_IS_LOADABLE
      runtime
#else
      nullptr
#endif
  };
  return api;
}

} // namespace loadable_module
#endif
