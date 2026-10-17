#include "app_flow.hpp"
#include "basic_native_io.hpp"
#include "builtin_font.hpp"
#include "clock.hpp"
#include "cross_hal.h"
#include "input.hpp"
#include "keyboard_layout.hpp"
#include "language_resources.hpp"
#include "loadable_app_api.h"
#include "loadable_app_services.h"
#include "loadable_module_abi.hpp"
#include "loadable_module_format.hpp"
#include "m61_platform.hpp"
#include "m61_text.hpp"
#include "mk61_ref.hpp"
#include "mk8_codec.hpp"
#include "mk_math.hpp"
#include "native_runtime.hpp"
#include "number_format.hpp"
#include "script.hpp"
#include "services.hpp"
#include "storage_path.hpp"
#include "terminal_core.hpp"
#include "text_editor.hpp"
#include "tinybasic_diagnostic.hpp"
#include "ui_font_service.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "hardware/sync.h"
#include "pico/stdlib.h"
#endif

namespace picocalc {
namespace {
const char *extension(unsigned type) {
  static const char *ext[] = {".m61", "",     ".foc",  ".bas", ".txt",
                              ".sta", ".fmk", ".wbmp", ".app", ".ch8",
                              ".md",  ".bin", ".sheet"};
  return type < 13 ? ext[type] : "";
}
bool utf8(const char *source, char *out, unsigned capacity) {
  usize used = 0;
  if (!source || !mk8::to_utf8((const u8 *)source, std::strlen(source),
                               (u8 *)out, capacity - 1, used))
    return false;
  out[used] = 0;
  return true;
}
bool join(const char *directory, const char *leaf, char out[files::PATH_SIZE]) {
  const int n = std::snprintf(out, files::PATH_SIZE, "%s%s%s", directory,
                              !std::strcmp(directory, "/") ? "" : "/", leaf);
  return n > 0 && n < (int)files::PATH_SIZE;
}
} // namespace

// One foreground application owns this table at a time, just as on STM32.
// No APP pointers or leases survive return, media export or a subsequent load.
class NativeHost {
public:
  explicit NativeHost(Services &service) : s(service) { current = this; }
  ~NativeHost() {
    while (font_sessions) {
      program_store_text_font_end();
      --font_sessions;
    }
    s.graph_.reset();
    s.graph_visible_ = false;
    for (auto &lease : leases)
      std::free(lease.data);
    current = nullptr;
  }
  static NativeHost *current;
  static const mk61_app_api api;
  static const mk61_app_services common;
  static const mk61_service_keyboard mapping;
  Services &s;
  struct Lease {
    u8 *data = nullptr;
    unsigned size = 0;
  } leases[2];
  u8 fifo[32]{}, head = 0, count = 0, last = 0;
  unsigned cursor_x = 0, cursor_y = 0, revision = 1;
  bool graphics = false;
  u32 sound_end = 0;
  unsigned font_sessions = 0;
  bool preview = false;
  Settings settings() const { return s.ui_ ? s.ui_->settings() : Settings{}; }
  u32 setup(u32 op, u32 a, u32 b, void *payload);
  u32 resource(u32 op, void *payload);
  void pump() {
    u8 key = 0;
    if (s.pump_ && s.pump_(s.pump_context_, key) && count < sizeof(fifo)) {
      fifo[(head + count) % sizeof(fifo)] = key;
      ++count;
    }
    if (sound_end && (i32)(millis() - sound_end) >= 0) {
      script::tone(0, 0);
      sound_end = 0;
    }
  }
  int take(bool wait = false) {
    do {
      pump();
      if (count) {
        last = fifo[head];
        head = (head + 1) % sizeof(fifo);
        --count;
        return last;
      }
    } while (wait);
    return -1;
  }
  static void service() { current->pump(); }
  static void delay(u32 ms) {
    const u32 start = millis();
    while ((u32)(millis() - start) < ms)
      current->pump();
  }
  static u32 columns() { return script::columns(); }
  static u32 rows() { return script::rows(); }
  static u32 clear() {
    current->cursor_x = current->cursor_y = 0;
    script::show_text("");
    return 1;
  }
  static u32 write(u32 x, u32 y, const char *text, u32 n) {
    if (!text || n > MK61_APP_MAX_TEXT_BYTES || x >= columns() || y >= rows())
      return 0;
    script::write_text(x, y, text, n);
    return 1;
  }
  static i32 poll() {
    const int c = current->take();
    return c < 0 ? -1 : controls::logical((u8)c);
  }
  static i32 wait() { return controls::logical((u8)current->take(true)); }
  static u32 held(i32 key) {
    if (key < 0)
      return 0;
    for (unsigned c = 1; c < 256; ++c)
      if (controls::logical((u8)c) == key && controls::pressed((u8)c, millis()))
        return 1;
    return 0;
  }
  static u32 file_size(u32 id) {
    program_store::Entry e;
    return id < 0xFFFF && program_store::entry_by_id((u16)id, e) ? e.data_len
                                                                 : 0;
  }
  static u32 file_read(u32 id, u32 offset, u8 *out, u32 n) {
    const char *path = id < 0xFFFF ? script::file_path((u16)id) : nullptr;
    unsigned got = 0;
    if (!path || !out || n > 65535 ||
        !files::read_range(path, offset, out, n, got))
      return 0;
    return got;
  }
  static u32 beep(u32 hz, u32 ms, u32 volume) {
    if (hz > 20000 || ms > 60000 || volume > 100)
      return 0;
    script::tone(volume ? hz : 0, 0);
    current->sound_end = ms ? millis() + ms : 0;
    return 1;
  }
  static void stop() {
    script::tone(0, 0);
    current->sound_end = 0;
  }
  static void led(u32 on) { script::led(on != 0); }
  static u32 blink(u32 n, u32 on, u32 off) {
    if (n > 100 || on > 10000 || off > 10000)
      return 0;
    for (u32 i = 0; i < n; ++i) {
      script::led(true);
      delay(on);
      script::led(false);
      delay(off);
    }
    return 1;
  }
  static u32 yes() { return 1; }
  static u32 width() { return 192; }
  static u32 height() { return 64; }
  static u32 graph_revision() { return current->revision; }
  static u32 graph_begin() {
    current->graphics = true;
    return 1;
  }
  static u32 graph_present(const u8 *data, u32 n) {
    if (!current->graphics || !data || n != 1536)
      return 0;
    script::show_frame(data);
    return 1;
  }
  static void graph_end() { current->graphics = false; }
  static const void *query(u32 id, u32 version) {
    return id == MK61_APP_SERVICE_COMMON && version == MK61_APP_SERVICES_VERSION
               ? &common
               : nullptr;
  }
  static double math(u32 op, double x, double y) {
    switch (op) {
    case MK61_SERVICE_SIN:
      return mk_math::sin(x);
    case MK61_SERVICE_COS:
      return mk_math::cos(x);
    case MK61_SERVICE_TAN:
      return mk_math::tan(x);
    case MK61_SERVICE_ASIN:
      return mk_math::asin(x);
    case MK61_SERVICE_ACOS:
      return mk_math::acos(x);
    case MK61_SERVICE_ATAN:
      return mk_math::atan(x);
    case MK61_SERVICE_LN:
      return mk_math::ln(x);
    case MK61_SERVICE_LOG10:
      return mk_math::log10(x);
    case MK61_SERVICE_EXP:
      return mk_math::exp(x);
    case MK61_SERVICE_SQRT:
      return mk_math::sqrt(x);
    default:
      return mk_math::pow(x, y);
    }
  }
  static int format(char *out, u32 capacity, const char *text, va_list args) {
    return std::vsnprintf(out, capacity, text, args);
  }
  static bool file(u16 id, mk61_service_file &out) {
    program_store::Entry entry;
    if (!program_store::entry_by_id(id, entry))
      return false;
    out = {};
    out.id = id;
    out.parent = entry.parent_id;
    out.size = entry.data_len;
    out.type = (u32)entry.type;
    out.kind = (u32)entry.kind;
    std::memcpy(out.name, entry.name, sizeof(out.name));
    out.name[31] = 0;
    return true;
  }
  // Bounded SD traversal uses stable registry IDs; APP never sees FAT handles.
  bool find(const char *directory, unsigned type, int wanted, unsigned &count,
            mk61_service_file *out, unsigned depth = 0) {
    if (depth > 8)
      return false;
    for (unsigned skip = 0; skip < 4096; ++skip) {
      files::Entry entry{};
      unsigned used = 0;
      bool more = false;
      if (!files::list(directory, skip, &entry, 1, used, more) || !used)
        break;
      if (entry.name[0] == '.') {
        if (!more)
          break;
        continue;
      }
      char path[files::PATH_SIZE];
      if (!join(directory, entry.name, path))
        continue;
      if (entry.directory) {
        if (find(path, type, wanted, count, out, depth + 1))
          return true;
      } else {
        const bool match = (unsigned)script::file_type(path) == type;
        if (match) {
          if ((int)count == wanted && out) {
            program_store::Entry e;
            return script::register_file(path, e) && file(e.id, *out);
          }
          ++count;
        }
      }
      pump();
      if (!more)
        break;
    }
    return false;
  }
  bool filename(mk61_service_save_target &target, unsigned capacity) {
    if (!target.name || capacity < 2 || capacity > 256)
      return false;
    const auto saved = s.page_;
    s.page_ = ServicePage::PROMPT;
    s.runtime_graphics_ = false;
    std::snprintf(s.prompt_text_, sizeof(s.prompt_text_), "%s", target.name);
    s.prompt_length_ = (u16)std::strlen(s.prompt_text_);
    bool ok = false;
    for (;;) {
      u8 c;
      if (!s.pump_ || !s.pump_(s.pump_context_, c))
        continue;
      if (c == 0x1B || c == 0xB1)
        break;
      if (c == '\r' || c == '\n') {
        ok = s.prompt_length_ != 0;
        break;
      }
      if (c == 8 || c == 0x7F || c == 0xD4) {
        if (s.prompt_length_)
          --s.prompt_length_;
      } else if (c >= 32 && c < 127 &&
                 (unsigned)s.prompt_length_ + 1 < capacity && c != '/' &&
                 c != '\\')
        s.prompt_text_[s.prompt_length_++] = (char)c;
      s.prompt_text_[s.prompt_length_] = 0;
    }
    if (ok)
      std::snprintf(target.name, capacity, "%s", s.prompt_text_);
    s.page_ = saved;
    s.runtime_graphics_ = true;
    return ok;
  }
  bool choose(unsigned type, mk61_service_choice &choice) {
    unsigned total = 0;
    find("/", type, -1, total, nullptr);
    if (!total)
      return false;
    unsigned selected = 0;
    for (;;) {
      mk61_service_file f{};
      unsigned n = 0;
      if (!find("/", type, (int)selected, n, &f))
        return false;
      char text[96];
      std::snprintf(
          text, sizeof(text),
          "OPEN %u/%u\n\n%s\n\nArrows: choose\nEnter: open  Esc: cancel",
          selected + 1, total, f.name);
      script::show_text(text);
      const int key = take(true);
      if (key == 0x1B || key == 0xB1)
        return false;
      if (key == '\r' || key == '\n') {
        choice.file = f;
        choice.parent = f.parent;
        return true;
      }
      if (key == 0xB4 || key == 0xB5)
        selected = (selected + total - 1) % total;
      if (key == 0xB7 || key == 0xB6)
        selected = (selected + 1) % total;
    }
  }
  static u32 call(u32 op, u32 a, u32 b, u32 c, void *payload);
};
NativeHost *NativeHost::current = nullptr;
const mk61_service_keyboard NativeHost::mapping = [] {
  mk61_service_keyboard m{};
  static_assert(sizeof(m) == sizeof(keyboard_layout::MINI), "mapping ABI");
  std::memcpy(&m, &keyboard_layout::MINI, sizeof(m));
  return m;
}();
const mk61_app_api NativeHost::api = {
    MK61_APP_API_MAGIC,
    MK61_APP_API_VERSION,
    sizeof(mk61_app_api),
    MK61_APP_CAP_TIME | MK61_APP_CAP_TEXT_DISPLAY | MK61_APP_CAP_KEYBOARD |
        MK61_APP_CAP_LED | MK61_APP_CAP_SOUND | MK61_APP_CAP_FILES |
        MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEY_STATE,
    millis,
    service,
    delay,
    columns,
    rows,
    clear,
    write,
    poll,
    wait,
    led,
    blink,
    beep,
    stop,
    file_size,
    file_read,
    yes,
    width,
    height,
    graph_revision,
    graph_begin,
    graph_present,
    graph_end,
    held,
    query};
const mk61_app_services NativeHost::common = {MK61_APP_SERVICES_MAGIC,
                                              MK61_APP_SERVICES_VERSION,
                                              sizeof(mk61_app_services),
                                              &mapping,
                                              call,
                                              math,
                                              format,
#if defined(PICO_ON_DEVICE)
                                              native_runtime};
#else
                                              nullptr};
