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
#include "language_cache.hpp"
#include "number_format.hpp"
#include "script.hpp"
#include "services.hpp"
#include "text_input.hpp"
#include "storage_path.hpp"
#include "terminal_core.hpp"
#include "text_editor.hpp"
#include "loadable_system_editor.hpp"
#include "tinybasic_diagnostic.hpp"
#include "ui_font_service.hpp"
#include "fonts.hpp"
#include "ui_font_catalog.hpp"
#include "diagnostics.hpp"
#include "native_display.hpp"
#include "native_keyboard.hpp"
#include "loadable_buffer_services.hpp"
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
                              ".state.txt", ".fmk", ".wbmp", ".app", ".ch8",
                              ".md",  ".bin", ".mks"};
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
  explicit NativeHost(Services &service,bool native=false) : s(service), display(settings(),native) {
    s.graph_.reset();
    s.graph_width_=display.width();s.graph_height_=display.height();
    current = this;
    controls::set_listener([](void* raw,KeyEvent event) {
      auto& host=*(NativeHost*)raw;host.input_received=true;host.keyboard.event(event,millis());
    },this);
  }
  ~NativeHost() {
    controls::set_listener(nullptr,nullptr);
    while (font_sessions) {
      program_store_text_font_end();
      --font_sessions;
    }
    s.graph_.reset();
    s.graph_width_=s.graph_height_=320;
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
  NativeDisplay display;
  NativeKeyboard keyboard;
  bool input_received=false;
  struct Lease {
    u8 *data = nullptr;
    unsigned size = 0;
  } leases[2];
  loadable_buffers::Session buffers;
  bool graphics = false;
  unsigned font_sessions = 0;
  bool preview = false;
  Settings settings() const { return s.ui_ ? s.ui_->settings() : Settings{}; }
  u32 setup(u32 op, u32 a, u32 b, void *payload);
  u32 resource(u32 op, u32 inode, void *payload);
  void pump() {
    display.settings(settings());display.flush();
    input_received=false;
    u8 key = 0;
    if(s.pump_ && s.pump_(s.pump_context_,key) && !input_received) controls::pulse(key,millis());
    controls::service(millis());
  }
  int take(bool wait = false) {
    do {
      pump();
      const int key=keyboard.press();if(key>=0) return key;
    } while (wait);
    return -1;
  }
  int raw_key(int state,bool wait) {
    do { pump();const int key=keyboard.raw(state);if(key>=0) return key; } while(wait);
    return -1;
  }
  static void service() { current->pump(); }
  static void delay(u32 ms) {
    const u32 start = millis();
    while ((u32)(millis() - start) < ms)
      current->pump();
  }
  static u32 columns() { current->display.settings(current->settings());return current->display.columns(); }
  static u32 rows() { current->display.settings(current->settings());return current->display.rows(); }
  static u32 clear() {
    return current->display.clear();
  }
  static u32 write(u32 x, u32 y, const char *text, u32 n) {
    if (!text || n > MK61_APP_MAX_TEXT_BYTES || x >= columns() || y >= rows())
      return 0;
    return current->display.write(x,y,text,n);
  }
  static i32 poll() {
    const int c = current->take();
    if(c>=0) current->keyboard.handoff(current->keyboard.last(),millis());
    return c < 0 ? -1 : controls::logical((u8)c);
  }
  static i32 wait() {
    const int c=current->take(true);current->keyboard.handoff(current->keyboard.last(),millis());
    return controls::logical((u8)c);
  }
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
    return id < 0xFFFF && program_store::entry_by_id((u16)id, e) &&
                   e.kind == program_store::NodeKind::FILE ? e.data_len : UINT32_MAX;
  }
  static u32 file_read(u32 id, u32 offset, u8 *out, u32 n) {
    if(id>=0xFFFF || offset>65535 || n>65535 || (!out && n)) return UINT32_MAX;
    u16 got=0;
    if(!program_store::read_range_id((u16)id,(u16)offset,out,(u16)n,&got)) return UINT32_MAX;
    return got;
  }
  static u32 beep(u32 hz, u32 ms, u32 volume) {
    if (hz > 65535 || !ms || ms > 65535 || volume > 100)
      return 0;
    script::tone(hz, ms, volume);
    return 1;
  }
  static void stop() {
    script::tone(0, 0);
  }
  static void led(u32 on) { script::led(on != 0); }
  static u32 blink(u32 n, u32 on, u32 off) {
    return script::led_blink(n,on,off);
  }
  static u32 yes() { return 1; }
  static u32 width() { return current->display.width(); }
  static u32 height() { return current->display.height(); }
  static u32 graph_revision() { return current->display.revision(); }
  static u32 graph_begin() {
    return current->graphics = current->display.bitmap_begin();
  }
  static u32 graph_present(const u8 *data, u32 n) {
    if (!current->graphics || !data || n != current->display.width()*current->display.height()/8)
      return 0;
    return current->display.bitmap_present(data,n);
  }
  static void graph_end() { current->display.bitmap_end();current->graphics = false; }
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
    case MK61_SERVICE_POW:
      return mk_math::pow(x, y);
    default:return 0;
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
    const bool saved_graphics=s.runtime_graphics_;
    s.page_ = ServicePage::PROMPT;
    s.runtime_graphics_ = false;
    usize utf8_size=0;
    const unsigned initial=(unsigned)std::strlen(target.name);
    if(initial>=capacity || !mk8::to_utf8((const u8*)target.name,initial,(u8*)s.prompt_text_,sizeof(s.prompt_text_)-1,utf8_size)) {
      s.page_=saved;s.runtime_graphics_=saved_graphics;return false;
    }
    s.prompt_length_=(u16)utf8_size;s.prompt_text_[utf8_size]=0;
    bool ok = false;
    for (;;) {
      const u8 c=(u8)take(true);
      if (c == 0x1B || c == 0xB1) { keyboard.handoff(controls::raw_key(c),millis());break; }
      if (c == '\r' || c == '\n') {
        usize used=0;u8 converted[256];
        if(s.prompt_length_ && mk8::from_utf8((const u8*)s.prompt_text_,s.prompt_length_,converted,capacity-1,used)) {
          std::memcpy(target.name,converted,used);target.name[used]=0;
          keyboard.handoff(controls::raw_key(c),millis());ok=true;break;
        }
        continue;
      }
      if(c==0x88) s.input_russian_=!s.input_russian_;
      else if(c==8 || c==0x7F || c==0xD4) text_input::backspace_utf8(s.prompt_text_,s.prompt_length_);
      else if(text_input::mapped(c,s.input_russian_)!='/' && text_input::mapped(c,s.input_russian_)!='\\')
        text_input::append_utf8(s.prompt_text_,s.prompt_length_,sizeof(s.prompt_text_),c,s.input_russian_);
    }
    s.page_ = saved;
    s.runtime_graphics_ = saved_graphics;
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
      clear();display.call(MK61_SERVICE_DISPLAY_PRINT,0,0,text);
      const int key = take(true);
      if (key == 0x1B || key == 0xB1) { keyboard.handoff(controls::raw_key((u8)key),millis());return false; }
      if (key == '\r' || key == '\n') {
        keyboard.handoff(controls::raw_key((u8)key),millis());
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
#if !defined(PICO_ON_DEVICE)
void Services::test_native_contract(void (*test)(void*,const mk61_app_api&,const mk61_app_services&),void* context,bool native) {
  if(NativeHost::current || !test) return;
  NativeHost host(*this,native);test(context,NativeHost::api,NativeHost::common);
}
#endif
NativeHost *NativeHost::current = nullptr;
Services::NativeBufferStatistics Services::native_buffer_statistics() const {
  if(!NativeHost::current) return {};
  const auto s=NativeHost::current->buffers.statistics();
  return {s.count,s.bytes,s.external_bytes,s.windows};
}
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
  host.display.settings(host.settings());
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
           MK61_SERVICE_CAP_EXPLORER | MK61_SERVICE_CAP_BASIC_GRAPHICS | MK61_SERVICE_CAP_BUFFERS |
           (shared_memory::buffer_statistics().external_capacity?MK61_SERVICE_CAP_EXTERNAL_BUFFERS:0) |
           MK61_SERVICE_CAP_APP_FLOW
#if defined(PICO_ON_DEVICE)
           | MK61_SERVICE_CAP_RUNTIME
#endif
        ;
  case MK61_SERVICE_UI_FONT:
    // A legacy APP's 192x64 Surface keeps the old retro strike and metrics.
    // Its glyph service must describe that same surface, even though the
    // panel's native family 4 now uses Ark Mono.
    if(host.display.width()==192 &&
       ((a==MK61_UI_FONT_INFO && host.settings().ui_font_family==4) ||
        (a==MK61_UI_FONT_GLYPH && payload && c==sizeof(mk61_service_ui_glyph) &&
         ((mk61_service_ui_glyph*)payload)->family==4)))
      return ui_font_service::call(4,16,a,b,c,payload);
    return fonts::service(host.settings(), a, b, c, payload);
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
    return host.resource(a, b, payload);
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
      if(s.graph_width_==320) script::show_native_frame(s.graph_.frame());else script::show_frame(s.graph_.frame());
      s.runtime_graphics_ = false;
    }
    if (control && (r.operation == basic_graphics::Operation::WIDTH ||
                    r.operation == basic_graphics::Operation::HEIGHT ||
                    r.operation == basic_graphics::Operation::ACTIVE))
      return result == basic_graphics::Result::OK ? (u32)r.value : 0;
    return (u32)result + 1;
  }
  case MK61_SERVICE_DISPLAY:
    return host.display.call(a,b,c,payload);
  case MK61_SERVICE_KEYBOARD:
    switch(a) {
    case MK61_SERVICE_KEY_SCAN:host.pump();return 1;
    case MK61_SERVICE_KEY_ANY:host.pump();return controls::any_pressed(millis());
    case MK61_SERVICE_KEY_POLL:return (u32)host.raw_key(-1,false);
    case MK61_SERVICE_KEY_GET:
      if(b!=0 && b!=keyboard_core::RELEASE_MASK && b!=UINT32_MAX) return UINT32_MAX;
      return (u32)host.raw_key(b==UINT32_MAX?-1:(int)b,false);
    case MK61_SERVICE_KEY_WAIT: {
      const int key=host.raw_key(0,true);host.keyboard.handoff(key,millis());return (u32)key;
    }
    case MK61_SERVICE_KEY_PRESSED:host.pump();return controls::raw_pressed((i32)b,millis());
    case MK61_SERVICE_KEY_IMMEDIATE:host.pump();return host.keyboard.immediate((i32)b);
    case MK61_SERVICE_KEY_CLEAR_IMMEDIATE:host.keyboard.clear_immediate();return 1;
    case MK61_SERVICE_KEY_CLEAR_HOLD:return 1; // BIOS supplies edge events; no resident repeat counter.
    case MK61_SERVICE_KEY_HANDOFF:host.keyboard.handoff((i32)b,millis());return 1;
    case MK61_SERVICE_KEY_HANDOFF_PENDING:host.pump();return host.keyboard.pending(millis());
    case MK61_SERVICE_KEY_LAST:return (u32)host.keyboard.last();
    default:return 0;
    }
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
      write(0, row, lines[row],
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
        write(0, row, i == selected ? ">" : " ", 1);
        if (items[i].text)
          write(1, row, items[i].text,
                             (unsigned)strnlen(items[i].text, columns() - 1));
      }
      const int key = host.take(true);
      if (key == 0x1B || key == 0xB1) { host.keyboard.handoff(controls::raw_key((u8)key),millis());return 1; }
      if ((key == 0xB4 || key == 0xB5) && selected)
        --selected;
      if ((key == 0xB7 || key == 0xB6) && selected + 1 < a)
        ++selected;
      if (key == '\r' || key == '\n') {
        host.keyboard.handoff(controls::raw_key((u8)key),millis());
        if(!items[selected].action || items[selected].action()) return 1;
      }
    }
  }
  case MK61_SERVICE_BUFFER: {
    if(!payload || b || c!=sizeof(mk61_service_buffer)) return 0;
    auto& request=*(mk61_service_buffer*)payload;
    if(a!=MK61_BUFFER_PRESENT) return host.buffers.call(a,request);
    const u32 bytes=host.display.width()*host.display.height()/8;
    if(!host.graphics || request.size!=bytes) return 0;
    auto info=request;
    if(!host.buffers.call(MK61_BUFFER_INFO,info) || request.offset>info.size || bytes>info.size-request.offset) return 0;
    mk61_service_framebuffer frame{};
    if(!host.display.call(MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame) || frame.bytes!=bytes) return 0;
    // Fill the existing borrowed frame without pumping the UI mid-copy.
    // A backend failure publishes a blank frame rather than partial data.
    for(u32 at=0;at<bytes;) {
      auto part=request;part.offset+=at;part.size=bytes-at<1024?bytes-at:1024;part.data=frame.pixels+at;
      if(!host.buffers.call(MK61_BUFFER_READ,part)) {
        std::memset(frame.pixels,0,bytes);host.display.bitmap_present(frame.pixels,bytes);return 0;
      }
      at+=part.size;
    }
    return host.display.bitmap_present(frame.pixels,bytes);
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
    if(!p.significant_digits || p.significant_digits>14) return 0;
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
    if (!payload || a>MK61_DOUBLE_FROM_FLOAT)
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
    if (!payload || a>1 || (!a && b>=0xFFFF))
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
    if (program_store::text_content((program_store::ProgramType)c)
            ? !files::write_text(path,(const char*)p.data,p.size)
            : !files::write(path, p.data, p.size))
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
    if(!payload) return 0;
    auto& e=*(mk61_service_editor*)payload;
    if(!e.source || e.length>65534 || e.cursor>e.length || e.top>65535 ||
       !mk8::text_valid((const u8*)e.source,e.length)) return 0;
    host.display.call(MK61_SERVICE_DISPLAY_END_UI_TEXT,0,0,nullptr);
    const unsigned visible=rows(),cols=columns();
    u16 top=text_editor::line_start_for_cursor(e.source,(u16)(e.top<e.length?e.top:e.length));
    const u16 active=text_editor::line_start_for_cursor(e.source,(u16)e.cursor);
    if(active<top) top=active;
    u16 at=top;unsigned row=0;
    while(at<active && row<visible) { at=text_editor::next_line_start(e.source,at,(u16)e.length);++row; }
    if(row>=visible) {
      top=active;for(unsigned i=1;i<visible && top;++i) top=text_editor::previous_line_start(e.source,top);
    }
    e.top=top;
    if(op==MK61_SERVICE_EDITOR_DRAW) {
      clear();at=top;
      const unsigned column=e.cursor-active;
      const unsigned window=column>cols-2?column-(cols-2):0;
      for(row=0;row<visible;++row) {
        const bool current=at==active;
        host.display.call(MK61_SERVICE_DISPLAY_CURSOR,0,row,nullptr);
        host.display.call(MK61_SERVICE_DISPLAY_WRITE,current?'>':' ',0,nullptr);
        const u16 end=text_editor::line_end_for_start(e.source,at,(u16)e.length);
        unsigned pos=at+(current?window:0);
        for(unsigned col=1;col<cols && pos<end;++col,++pos)
          host.display.call(MK61_SERVICE_DISPLAY_WRITE,(u8)e.source[pos],0,nullptr);
        if(at==e.length) break;
        at=text_editor::next_line_start(e.source,at,(u16)e.length);
      }
      at=top;row=0;while(at<active && row+1<visible) { at=text_editor::next_line_start(e.source,at,(u16)e.length);++row; }
      host.display.call(MK61_SERVICE_DISPLAY_CURSOR,1+column-window,row,nullptr);
      host.display.call(MK61_SERVICE_DISPLAY_CURSOR_ON,0,0,nullptr);
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
    char literal[2]{};
    if(e.key>=MK61_APP_KEY_RAW_BASE+32 && e.key<MK61_APP_KEY_RAW_BASE+256 &&
       e.key!=MK61_APP_KEY_RAW_BASE+127) literal[0]=(char)(e.key-MK61_APP_KEY_RAW_BASE);
    return loadable_module::system_editor::handle(e,literal[0]?literal:nullptr);
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

u32 NativeHost::resource(u32 op, u32 inode, void *payload) {
  const u32 revision = files::revision();
  if (op == 0 || op == 4)
    return revision;
  if(op==6 && payload) {
    const char* path=inode<0xFFFF ? script::file_path((u16)inode) : nullptr;
    return path && files::content_stamp(path,*(u32*)payload);
  }
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
  if (!r.output || r.reserved > (op == 5 ? 2U : 0U))
    return 0;
  const auto current=[&]() {
    if(r.reserved!=2) return r.revision==files::revision();
    u32 stamp=0;const char* path=script::file_path(r.id);
    return path && files::content_stamp(path,stamp) && stamp==r.revision;
  };
  return current() && file_read(r.id, r.offset, r.output, r.length) == r.length && current();
}
u32 NativeHost::setup(u32 op, u32 a, u32 b, void *payload) {
  auto settings = this->settings();
  const auto save = [&]() { return s.ui_ && s.ui_->apply_settings(settings); };
  switch (op) {
  case MK61_SETUP_VERSION:
    return MK61_SETUP_API_VERSION;
  case MK61_SETUP_FEATURES:
    return MK61_SETUP_FEATURE_UI_TEXT_MODE | MK61_SETUP_FEATURE_TEXT_PROFILE |
           MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE |
           MK61_SETUP_FEATURE_UI_FONT | MK61_SETUP_FEATURE_UI_FONT_CATALOG |
           MK61_SETUP_FEATURE_CLASSIC_UI_FONT | MK61_SETUP_FEATURE_COMPACT_UI_FONT |
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
    if (p.role > MK61_PREPARED_FONT_UI || p.reserved ||
        (p.flags & ~(MK61_PREPARED_FONT_PERSIST | MK61_PREPARED_FONT_SELECT_UI)) ||
        (p.role == MK61_PREPARED_FONT_TEXT && (p.flags & MK61_PREPARED_FONT_SELECT_UI)))
      return (u32)MK61_TEXT_FONT_INVALID;
    prepared_font::Face font;
    if (!font.open(p.data, p.size) ||
        (p.expected_height && p.expected_height != font.metrics().height))
      return (u32)MK61_TEXT_FONT_INVALID;
    if(p.role==MK61_PREPARED_FONT_UI) {
      program_store::Entry source{};
      if(p.source_id>=0xFFFF || !program_store::entry_by_id((u16)p.source_id,source) ||
         source.type!=program_store::ProgramType::FONT) return (u32)MK61_TEXT_FONT_INVALID;
      u32 choice=p.ui_key;
      if(p.flags & MK61_PREPARED_FONT_SELECT_UI) {
        fonts::Item item{};
        if(!fonts::describe(choice,item) || item.family!=3 || item.size!=font.metrics().height)
          return (u32)MK61_TEXT_FONT_INVALID;
        mk61_setup_ui_font_source selected{};
        if(!setup(MK61_SETUP_UI_FONT_SOURCE,choice,0,&selected) || selected.id!=p.source_id)
          return (u32)MK61_TEXT_FONT_INVALID;
      } else if(!choice) choice=fonts::key(settings);
      if(!fonts::install(p.data,p.size,choice,p.expected_height)) return (u32)MK61_TEXT_FONT_INVALID;
      if(p.flags & MK61_PREPARED_FONT_SELECT_UI) {
        settings.ui_font_family=3;settings.ui_font_key=choice;settings.ui_font_size=font.metrics().height;
        if(!s.ui_ || !s.ui_->apply_settings(settings,(p.flags & MK61_PREPARED_FONT_PERSIST)!=0))
          return (u32)MK61_TEXT_FONT_UNAVAILABLE;
      }
      return (u32)MK61_TEXT_FONT_OK;
    }
    if(!script::install_prepared(p.data,p.size)) return (u32)MK61_TEXT_FONT_UNAVAILABLE;
    if(p.flags & MK61_PREPARED_FONT_PERSIST) {
      const auto profile=script::text_profile();
      settings.text_rows=profile.rows;settings.text_width=profile.width;
      settings.text_height=profile.height;settings.text_gap=profile.line_gap;
      if(!save()) return (u32)MK61_TEXT_FONT_UNAVAILABLE;
    }
    return (u32)MK61_TEXT_FONT_OK;
  }
  case MK61_SETUP_FONT_RESTORE:
    return script::text_profile({settings.text_rows, settings.text_width,
                                 settings.text_height, settings.text_gap});
  case MK61_SETUP_UI_FONT_READ:
    if (!payload) return 0;
    *(mk61_setup_ui_font *)payload = {settings.ui_font_family, settings.ui_font_size};
    return 1;
  case MK61_SETUP_UI_FONT_APPLY: {
    if (!payload) return 0;
    const auto &p = *(const mk61_setup_ui_font *)payload;
    settings.ui_font_family=p.family==2?1:p.family;
    settings.ui_font_size=p.size;
    if(settings.ui_font_family!=3) settings.ui_font_key=0;
    return save();
  }
  case MK61_SETUP_UI_FONT_COUNT:
    return fonts::count();
  case MK61_SETUP_UI_FONT_CURRENT:
    return fonts::key(settings);
  case MK61_SETUP_UI_FONT_ITEM:
  case MK61_SETUP_UI_FONT_STEP: {
    if(!payload) return 0;
    fonts::Item item{};
    if(op==MK61_SETUP_UI_FONT_ITEM ? !fonts::item(a,item) :
        !fonts::step(a,(i32)b,item)) return 0;
    auto& out=*(mk61_setup_ui_font_item*)payload;
    out={};out.key=item.key;out.size=item.size;
    std::snprintf(out.name,sizeof(out.name),"%.31s",item.name);
    return 1;
  }
  case MK61_SETUP_UI_FONT_APPLY_ITEM: {
    fonts::Item item{};
    if(!fonts::describe(a,item)) return 0;
    settings.ui_font_family=item.family;settings.ui_font_size=item.size;
    settings.ui_font_key=item.family==3?item.key:0;
    return save();
  }
  case MK61_SETUP_UI_FONT_SOURCE: {
    if(!payload) return 0;
    fonts::Item item{};
    if(!fonts::describe(a,item) || item.family!=3) return 0;
    // Resolve by stable key, retaining the real UTF-8 filename.
    for(unsigned skip=0;;++skip) {
      files::Entry entry{};unsigned used=0;bool more=false;
      if(!files::list("/Fonts",skip,&entry,1,used,more) || !used) return 0;
      if(!entry.directory && ui_font_catalog::name_key(entry.name)==a) {
        char path[files::PATH_SIZE];
        std::snprintf(path,sizeof(path),"/Fonts/%s",entry.name);
        program_store::Entry source{};
        if(!script::register_file(path,source)) return 0;
        auto& out=*(mk61_setup_ui_font_source*)payload;
        out={};out.id=source.id;out.size=item.size;return 1;
      }
    }
  }
  case MK61_SETUP_CALCULATOR_FONT_READ:
    return settings.calculator_font;
  case MK61_SETUP_CALCULATOR_FONT_APPLY:
    if (a > 1)
      return 0;
    settings.calculator_font = (u8)a;
    return save();
  case MK61_SETUP_TEXT_MODE:
    return a>1?0:display.call(a?MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT:MK61_SERVICE_DISPLAY_END_UI_TEXT,0,0,nullptr);
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
  release_cache();
  (void)source_.park();
  if(!path || !*path) return 4;
  shown_frame_revision_=0; // A native APP may draw directly into the shared canvas.
  language_cache::discard();
  char application[files::PATH_SIZE],document[files::PATH_SIZE];
  if(!m61_text::active()) {
    std::snprintf(application,sizeof(application),"%s",path);
    if(file!=0xFFFF) {
      const char* name=script::file_path(file);if(!name) return 4;
      std::snprintf(document,sizeof(document),"%s",name);
    }
    script::reset_files();path=application;
    if(file!=0xFFFF) {
      program_store::Entry entry;
      if(!script::register_file(document,entry)) return 4;
      file=entry.id;
    }
  }
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
  diagnostics::Scope measure(diagnostics::Point::APP);
  diagnostics::context(diagnostics::State::APP,file);
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
  // A completed BASIC drawing no longer owns the foreground. Release its
  // native frame before reserving an APP image (SHEET needs almost 30 KiB).
  graph_.reset();graph_visible_=false;
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
    NativeHost host(*this,(header.flags&MK61_APP_NATIVE_320_FLAG)!=0);
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