#endif

u32 NativeHost::call(u32 op, u32 a, u32 b, u32 c, void *payload) {
  auto &host = *current;
  auto &s = host.s;
  switch (op) {
  case MK61_SERVICE_CAPABILITIES:
    return MK61_SERVICE_CAP_UI | MK61_SERVICE_CAP_FILES |
           MK61_SERVICE_CAP_DIALOGS | MK61_SERVICE_CAP_MEMORY |
           MK61_SERVICE_CAP_EDITOR | MK61_SERVICE_CAP_FONT |
           MK61_SERVICE_CAP_REGISTERS | MK61_SERVICE_CAP_MATH |
           MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_NUMBER_IO |
           MK61_SERVICE_CAP_FLOAT_CONVERT | MK61_SERVICE_CAP_DEBUG_IO |
           MK61_SERVICE_CAP_SETUP | MK61_SERVICE_CAP_UI_FONT |
           MK61_SERVICE_CAP_TEXT_FONT | MK61_SERVICE_CAP_RESOURCES |
           MK61_SERVICE_CAP_EXPLORER | MK61_SERVICE_CAP_BASIC_GRAPHICS |
           MK61_SERVICE_CAP_APP_FLOW
#if defined(PICO_ON_DEVICE)
           | MK61_SERVICE_CAP_RUNTIME
#endif
        ;
  case MK61_SERVICE_UI_FONT:
    return ui_font_service::call(1, host.settings().ui_font_size, a, b, c,
                                 payload);
  case MK61_SERVICE_TEXT_FONT:
    switch (a) {
    case MK61_TEXT_FONT_BEGIN: {
      const i32 result = program_store_text_font_begin();
      if (result > 0)
        ++host.font_sessions;
      return (u32)result;
    }
    case MK61_TEXT_FONT_LOAD:
      return payload ? (u32)program_store_text_font_load_from(
                           (const char *)payload, program_store::ROOT_ID)
                     : (u32)MK61_TEXT_FONT_INVALID;
    case MK61_TEXT_FONT_RESTORE:
      return host.font_sessions ? (u32)program_store_text_font_restore()
                                : (u32)MK61_TEXT_FONT_UNAVAILABLE;
    case MK61_TEXT_FONT_END:
      if (!host.font_sessions)
        return (u32)MK61_TEXT_FONT_UNAVAILABLE;
      --host.font_sessions;
      return (u32)program_store_text_font_end();
    case MK61_TEXT_FONT_ACTIVATE:
      return script::activate_font();
    default:
      return (u32)MK61_TEXT_FONT_INVALID;
    }
  case MK61_SERVICE_RESOURCE_READ:
    return host.resource(a, payload);
  case MK61_SERVICE_LANGUAGE_ERROR_TEXT:
    if (a > (u32)language_vm::Error::GRAPHICS_ARGUMENT || b > 1 || c || payload)
      return 0;
    return (u32)(uintptr_t)tinybasic_diagnostic::reason((language_vm::Error)a,
                                                        b != 0);
  case MK61_SERVICE_BASIC_FRONTEND:
    if (a || b || c != sizeof(basic_graphics::NativeRequest) || !payload)
      return 0;
    return basic_graphics::process_native(
               *(basic_graphics::NativeRequest *)payload)
               ? 1
               : 2;
  case MK61_SERVICE_FILE_ACTIONS: {
    program_store::Entry e{};
    if (a > 0xFFFF || !program_store::entry_by_id((u16)a, e) ||
        e.kind != program_store::NodeKind::FILE)
      return 0;
    using T = program_store::ProgramType;
    u32 mask = loadable_module::EXPLORER_CAN_VIEW;
    if (e.type == T::MK61 || e.type == T::MK61_BINARY)
      mask |= loadable_module::EXPLORER_CAN_LOAD;
    if (e.type == T::MK61 || e.type == T::TINYBASIC || e.type == T::FOCAL ||
        e.type == T::APP || e.type == T::CHIP8)
      mask |= loadable_module::EXPLORER_CAN_RUN;
    if (e.type == T::MK61 || e.type == T::TINYBASIC || e.type == T::FOCAL ||
        e.type == T::TEXT || e.type == T::MARKDOWN)
      mask |= loadable_module::EXPLORER_CAN_EDIT;
    return mask;
  }
  case MK61_SERVICE_FILE_CHILD_COUNT:
  case MK61_SERVICE_FILE_CHILD: {
    if (a > 0xFFFF || (op == MK61_SERVICE_FILE_CHILD && (!payload || b > 4095)))
      return 0;
    const char *root = script::file_path((u16)a);
    if (!root)
      return 0;
    files::Entry entry{};
    unsigned used = 0;
    bool more = false;
    if (op == MK61_SERVICE_FILE_CHILD_COUNT) {
      unsigned n = 0;
      while (n < 4096 && files::list(root, n, &entry, 1, used, more) && used) {
        ++n;
        host.pump();
        if (!more)
          break;
      }
      return n;
    }
    char path[files::PATH_SIZE];
    program_store::Entry registered;
    return files::list(root, b, &entry, 1, used, more) && used &&
           join(root, entry.name, path) &&
           script::register_file(path, registered) &&
           file(registered.id, *(mk61_service_file *)payload);
  }
  case MK61_SERVICE_BASIC_GRAPHICS: {
    basic_graphics::Request request{};
    const bool control = !b && !c && !payload;
    if (control)
      request.operation = (basic_graphics::Operation)a;
    else if (a || b || c != sizeof(request) || !payload)
      return 0;
    auto &r = control ? request : *(basic_graphics::Request *)payload;
    const auto result = s.graph_request(r);
    if (s.graph_.active()) {
      script::show_frame(s.graph_.frame());
      s.runtime_graphics_ = false;
    }
    if (control && (r.operation == basic_graphics::Operation::WIDTH ||
                    r.operation == basic_graphics::Operation::HEIGHT ||
                    r.operation == basic_graphics::Operation::ACTIVE))
      return result == basic_graphics::Result::OK ? (u32)r.value : 0;
    return (u32)result + 1;
  }
  case MK61_SERVICE_DISPLAY:
    switch (a) {
    case MK61_SERVICE_DISPLAY_CLEAR:
      return clear();
    case MK61_SERVICE_DISPLAY_CURSOR:
      host.cursor_x = b;
      host.cursor_y = c;
      return 1;
    case MK61_SERVICE_DISPLAY_WRITE: {
      if (b > 255 || !mk8::valid_byte((u8)b))
        return 0;
      if (b == '\r') {
        host.cursor_x = 0;
        return 1;
      }
      if (b == '\n') {
        host.cursor_x = 0;
        ++host.cursor_y;
        return 1;
      }
      script::write_codepoint(host.cursor_x++, host.cursor_y,
                              mk8::codepoint((u8)b));
      if (host.cursor_x >= columns()) {
        host.cursor_x = 0;
        ++host.cursor_y;
      }
      return 1;
    }
    case MK61_SERVICE_DISPLAY_WRITE_CODEPOINT:
      script::write_codepoint(host.cursor_x++, host.cursor_y,
                              b <= 0xFFFF ? (u16)b : '?');
      return 1;
    case MK61_SERVICE_DISPLAY_FLOW_TEXT: {
      if (!payload)
        return 0;
      const auto &p = *(const mk61_service_text_flow *)payload;
      if (p.flags & ~3U)
        return 0;
      return script::flow_text(p.text, p.length, p.first_row, p.max_rows,
                               (p.flags & 1) != 0, (p.flags & 2) != 0);
    }
    case MK61_SERVICE_DISPLAY_PRINT:
      if (payload) {
        for (const char *p = (const char *)payload; *p; ++p) {
          if (*p == '\n') {
            host.cursor_x = 0;
            ++host.cursor_y;
          } else {
            if (host.cursor_x >= columns()) {
              host.cursor_x = 0;
              ++host.cursor_y;
            }
            script::write_text(host.cursor_x++, host.cursor_y, p, 1);
          }
        }
        return 1;
      }
      return 0;
    case MK61_SERVICE_DISPLAY_WIDTH:
      return 192;
    case MK61_SERVICE_DISPLAY_HEIGHT:
      return 64;
    case MK61_SERVICE_DISPLAY_GRAPHICS_MODE:
      return host.graphics;
    case MK61_SERVICE_DISPLAY_GRAPHICS:
      return 1;
    case MK61_SERVICE_DISPLAY_SUPPORTS_CURSOR:
      return 0;
    case MK61_SERVICE_DISPLAY_FLUSH:
    case MK61_SERVICE_DISPLAY_BEGIN_UPDATE:
    case MK61_SERVICE_DISPLAY_END_UPDATE:
    case MK61_SERVICE_DISPLAY_END_VIEWPORT:
    case MK61_SERVICE_DISPLAY_END_UI_TEXT:
    case MK61_SERVICE_DISPLAY_CURSOR_OFF:
      return 1;
    default:
      return 0;
    }
  case MK61_SERVICE_KEYBOARD:
    if (a == MK61_SERVICE_KEY_SCAN) {
      host.pump();
      return 1;
    }
    if (a == MK61_SERVICE_KEY_ANY)
      return host.count != 0;
    if (a == MK61_SERVICE_KEY_POLL || a == MK61_SERVICE_KEY_GET ||
        a == MK61_SERVICE_KEY_WAIT) {
      const int key = host.take(a == MK61_SERVICE_KEY_WAIT);
      if (key < 0)
        return (u32)-1;
      if (key == 0x1B || key == 0xB1)
        return mapping.esc;
      if (key == '\r' || key == '\n')
        return mapping.ok;
      if (key == 0xB4)
        return mapping.left;
      if (key == 0xB7)
        return mapping.right;
      if (key == 0xB5)
        return mapping.shg_left;
      if (key == 0xB6)
        return mapping.shg_right;
      const int scan = controls::scan((u8)key);
      return scan < 0 ? MK61_APP_KEY_RAW_BASE + key : (u32)scan;
    }
    if (a == MK61_SERVICE_KEY_PRESSED)
      return held(keyboard_layout::logical_key(keyboard_layout::MINI, (i32)b));
    if (a == MK61_SERVICE_KEY_LAST)
      return host.last;
    return 0;
  case MK61_SERVICE_SETTINGS:
    if (a == MK61_SERVICE_LANGUAGE)
      return s.russian_;
    if (a == MK61_SERVICE_ANGLE)
      return MK61Emu_GetAngleUnit();
    if (a == MK61_SERVICE_REGISTER_F)
      return core_61::expanded_program_is_on();
    return a == MK61_SERVICE_VOLUME ? host.settings().volume : 0;
  case MK61_SERVICE_RANDOM: {
    static u32 word = 0x1F3137;
    word = word * 1664525 + 1013904223;
    return word;
  }
  case MK61_SERVICE_MICROS:
#if defined(PICO_ON_DEVICE)
    return time_us_32();
#else
    return millis() * 1000;
#endif
  case MK61_SERVICE_TEXT_ROWS: {
    if (!payload || a > MK61_SERVICE_MAX_ROWS)
      return 0;
    const auto lines = (const char *const *)payload;
    clear();
    for (unsigned row = 0; row < a && row < rows(); ++row) {
      if (!lines[row])
        return 0;
      script::write_text(0, row, lines[row],
                         (unsigned)strnlen(lines[row], columns()));
    }
    return 1;
  }
  case MK61_SERVICE_MENU: {
    if (!payload || !a || a > MK61_SERVICE_MAX_ROWS)
      return 0;
    const auto items = (const mk61_service_menu_item *)payload;
    unsigned selected = 0;
    for (;;) {
      clear();
      const unsigned visible = rows(),
                     first = selected >= visible ? selected - visible + 1 : 0;
      for (unsigned row = 0; row < visible && first + row < a; ++row) {
        const unsigned i = first + row;
        script::write_text(0, row, i == selected ? ">" : " ", 1);
        if (items[i].text)
          script::write_text(1, row, items[i].text,
                             (unsigned)strnlen(items[i].text, columns() - 1));
      }
      const int key = host.take(true);
      if (key == 0x1B || key == 0xB1)
        return 1;
      if ((key == 0xB4 || key == 0xB5) && selected)
        --selected;
      if ((key == 0xB7 || key == 0xB6) && selected + 1 < a)
        ++selected;
      if ((key == '\r' || key == '\n') &&
          (!items[selected].action || items[selected].action()))
        return 1;
    }
  }
  case MK61_SERVICE_MEMORY_ACQUIRE: {
    if (!payload || a > 1 || !c || c > 65535 || host.leases[a].data)
      return 0;
    auto &lease = *(mk61_service_lease *)payload;
    auto *data = (u8 *)std::calloc(1, c);
    if (!data)
      return 0;
    host.leases[a] = {data, c};
    lease = {};
    lease.data = data;
    lease.size = c;
    lease.fresh = 1;
    return 1;
  }
  case MK61_SERVICE_MEMORY_RELEASE:
    if (!payload || a > 1)
      return 0;
    if (((mk61_service_lease *)payload)->data != host.leases[a].data)
      return 0;
    std::free(host.leases[a].data);
    host.leases[a] = {};
    *(mk61_service_lease *)payload = {};
    return 1;
  case MK61_SERVICE_MEMORY_DATA:
    return a < 2 ? (u32)(uintptr_t)host.leases[a].data : 0;
  case MK61_SERVICE_FONT: {
    if (!payload || a > 1 || b > 0xFFFF)
      return 0;
    builtin_font::Raster raster;
    if (!builtin_font::decode(a ? builtin_font::FaceId::FONT_3X5
                                : builtin_font::FaceId::FONT_5X8,
                              (u16)b, raster))
      return 0;
    auto &g = *(mk61_service_glyph *)payload;
    g = {};
    g.width = raster.width;
    g.height = raster.height;
    for (unsigned y = 0; y < g.height && y < 8; ++y)
      for (unsigned x = 0; x < g.width && x < 8; ++x)
        if (fmk::bitmapPixel(raster.data, raster.width, x, y))
          g.pixels[y] |= (u8)(0x80U >> x);
    return 1;
  }
  case MK61_SERVICE_NUMBER_FORMAT: {
    if (!payload)
      return 0;
    auto &p = *(mk61_service_number_format *)payload;
    return number_format::general(p.value, (u8)p.significant_digits, p.output,
                                  p.capacity);
  }
  case MK61_SERVICE_NUMBER_PARSE: {
    if (!payload)
      return 0;
    auto &p = *(mk61_service_number_parse *)payload;
    if (!p.input)
      return 0;
    const char *end = p.input;
    p.value = mk_math::strtod(p.input, &end);
    const bool ok = end != p.input;
    p.consumed = (u32)(end - p.input);
    return ok;
  }
  case MK61_SERVICE_REF_READ:
  case MK61_SERVICE_REF_WRITE:
    if (!payload || a > MK61_SERVICE_REF_R || b > 15)
      return 0;
    return op == MK61_SERVICE_REF_READ
               ? mk61_ref::read({(mk61_ref::Kind)a, (u8)b}, *(double *)payload)
               : mk61_ref::write({(mk61_ref::Kind)a, (u8)b},
                                 *(double *)payload);
  case MK61_SERVICE_REF_PARSE: {
    if (!payload)
      return 0;
    auto &p = *(mk61_service_ref_parse *)payload;
    mk61_ref::Ref ref;
    if (!mk61_ref::parse_name(p.name, ref))
      return 0;
    p.kind = (u32)ref.kind;
    p.reg = ref.reg;
    return 1;
  }
  case MK61_SERVICE_FLOAT_CONVERT: {
    if (!payload)
      return 0;
    auto &p = *(mk61_service_float_convert *)payload;
    float f;
    if (a == MK61_FLOAT_FROM_DOUBLE) {
      f = (float)p.value;
      std::memcpy(&p.bits, &f, 4);
    } else {
      std::memcpy(&f, &p.bits, 4);
      p.value = f;
    }
    return 1;
  }
  case MK61_SERVICE_FILE_COUNT: {
    unsigned n = 0;
    host.find("/", a, -1, n, nullptr);
    return n;
  }
  case MK61_SERVICE_FILE_ENTRY:
    if (!payload)
      return 0;
    if (!a)
      return file((u16)b, *(mk61_service_file *)payload);
    else {
      unsigned n = 0;
      return host.find("/", c, (int)b, n, (mk61_service_file *)payload);
    }
  case MK61_SERVICE_FILE_RESOLVE: {
    if (!payload || !c || a > 0xFFFF)
      return (u32)storage_path::Status::NOT_FOUND;
    program_store::Entry e;
    const auto result = storage_path::resolve_file(
        (u16)a, (const char *)(uintptr_t)c, (program_store::ProgramType)b, e);
    if (result == storage_path::Status::OK)
      (void)file(e.id, *(mk61_service_file *)payload);
    return (u32)result;
  }
  case MK61_SERVICE_FILE_CHOOSE:
    return payload && host.choose(a, *(mk61_service_choice *)payload);
  case MK61_SERVICE_FILE_SAVE_TARGET:
    return payload && host.filename(*(mk61_service_save_target *)payload, c);
  case MK61_SERVICE_FILE_WRITE: {
    if (!payload || c > 12 || c == 1)
      return 0;
    auto &p = *(mk61_service_write *)payload;
    char name[256], path[files::PATH_SIZE];
    if (!utf8(p.name, name, sizeof(name)))
      return 0;
    if (!std::strrchr(name, '.')) {
      const unsigned n = std::strlen(name);
      if (n + std::strlen(extension(c)) >= sizeof(name))
        return 0;
      std::strcat(name, extension(c));
    }
    const char *base = script::file_path((u16)a);
    if (!base || !join(base, name, path) || p.size > 65534)
      return 0;
    if (b != MK61_SERVICE_INVALID_ID) {
      const char *old = script::file_path((u16)b);
      if (!old)
        return 0;
      std::snprintf(path, sizeof(path), "%s", old);
    }
    if (!files::write(path, p.data, p.size))
      return 0;
    program_store::Entry e;
    if (!script::register_file(path, e))
      return 0;
    p.id = e.id;
    return 1;
  }
  case MK61_SERVICE_FILE_REMOVE: {
    const char *path = script::file_path((u16)a);
    return path && files::remove(path);
  }
  case MK61_SERVICE_FILE_EXISTS: {
    if (!payload)
      return 0;
    program_store::Entry e;
    return storage_path::resolve_file(
               program_store::ROOT_ID, (const char *)payload,
               (program_store::ProgramType)a, e) == storage_path::Status::OK;
  }
  case MK61_SERVICE_EDITOR_SCROLL:
  case MK61_SERVICE_EDITOR_DRAW: {
    if (!payload)
      return 0;
    auto &e = *(mk61_service_editor *)payload;
    if (!e.source || e.length > 65534 || e.cursor > e.length)
      return 0;
    const unsigned cols = columns(), visible = rows();
    unsigned cursor_row = 0, cursor_col = 0;
    for (unsigned i = 0; i < e.cursor; ++i) {
      if (e.source[i] == '\n' || ++cursor_col >= cols) {
        ++cursor_row;
        cursor_col = 0;
      }
    }
    if (cursor_row < e.top)
      e.top = cursor_row;
    if (cursor_row >= e.top + visible)
      e.top = cursor_row - visible + 1;
    if (op == MK61_SERVICE_EDITOR_DRAW) {
      clear();
      unsigned row = 0, col = 0;
      for (unsigned i = 0; i < e.length && row < e.top + visible; ++i) {
        const char ch = e.source[i];
        if (ch == '\n') {
          ++row;
          col = 0;
          continue;
        }
        if (row >= e.top)
          script::write_text(col, row - e.top, &ch, 1);
        if (++col >= cols) {
          col = 0;
          ++row;
        }
      }
      if (cursor_row >= e.top && cursor_row < e.top + visible)
        script::write_text(cursor_col, cursor_row - e.top, "_", 1);
    }
    return 1;
  }
  case MK61_SERVICE_EDITOR_KEY: {
    if (!payload)
      return 0;
    auto &e = *(mk61_service_edit_key *)payload;
    if (!e.source || e.capacity < 1 || e.capacity > 65535 ||
        e.length >= e.capacity || e.cursor > e.length)
      return 0;
    u16 len = (u16)e.length, cur = (u16)e.cursor;
    bool changed = false;
    const u8 key = host.last;
    if (key == 8 || key == 0x7F || key == 0xD4)
      changed = text_editor::backspace(e.source, len, cur);
    else if (key == 0xB4) {
      if (cur)
        --cur;
      changed = true;
    } else if (key == 0xB7) {
      if (cur < len)
        ++cur;
      changed = true;
    } else if (key >= 32 && key < 127) {
      const char text[] = {char(key), 0};
      changed =
          text_editor::insert_text(e.source, len, cur, (u16)e.capacity, text);
    }
    e.length = len;
    e.cursor = cur;
    e.sms_active = e.shift = 0;
    return changed;
  }
  case MK61_SERVICE_SETUP:
    return host.setup(a, b, c, payload);
  case MK61_SERVICE_DEBUG_WRITE:
    if (!payload || a > 128)
      return 0;
    std::printf("%.*s", (int)a, (const char *)payload);
    return 1;
  default:
    return 0;
  }
}

u32 NativeHost::resource(u32 op, void *payload) {
  const u32 revision = files::revision();
  if (op == 0 || op == 4)
    return revision;
  if (op == 3) {
    if (!payload)
      return 1;
    const auto &r = *(const mk61_service_resource_bytes *)payload;
    program_store::Entry entry{};
    if (!r.next || r.revision != revision ||
        !program_store::entry_by_id(r.id, entry) ||
        entry.data_len != r.source_size)
      return 0;
    u8 bytes[128];
    for (unsigned offset = 0; offset < r.source_size;) {
      const unsigned n = r.source_size - offset < sizeof(bytes)
                             ? r.source_size - offset
                             : sizeof(bytes);
      if (file_read(r.id, offset, bytes, n) != n)
        return 0;
      for (unsigned i = 0; i < n; ++i)
        if (!r.next(r.context, bytes[i]))
          return 0;
      offset += n;
      pump();
      if (files::revision() != revision)
        return 0;
    }
    return files::revision() == revision;
  }
  if (op == 2 && payload) {
    const auto &r = *(const mk61_service_resource_stream *)payload;
    if (r.reserved || r.revision != revision || !r.append ||
        !language_vm::valid_resource_recipe(r.recipe, r.recipe_size,
                                            r.source_size))
      return 0;
    const auto read = [](void *context, u16 offset, u8 *out, u16 n) {
      const auto &r = *(const mk61_service_resource_stream *)context;
      return files::revision() == r.revision &&
             file_read(r.id, offset, out, n) == n &&
             files::revision() == r.revision;
    };
    return language_vm::resource_text(r.recipe, read, (void *)&r, r.append,
                                      r.context) &&
           files::revision() == revision;
  }
  if ((op != 1 && op != 5) || !payload)
    return 0;
  const auto &r = *(const mk61_service_resource *)payload;
  if (r.revision != revision || !r.output || r.reserved > (op == 5 ? 1U : 0U))
    return 0;
  return file_read(r.id, r.offset, r.output, r.length) == r.length &&
         files::revision() == revision;
}
u32 NativeHost::setup(u32 op, u32 a, u32 b, void *payload) {
  auto settings = this->settings();
  const auto save = [&]() { return s.ui_ && s.ui_->apply_settings(settings); };
  switch (op) {
  case MK61_SETUP_VERSION:
    return MK61_SETUP_API_VERSION;
  case MK61_SETUP_FEATURES:
    return MK61_SETUP_FEATURE_TEXT_PROFILE |
           MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE |
           MK61_SETUP_FEATURE_UI_FONT | MK61_SETUP_FEATURE_UI_FONT_CATALOG |
           MK61_SETUP_FEATURE_CALCULATOR_FONT;
  case MK61_SETUP_RTC_CALIBRATION:
    if (!a)
      return (u32)clock::calibration();
    if ((i32)b < -500 || (i32)b > 500)
      return 0;
    settings.rtc_ppm = (i16)b;
    if (!save())
      return 0;
    clock::calibrate((i32)b);
    return 1;
  case MK61_SETUP_RTC_READ:
  case MK61_SETUP_RTC_WRITE: {
    if (!payload)
      return 0;
    auto &p = *(mk61_setup_datetime *)payload;
    if (op == MK61_SETUP_RTC_WRITE)
      return clock::set({(int)p.year, (int)p.month, (int)p.day, (int)p.hour,
                         (int)p.minute, (int)p.second});
    const auto d = clock::get();
    p = {(u32)d.year, (u32)d.month,  (u32)d.day,
         (u32)d.hour, (u32)d.minute, (u32)d.second};
    return 1;
  }
  case MK61_SETUP_HARDWARE: {
    if (!payload)
      return 0;
    auto &p = *(mk61_setup_hardware *)payload;
    p = {};
    p.idcode = 0x2040;
    p.flash_kb = 2048;
    std::strcpy(p.rtc_source, "XOS");
    std::strcpy(p.display, "PicoCalc 320x320");
    return 1;
  }
  case MK61_SETUP_FONT_READ: {
    if (!payload)
      return 0;
    const auto p = script::text_profile();
    *(mk61_setup_profile *)payload = {p.rows, p.width, p.height, p.line_gap};
    return 1;
  }
  case MK61_SETUP_FONT_APPLY: {
    if (!payload)
      return 0;
    const auto &p = *(const mk61_setup_profile *)payload;
    settings.text_rows = p.rows;
    settings.text_width = p.width;
    settings.text_height = p.height;
    settings.text_gap = p.gap;
    return valid_settings(settings) && save() &&
           script::text_profile({p.rows, p.width, p.height, p.gap});
  }
  case MK61_SETUP_FONT_PREVIEW:
    if (!payload || !a || a > prepared_font::MAX_IMAGE_SIZE)
      return 0;
    if (!preview) {
      if (program_store_text_font_begin() <= 0)
        return 0;
      preview = true;
      ++font_sessions;
    }
    return script::install_prepared((const u8 *)payload, a);
  case MK61_SETUP_FONT_PREVIEW_END:
    if (preview) {
      preview = false;
      --font_sessions;
      program_store_text_font_end();
    }
    return 1;
  case MK61_SETUP_PREPARED_FONT_INSTALL: {
    if (!payload)
      return (u32)MK61_TEXT_FONT_INVALID;
    const auto &p = *(const mk61_setup_prepared_font *)payload;
    if (p.role != MK61_PREPARED_FONT_TEXT || p.reserved || p.flags)
      return (u32)MK61_TEXT_FONT_UNSUPPORTED;
    prepared_font::Face font;
    if (!font.open(p.data, p.size) ||
        (p.expected_height && p.expected_height != font.metrics().height))
      return (u32)MK61_TEXT_FONT_INVALID;
    return script::install_prepared(p.data, p.size)
               ? (u32)MK61_TEXT_FONT_OK
               : (u32)MK61_TEXT_FONT_UNAVAILABLE;
  }
  case MK61_SETUP_FONT_RESTORE:
    return script::text_profile({settings.text_rows, settings.text_width,
                                 settings.text_height, settings.text_gap});
  case MK61_SETUP_UI_FONT_READ:
    if (!payload)
      return 0;
    *(mk61_setup_ui_font *)payload = {1, settings.ui_font_size};
    return 1;
  case MK61_SETUP_UI_FONT_APPLY: {
    if (!payload)
      return 0;
    const auto &p = *(const mk61_setup_ui_font *)payload;
    if (p.family != 1 && p.family != 2)
      return 0;
    settings.ui_font_size = p.size;
    return save();
  }
  case MK61_SETUP_UI_FONT_COUNT:
    return 3;
  case MK61_SETUP_UI_FONT_CURRENT:
    return settings.ui_font_size;
  case MK61_SETUP_UI_FONT_ITEM:
    if (!payload || a >= 3)
      return 0;
    {
      auto &item = *(mk61_setup_ui_font_item *)payload;
      item = {};
      item.key = item.size = (u8)(12 + 2 * a);
      std::snprintf(item.name, sizeof(item.name), "Ark Pixel %u", item.size);
      return 1;
    }
  case MK61_SETUP_UI_FONT_APPLY_ITEM:
    if (a != 12 && a != 14 && a != 16)
      return 0;
    settings.ui_font_size = (u8)a;
    return save();
  case MK61_SETUP_UI_FONT_STEP:
    if (!payload || ((i32)b != -1 && b != 1))
      return 0;
    {
      auto &item = *(mk61_setup_ui_font_item *)payload;
      item = {};
      const unsigned current = a == 12 ? 0 : a == 16 ? 2 : 1;
      item.key = item.size =
          (u8)(12 + 2 * ((current + ((i32)b < 0 ? 2 : 1)) % 3));
      std::snprintf(item.name, sizeof(item.name), "Ark Pixel %u", item.size);
      return 1;
    }
  case MK61_SETUP_CALCULATOR_FONT_READ:
    return settings.calculator_font;
  case MK61_SETUP_CALCULATOR_FONT_APPLY:
    if (a > 1)
      return 0;
    settings.calculator_font = (u8)a;
    return save();
  case MK61_SETUP_TEXT:
    if (!payload || a >= rows())
      return 0;
    script::write_text(0, a, (const char *)payload,
                       (unsigned)strnlen((const char *)payload, columns()));
    return 1;
  case MK61_SETUP_LCD_CHAR:
    return 0; // Character-LCD CGRAM is absent on PicoCalc.
  case MK61_SETUP_PHASE:
    return 1;
  default:
    return 0;
  }
}

u8 Services::run_handled(const char *path, u16 magic) {
  program_store::Entry document;
  if (!script::register_file(path, document))
    return 4;
  char parent[files::PATH_SIZE];
  std::snprintf(parent, sizeof(parent), "%s", path);
  char *slash = std::strrchr(parent, '/');
  if (slash == parent)
    slash[1] = 0;
  else if (slash)
    *slash = 0;
  else
    return 4;
  const char *roots[] = {parent,          "/app",    "/Apps",
                         "/Applications", "/System", "/"};
  for (const char *root : roots)
    for (unsigned skip = 0; skip < 1024; ++skip) {
      files::Entry entry{};
      unsigned used = 0;
      bool more = false;
      if (!files::list(root, skip, &entry, 1, used, more) || !used)
        break;
      char candidate[files::PATH_SIZE];
      const char *ext = std::strrchr(entry.name, '.');
      if (!entry.directory && ext &&
          (!std::strcmp(ext, ".APP") || !std::strcmp(ext, ".app")) &&
          join(root, entry.name, candidate)) {
        u8 bytes[64];
        loadable_module::Header header{};
        if (files::read_range(candidate, 0, bytes, sizeof(bytes), used) &&
            used == 64 &&
            loadable_module::decode_header(
                bytes, loadable_module::MAX_CONTAINER_SIZE, header) ==
                loadable_module::HeaderStatus::OK &&
            header.handled_type_magic == magic)
          return run_native(candidate, document.id);
      }
      if (!more)
        break;
    }
  message("Install a Pico H APP for this file type", ServicePage::BROWSER);
  return 1;
}
u8 Services::run_native(const char *path, u16 file) {
  if (NativeHost::current || running_ || files::usb_active())
    return 3;
  program_store::Entry root;
  if (!script::register_file(path, root))
    return 4;
  struct Backend {
    Services *self;
    u16 root, document;
  } backend{this, root.id, file};
  alignas(8) u8 context[MK61_APP_FLOW_USER_CONTEXT_SIZE]{};
  auto first = mk61_app_flow_to(MK61_APP_KIND_APPLICATION, root.id, 0);
  if (file != 0xFFFF) {
    const u32 args[] = {(u32)(uintptr_t)&NativeHost::api, file, 0, 0};
    std::memcpy(context, args, sizeof(args));
    first = mk61_app_flow_direct(MK61_APP_KIND_APPLICATION, root.id,
                                (u16)loadable_module::Command::FILE_OPEN, 0);
  }
  u32 result = 0;
  const auto status = app_flow::run(
      first, context, sizeof(context), result,
      [](void *raw, const app_flow::Target &target, app_flow::Step &step) {
        auto &backend = *(Backend *)raw;
        if (target.kind != MK61_APP_KIND_APPLICATION)
          return MK61_FLOW_UNAVAILABLE;
        const char *path = script::file_path(target.file_id);
        if (!path)
          return MK61_FLOW_INVALID_MODULE;
        const u8 code = backend.self->run_native_step(
            path, target.file_id == backend.root ? backend.document : 0xFFFF,
            &step);
        return code ? code == 3 ? MK61_FLOW_BUSY : MK61_FLOW_IO_ERROR
                    : MK61_FLOW_OK;
      },
      &backend);
  if (status != MK61_FLOW_OK)
    return status == MK61_FLOW_BUSY ? 3 : 2;
  std::printf("APP_FLOW_RESULT=%lu\n", (unsigned long)result);
  if (result) {
    runtime_graphics_ = false;
    message("APP returned an error",
            m61_text::active() ? ServicePage::CLOSED : ServicePage::BROWSER);
  }
  return result < 256 ? (u8)result : 5;
}
u8 Services::run_native_step(const char *path, u16 file, mk61_app_flow *flow) {
  if (NativeHost::current || running_ || files::usb_active())
    return 3;
  u8 encoded[64];
  unsigned used = 0;
  files::Entry info;
  loadable_module::Header header{};
  if (!files::stat(path, info) ||
      !files::read_range(path, 0, encoded, sizeof(encoded), used) ||
      used != 64) {
    message("APP: cannot read header", ServicePage::BROWSER);
    return 4;
  }
  if (loadable_module::decode_header(
          encoded, loadable_module::MAX_CONTAINER_SIZE, header) !=
          loadable_module::HeaderStatus::OK ||
      info.size != 64 + header.stored_size ||
      header.kind != loadable_module::Kind::APPLICATION) {
    message("APP: requires ABI 6 / Pico H (ARMv6-M) build",
            ServicePage::BROWSER);
    return 1;
  }
  auto *allocation = (u8 *)std::calloc(1, header.memory_size + 7);
  if (!allocation) {
    message("APP: not enough RAM", ServicePage::BROWSER);
    return 3;
  }
  auto *memory = (u8 *)(((uintptr_t)allocation + 7) & ~(uintptr_t)7);
  struct Source {
    const char *path;
    Services *service;
  } source{path, this};
  const loadable_module::Reader reader{
      &source, [](void *raw, u32 offset, u8 *out, usize n) {
        auto &source = *(Source *)raw;
        unsigned got = 0;
        u8 key = 0;
        if (source.service->pump_)
          (void)source.service->pump_(source.service->pump_context_, key);
        return n <= 65535 &&
               files::read_range(source.path, 64 + offset, out, (unsigned)n,
                                 got) &&
               got == n;
      }};
#if defined(PICO_ON_DEVICE)
  const u32 address = (u32)(uintptr_t)memory;
#else
  const u32 address =
      0x20026000; // Decode-only host test; ARM code is never executed.
#endif
  if (!loadable_module::decode_image(header, reader, memory, address)) {
    std::free(allocation);
    message("APP: damaged image / CRC / relocation", ServicePage::BROWSER);
    return 1;
  }
  std::snprintf(path_, sizeof(path_), "%s", path);
  page_ = ServicePage::CONSOLE;
  runtime_ = "APP";
  runtime_graphics_ = true;
  running_ = true;
  script::show_text("");
  u32 result = 5;
  {
    NativeHost host(*this);
#if defined(PICO_ON_DEVICE)
    __dmb();
    __isb();
    const auto entry =
        (loadable_module::Entry)((uintptr_t)memory + header.entry_offset + 1);
    result = entry((u32)loadable_module::Command::INITIALIZE,
                   (u32)(uintptr_t)&NativeHost::api, header.image_crc32,
                   (u32)header.kind, 0);
    if (!result && flow && (flow->current.flags & MK61_APP_FLOW_DIRECT)) {
      const unsigned offset = 4U * (flow->current.flags >> 1);
      u32 args[4];
      if (!flow->context || offset > flow->context_size ||
          sizeof(args) > flow->context_size - offset)
        result = 5;
      else {
        std::memcpy(args, (u8 *)flow->context + offset, sizeof(args));
        result = entry(flow->current.phase, args[0], args[1], args[2], args[3]);
        mk61_app_flow_return(flow, result, MK61_FLOW_OK);
        result = 0;
      }
    } else if (!result && flow &&
               entry(MK61_APP_FLOW_INFO, 0, 0, 0, 0) == MK61_APP_FLOW_MAGIC) {
      const u32 step_result =
          entry(MK61_APP_FLOW_STEP, (u32)(uintptr_t)flow, 0, 0, 0);
      result = step_result == 1 ? 0 : 5;
    } else if (!result) {
      result =
          entry((u32)(file == 0xFFFF ? loadable_module::Command::APPLICATION_RUN
                                     : loadable_module::Command::FILE_OPEN),
                (u32)(uintptr_t)&NativeHost::api, file, 0, 0);
      if (flow) {
        mk61_app_flow_return(flow, result, MK61_FLOW_OK);
        result = 0;
      }
    }
#endif
    NativeHost::stop();
    script::led(false);
  }
  std::free(allocation);
  runtime_graphics_ = true;
  running_ = false;
  runtime_ = "NONE";
  std::printf("APP_RESULT=%lu CRC=%08lX MEMORY=%lu\n", (unsigned long)result,
              (unsigned long)header.image_crc32,
              (unsigned long)header.memory_size);
  if (result) {
    runtime_graphics_ = false;
    message("APP returned an error",
            m61_text::active() ? ServicePage::CLOSED : ServicePage::BROWSER);
  } else if (m61_text::active()) {
    runtime_graphics_ = false;
    page_ = ServicePage::CLOSED;
  } else {
    viewing_ = true;
    page_ = ServicePage::CONSOLE;
    std::snprintf(status_, sizeof(status_), "APP finished; Enter / Esc: files");
  }
  return result < 256 ? (u8)result : 5;
}
} // namespace picocalc
