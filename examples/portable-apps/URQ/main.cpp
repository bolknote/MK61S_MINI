#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize("Oz")
#endif
#include "mk61_app.h"
#include "mk8_literal.hpp"
#include "phone_input.hpp"
#include "urq/engine.hpp"
#include <string.h>
#include <new>
#if !defined(MK61_TARGET_PICOCALC)
#include "classic_view.hpp"
#endif
#if defined(MK61_TARGET_PICOCALC)
#include "color.hpp"
#endif
#if !defined(MK61_TARGET_PICOCALC)
#define MK61_URQ_SPLIT 1
#endif

namespace {
constexpr auto full_line = M8_ARRAY("Строка заполнена");
struct History {
#if defined(MK61_TARGET_PICOCALC)
  static constexpr unsigned STRIDE = 3;
  uint16_t colors[512]{};
  uint16_t current_color = 0xFFFF;
#else
  static constexpr unsigned STRIDE = 1;
#endif
  const mk61_app_services* services = nullptr;
  mk61_service_buffer external{};
  char local[512]{};
  uint8_t cache[128 * STRIDE]{};
  uint32_t begin = 0, end = 0, cached = UINT32_MAX, cached_size = 0;
  void init(const mk61_app_services* s) {
    services = s; external = {}; begin = end = 0; cached = UINT32_MAX;
#if defined(MK61_TARGET_PICOCALC)
    current_color = 0xFFFF;
    const auto caps = s->call(MK61_SERVICE_CAPABILITIES, 0, 0, 0, nullptr);
    if(caps & MK61_SERVICE_CAP_EXTERNAL_BUFFERS)
      mk61_app_buffer_acquire(s, 256 * 1024, MK61_BUFFER_EXTERNAL, &external);
#endif
  }
  void close() {
    if(external.handle) mk61_app_buffer_release(services, external.handle);
    external = {};
  }
  void fallback() {
    close();cached = UINT32_MAX;
    if(end - begin > sizeof(local)) begin = end - sizeof(local);
  }
  uint32_t capacity() const { return external.handle ? external.size / STRIDE : sizeof(local); }
  bool append(const char* text, unsigned n) {
    while(n) {
      const uint32_t capacity_bytes = capacity();
      const uint32_t offset = end % capacity_bytes;
      unsigned count = n < capacity_bytes - offset ? n : capacity_bytes - offset;
      if(external.handle) {
#if defined(MK61_TARGET_PICOCALC)
        uint8_t bytes[64 * STRIDE];if(count > 64) count = 64;
        for(unsigned i = 0; i < count; ++i) {
          bytes[i*STRIDE] = uint8_t(text[i]);bytes[i*STRIDE+1] = uint8_t(current_color);bytes[i*STRIDE+2] = uint8_t(current_color>>8);
        }
        if(!mk61_app_buffer_write(services, external.handle, offset * STRIDE, bytes, count * STRIDE)) fallback();
#else
        if(!mk61_app_buffer_write(services, external.handle, offset, text, count)) fallback();
#endif
      }
      // A small SRAM tail makes loss of the optional history cache harmless.
      for(unsigned i = 0; i < count; ++i) {
        const unsigned index = (end+i)%sizeof(local);local[index] = text[i];
#if defined(MK61_TARGET_PICOCALC)
        colors[index] = current_color;
#endif
      }
      end += count; text += count; n -= count;
      if(end - begin > capacity()) begin = end - capacity();
    }
    cached = UINT32_MAX; return true;
  }
  bool get(uint32_t at, char& out, uint16_t* color = nullptr) {
    if(at < begin || at >= end) return false;
    if(!external.handle) {
      out = local[at % sizeof(local)];
#if defined(MK61_TARGET_PICOCALC)
      if(color) *color = colors[at % sizeof(local)];
#else
      (void)color;
#endif
      return true;
    }
    if(cached == UINT32_MAX || at < cached || at - cached >= cached_size) {
      const uint32_t offset = at % capacity();
      cached_size = end - at < sizeof(cache) / STRIDE ? end - at : sizeof(cache) / STRIDE;
      if(cached_size > capacity() - offset) cached_size = capacity() - offset;
      if(!mk61_app_buffer_read(services, external.handle, offset * STRIDE, cache, cached_size * STRIDE)) {
        fallback();return get(at,out,color);
      }
      cached = at;
    }
    const uint32_t index = (at - cached) * STRIDE;
    out = char(cache[index]);
#if defined(MK61_TARGET_PICOCALC)
    if(color) *color = uint16_t(cache[index+1] | uint16_t(cache[index+2])<<8);
#endif
    return true;
  }
};
enum class Screen : uint8_t { GAME, MENU, SAVE, LOAD, INVENTORY, CONFIRM };
enum class Request : uint8_t { NONE, MENU, SAVE, CONTENT, URL, INIT, INPUT };
struct App {
  const mk61_app_services* services = nullptr;
  urq::Engine engine;
  urq::Pack pack;
  mk61_service_lease lease{};
  mk61_service_lease shell_lease{};
  History history;
  uint32_t file = MK61_SERVICE_INVALID_ID, parent = MK61_SERVICE_ROOT_ID;
  uint32_t view = 0, scene = 0, next = 0, last_ms = 0;
  uint16_t part = 0xFFFF, part_id = 0xFFFF, selected = 0, menu = 0, action_next = 0;
  uint16_t length = 0, cursor = 0;
  char draft[256]{};
  char* input = nullptr; // draft lives in the shell across menus and cold APP swaps
  phone_input::State phone{};
  bool dirty = true, quitting = false, russian = true, typing = false, paging = false;
  bool actions = false;
#if !defined(MK61_TARGET_PICOCALC)
  bool compact = false;
  uint8_t* bitmap = nullptr;
#endif
  char notice[32]{};
  Request request = Request::NONE;
#if defined(MK61_TARGET_PICOCALC)
  uint16_t background = 0, foreground = 0xFFFF;
  bool colored = false;
#endif
  unsigned rows = 4, width = 20, body = 1;
};
#if defined(MK61_TARGET_PICOCALC)
static_assert(sizeof(App) <= 3072, "URQ native shell SRAM budget");
#else
static_assert(sizeof(App) <= 1600, "URQ shell must fit the shared SCRATCH arena");
#endif
App* app_state;
#define app (*app_state)
void notice(const char* text) { urq::copy_string(app.notice, text); }

uint32_t display(uint32_t operation, uint32_t b = 0, uint32_t c = 0, void* p = nullptr) {
  return app.services->call(MK61_SERVICE_DISPLAY, operation, b, c, p);
}
void line(unsigned row, const char* text, char marker = 0, uint32_t color = 0x10000,
          const uint16_t* colors = nullptr, unsigned count = 0) {
#if !defined(MK61_TARGET_PICOCALC)
  if(app.bitmap) {
    classic_view::Canvas canvas{app.services,app.bitmap};
    if(row==app.rows-1) canvas.hint(text);
    else {
      const unsigned y=row*classic_view::PITCH;const bool selected=marker=='>' && !app.typing;
      if(marker=='>') canvas.box(1,y,190,14,selected);
      canvas.text(marker?9:3,y+1,text,selected);
    }
    return;
  }
#endif
#if defined(MK61_TARGET_PICOCALC)
  if(app.colored) display(MK61_SERVICE_DISPLAY_UI_COLORS,
      color < 0x10000 ? color : ((app.background & 0x7E0) > 0x3E0 ? 0 : 0xFFFF), app.background);
#else
  (void)color; (void)colors; (void)count;
#endif
  display(MK61_SERVICE_DISPLAY_UI_LINE, row, uint8_t(marker), (void*)text);
#if defined(MK61_TARGET_PICOCALC)
  if(app.colored && colors) display(MK61_SERVICE_DISPLAY_UI_RUN_COLORS, row, count, (void*)colors);
#endif
}
void geometry() {
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact) {
    app.rows=5;app.width=186;app.body=app.engine.state().status==urq::Status::INPUT?3:4;return;
  }
#endif
  display(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT);
  app.rows = mk61_api->display_rows(); if(app.rows < 2) app.rows = 2;
  app.width = display(MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH);
  if(!app.width) app.width = mk61_api->display_columns();
  app.body = app.rows > 8 ? app.rows - 6 : app.rows > 3 ? app.rows - 2 : 1;
  if(app.body > 12) app.body = 12;
  if(!app.history.external.handle && app.body > 7) app.body = 7;
}
unsigned advance(char ch) {
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact) return classic_view::Canvas{app.services,nullptr}.advance(uint8_t(ch));
#endif
  char text[2] = {ch, 0};
  const uint32_t size = display(MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT, 0, 0, text);
  return size ? size : 1;
}
uint32_t wrap(uint32_t at, char* out, unsigned limit) {
  unsigned used = 0, pixels = 0, last_space = 0;
  char ch;
  const unsigned columns = 126;
  while(app.history.get(at + used, ch) && ch != '\n' && ch != '\r' && used < 126 && used < columns) {
    const unsigned size = advance(ch);
    if(used && pixels + size > limit) break;
    if(ch == ' ') last_space = used;
    out[used++] = ch; pixels += size;
  }
  char next = 0;
  const bool available = app.history.get(at + used, next);
  if(available && next != '\n' && next != '\r' && next != ' ' && last_space) used = last_space;
  if(!used && available && next != '\n' && next != '\r') { out[used++] = next; }
  unsigned take = used; while(take && out[take - 1] == ' ') --take;
  out[take] = 0; at += used;
  while(app.history.get(at, ch) && (ch == ' ' || ch == '\r')) ++at;
  if(app.history.get(at, ch) && ch == '\n') ++at;
  return at;
}
uint32_t page(uint32_t at, bool draw) {
  if(at < app.history.begin) at = app.history.begin;
  for(unsigned row = 0; row < app.body; ++row) {
    char buffer[128]; const uint32_t next = wrap(at, buffer, app.width);
    uint16_t color = 0xFFFF;
#if defined(MK61_TARGET_PICOCALC)
    char unused;app.history.get(at, unused, &color);uint16_t colors[64];unsigned count = strlen(buffer);
    if(count > 64) count = 64;
    for(unsigned i=0;i<count;++i) { colors[i]=color;app.history.get(at+i,unused,&colors[i]); }
    if(draw) line(row, buffer, 0, color, colors, count);
#else
    if(draw) line(row, buffer, 0, color);
#endif
    if(next == at) break;
    at = next;
  }
  return at;
}
unsigned action_indices(uint16_t* indices) {
  unsigned count = 0;
  for(unsigned i = 0; i < app.engine.state().action_count; ++i)
    if(app.engine.state().actions[i].live) indices[count++] = uint16_t(i);
  return count;
}
void end_typing() {
  if(!app.typing) return;
#if defined(MK61_TARGET_PICOCALC)
  app.services->call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_END, 0, 0, nullptr);
#endif
  app.typing = false;
}
[[maybe_unused]] void begin_typing(bool reset) {
  if(reset) { app.length = app.cursor = 0; app.input[0] = 0; phone_input::finish(app.phone); }
  if(!app.length) app.input[0] = 0;
#if defined(MK61_TARGET_PICOCALC)
  mk61_service_text_event event{}; event.layout = app.russian ? 1 : 0;
  if(!app.services->call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_BEGIN, 0, sizeof(event), &event)) {
    notice(M8("Нужна новая прошивка")); return;
  }
#endif
  app.typing = true;
}
void draw_game() {
  geometry();
#if !defined(MK61_TARGET_PICOCALC)
  uint8_t pixels[classic_view::BYTES]{};
  if(app.compact) { mk61_api->graphics_begin();app.bitmap=pixels; }
  else
#endif
  display(MK61_SERVICE_DISPLAY_BEGIN_UPDATE);
#if defined(MK61_TARGET_PICOCALC)
  app.background = urq_color::parse(app.engine.get("style_backcolor"), 0);
  app.foreground = urq_color::parse(app.engine.get("style_textcolor"), 0xFFFF);
  if(app.colored) display(MK61_SERVICE_DISPLAY_UI_COLORS, (app.background & 0x7E0) > 0x3E0 ? 0 : 0xFFFF, app.background);
#endif
#if !defined(MK61_TARGET_PICOCALC)
  if(!app.compact)
#endif
  display(MK61_SERVICE_DISPLAY_CLEAR);
  const auto status = app.engine.state().status;
  app.next = page(app.view, true);
  const unsigned first = app.body;
  if(status == urq::Status::INPUT && !app.paging) {
    char visible[128]; unsigned start = app.cursor, pixels = advance('|');
    while(start && pixels + advance(app.input[start - 1]) < app.width - advance('>')) {
      pixels += advance(app.input[--start]);
    }
    unsigned n = 0;
    for(unsigned i = start; i <= app.length && n < sizeof(visible) - 2; ++i) {
      if(i == app.cursor) visible[n++] = '|';
      if(i < app.length) visible[n++] = app.input[i];
    }
    visible[n] = 0; line(first, visible, '>');
  } else if(!app.paging) {
    uint16_t indices[urq::ACTIONS]; const unsigned count = action_indices(indices);
    if(app.selected >= count) app.selected = count ? uint16_t(count - 1) : 0;
#if !defined(MK61_TARGET_PICOCALC)
    if(app.compact && app.actions && count) {
      memset(pixels,0,sizeof(pixels));
      classic_view::Canvas canvas{app.services,pixels};unsigned index=app.selected,offset=app.menu;
      app.action_next=0;
      for(unsigned row=0;row<4 && index<count;++row) {
        const char* caption=app.engine.text(app.engine.state().actions[indices[index]].caption);
        char text[128],numbered[128];
        const unsigned next=canvas.wrap(caption,offset,text,160);
        if(offset && row) urq::copy_string(numbered,text);
        else mk61_app_snprintf(app.services,numbered,sizeof(numbered),"%u %s",index+1,text);
        line(row,numbered,index==app.selected?'>':' ');
        if(caption[next]) {offset=next;if(index==app.selected) app.action_next=uint16_t(next);}
        else {if(index==app.selected) app.action_next=0;++index;offset=0;}
      }
    } else if(!app.compact)
#endif
    {
    const unsigned available = app.rows > first + 1 ? app.rows - first - 1 : 1;
    const unsigned top = app.selected >= available ? app.selected - available + 1 : 0;
    for(unsigned row = 0; row < available && top + row < count; ++row) {
      const auto& a = app.engine.state().actions[indices[top + row]];
      char caption[128];
      mk61_app_snprintf(app.services, caption, sizeof(caption), "%u %s", top + row + 1,
                        app.engine.text(a.caption));
      line(first + row, caption, top + row == app.selected ? '>' : ' ');
    }
    }
  }
  const char* footer = *app.notice ? app.notice : app.paging ? M8("Далее:OK") :
      status == urq::Status::ANYKEY ? M8("Любая клавиша") :
      status == urq::Status::PAUSE ? M8("Пауза") : "OK / USER";
#if defined(MK61_TARGET_PICOCALC)
  if(status==urq::Status::INPUT && !app.paging && !*app.notice)
    footer=app.russian?M8("RU Enter:ввод Tab:меню F8:язык"):M8("EN Enter:ввод Tab:меню F8:язык");
#endif
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact && !*app.notice) {
    footer=app.paging?M8("OK/→:далее ESC:выход"):
        app.actions?M8("←→:пункт OK:выбор USER:меню"):
        status==urq::Status::CHOICE?M8("OK:действия ←→:текст USER:меню"):
        status==urq::Status::INPUT?M8("OK:ввод K:язык F:аА USER"):footer;
    if(status==urq::Status::INPUT && !app.paging) {
      static const char* const layouts[]={M8("РУС"),"ABC","123"};
      char hint[48];mk61_app_snprintf(app.services,hint,sizeof(hint),"%s %s",layouts[app.phone.layout],footer);
      line(app.rows-1,hint);footer=nullptr;
    }
  }
#endif
  if(app.rows > 3 && footer) line(app.rows - 1, footer);
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact) { mk61_api->graphics_present(pixels,sizeof(pixels));app.bitmap=nullptr; }
  else
#endif
  display(MK61_SERVICE_DISPLAY_END_UPDATE);
  app.dirty = false;
}
bool up(int key) { return key == MK61_APP_KEY_SHIFT_LEFT || key == MK61_APP_KEY_BACKWARD; }
bool down(int key) { return key == MK61_APP_KEY_SHIFT_RIGHT || key == MK61_APP_KEY_FORWARD; }
bool screen_changed(uint32_t& previous) {
  const uint32_t current=mk61_api->graphics_revision?mk61_api->graphics_revision():0;
  const bool changed=current!=previous;previous=current;return changed;
}
int wait_reading_key() {
  uint32_t revision=UINT32_MAX;
  for(;;) {
    if(screen_changed(revision)) draw_game();
    const int key=mk61_api->key_poll();if(key>=0) return key;
    mk61_api->delay_ms(1);
  }
}
void print(void*, const char* text, bool newline) {
#if defined(MK61_TARGET_PICOCALC)
  app.history.current_color = urq_color::parse(app.engine.get("style_textcolor"), 0xFFFF);
#endif
  while(*text && !app.quitting) {
    unsigned n = 0; while(text[n] && n < 64) ++n;
    if(!app.history.append(text, n)) { app.engine.fail(urq::Error::IO); return; }
    text += n; geometry();
    while(page(app.view, false) < app.history.end && !app.quitting) {
      app.paging = true; draw_game();
      int key = wait_reading_key();
      if(key == MK61_APP_KEY_ESC || key == MK61_APP_KEY_USER) {
        notice(M8("OK:читать ESC:выйти"));draw_game();
        key = wait_reading_key();
        app.notice[0]=0;
        if(key == MK61_APP_KEY_ESC) { app.quitting = true; break; }
      }
      if(key == MK61_APP_KEY_OK || down(key) || key == MK61_APP_KEY_RIGHT)
        app.view = app.next;
    }
  }
  if(newline && !app.quitting) app.history.append("\n", 1);
  app.paging = false; app.dirty = true;
}
void clear(void*, bool text, bool) {
  if(text) {
    app.history.append("\n", 1); app.view = app.scene = app.history.end;
    app.selected = app.menu = 0;app.actions=false;
  }
  app.dirty = true;
}
uint32_t file_id(uint16_t part) {
  if(!part) return app.file;
  if(part == app.part) return app.part_id;
  char name[16]; mk61_app_snprintf(app.services, name, sizeof(name), "p%04u.uqd", part - 1);
  mk61_service_file file{};
  const uint32_t result = app.services->call(MK61_SERVICE_FILE_RESOLVE, app.parent,
      MK61_SERVICE_FILE_URQ_DATA, uint32_t(uintptr_t(name)), &file);
  if(result != 0) return MK61_SERVICE_INVALID_ID;
  app.part = part; app.part_id = uint16_t(file.id); return file.id;
}
bool read(void*, uint16_t part, uint32_t offset, uint8_t* out, uint32_t n) {
  const uint32_t id = file_id(part);
  return id != MK61_SERVICE_INVALID_ID && mk61_api->file_read(id, offset, out, n) == n;
}
uint32_t size(void*, uint16_t part) {
  const uint32_t id = file_id(part);
  return id == MK61_SERVICE_INVALID_ID ? 0 : mk61_api->file_size(id);
}
void number(void*, double value, bool fixed, char* out, uint16_t capacity) {
  mk61_service_number_format request{value, out, capacity, 2};
  if(!app.services->call(MK61_SERVICE_NUMBER_FORMAT, fixed?MK61_NUMBER_ECMA_FRACTIONAL:MK61_NUMBER_ECMA_GENERAL,
                         0, 0, &request) && capacity) out[0] = 0;
}
uint32_t clock(void*, bool days) {
  return app.services->call(MK61_SERVICE_SETUP,MK61_SETUP_RTC_VALUE,days?1:0,0,nullptr);
}
bool parse(void*, const char* text, double& value) {
  mk61_service_number_parse request{0, text, 0};
  if(!app.services->call(MK61_SERVICE_NUMBER_PARSE, 1, 0, 0, &request)) return false;
  const char* end = text + request.consumed;
  while(*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n') ++end;
  value = request.value; return !*end;
}
#if !defined(MK61_URQ_SPLIT) || defined(MK61_URQ_COLD)
struct Range {
  uint32_t offset, size, at, copied;
  uint8_t* out;
  uint32_t crc = 0;
};
bool emit(void* raw, const uint8_t* bytes, uint32_t n) {
  auto& r = *(Range*)raw;
  if(r.out && r.at < r.offset + r.size && r.at + n > r.offset) {
    const uint32_t start = r.offset > r.at ? r.offset - r.at : 0;
    const uint32_t end = r.offset + r.size < r.at + n ? r.offset + r.size - r.at : n;
    memcpy(r.out + r.at + start - r.offset, bytes + start, end - start); r.copied += end - start;
  }
  r.crc = urq::crc32(bytes, n, r.crc);r.at += n; return true;
}
bool save_payload(urq::Sink sink) {
  if(app.length >= sizeof(app.draft) || app.cursor > app.length) return false;
  Range size{};if(!app.engine.snapshot({&size, emit})) return false;
  uint8_t header[16]{};urq::put16(header, 1);urq::put16(header+2,app.length);urq::put16(header+4,app.cursor);
#if defined(MK61_TARGET_PICOCALC)
  const unsigned colors = app.colored ? app.engine.state().context_size : 0;
  const unsigned layout = app.russian ? 0 : 1;
#else
  const unsigned colors = 0, layout = app.phone.layout;
#endif
  urq::put16(header+6,uint16_t(colors));urq::put32(header+8,size.at);
  header[12]=uint8_t((layout==0?1:0)|(app.phone.lowercase?2:0)|(layout<<2));
  if(!sink.write(sink.context,header,sizeof(header)) || !app.engine.snapshot(sink) ||
     !sink.write(sink.context,(const uint8_t*)app.draft,app.length)) return false;
#if defined(MK61_TARGET_PICOCALC)
  for(unsigned i=0;i<colors;++i) {
    uint16_t color;char text;uint8_t wire[2];
    if(!app.history.get(app.history.end-colors+i,text,&color)) return false;
    urq::put16(wire,color);if(!sink.write(sink.context,wire,2)) return false;
  }
#endif
  return true;
}
bool save_image(Range& range) {
  Range payload{};if(!save_payload({&payload,emit})) return false;
  uint8_t header[32]{};memcpy(header,"URQS",4);urq::put16(header+4,4);memcpy(header+8,app.pack.id(),16);
  urq::put32(header+24,payload.at);urq::put32(header+28,payload.crc);
  return emit(&range,header,sizeof(header)) && save_payload({&range,emit});
}
uint32_t slot_id(unsigned slot) {
  char name[16]; mk61_app_snprintf(app.services, name, sizeof(name), "slot%u.urs", slot + 1);
  mk61_service_file file{};
  return app.services->call(MK61_SERVICE_FILE_RESOLVE, app.parent, MK61_SERVICE_FILE_URQ_SAVE,
      uint32_t(uintptr_t(name)), &file) == 0 ? file.id : MK61_SERVICE_INVALID_ID;
}
bool save_slot(unsigned slot) {
  char name[16]; mk61_app_snprintf(app.services, name, sizeof(name), "slot%u", slot + 1);
  Range length{}; if(!save_image(length)) return false;
  mk61_service_write_source request{name, nullptr,
    [](void*, uint32_t offset, uint8_t* out, uint32_t n) -> int {
      Range range{offset, n, 0, 0, out};
      return save_image(range) && range.copied == n;
    }, length.at, MK61_SERVICE_INVALID_ID};
  return app.services->call(MK61_SERVICE_FILE_WRITE_SOURCE, app.parent, slot_id(slot),
                             MK61_SERVICE_FILE_URQ_SAVE, &request) != 0;
}
bool load_slot(unsigned slot) {
  const uint32_t id = slot_id(slot);
  if(id == MK61_SERVICE_INVALID_ID) return false;
  const urq::Source source{(void*)(uintptr_t)id,
    [](void* raw, uint32_t offset, uint8_t* out, uint32_t n) {
      return mk61_api->file_read(uint32_t(uintptr_t(raw)), offset, out, n) == n;
    }, mk61_api->file_size(id)};
  uint8_t header[48], draft[256];
  if(source.size < 80 || source.size > 61440 || !source.read(source.context,0,header,sizeof(header)) ||
     memcmp(header,"URQS",4) || urq::le16(header+4)!=4 || header[6] || header[7] ||
     memcmp(header+8,app.pack.id(),16) || urq::le32(header+24)!=source.size-32 || urq::le16(header+32)!=1 ||
     header[44]&~15U || ((header[44]>>2)&3U)>2 || header[45] || header[46] || header[47]) return false;
  const unsigned length=urq::le16(header+34), cursor=urq::le16(header+36), colors=urq::le16(header+38);
  const uint32_t engine_size=urq::le32(header+40);
  if(length>=sizeof(draft) || cursor>length || colors>=512 || engine_size>source.size-48 ||
     source.size!=48+engine_size+length+colors*2 ||
     !source.read(source.context,48+engine_size,(uint8_t*)draft,length) ||
     !mk8::text_valid((const uint8_t*)draft,length)) return false;
  draft[length]=0;
  uint8_t bytes[128];uint32_t crc=0;
  for(uint32_t at=32;at<source.size;) {
    const uint32_t n=source.size-at<sizeof(bytes)?source.size-at:sizeof(bytes);
    if(!source.read(source.context,at,bytes,n)) return false;
    crc=urq::crc32(bytes,n,crc);at+=n;
  }
  if(crc!=urq::le32(header+28)) return false;
  struct Inner { urq::Source source; } inner{source};
  if(colors) {
    uint8_t count[2];if(!source.read(source.context,48+32+26,count,2) || urq::le16(count)!=colors) return false;
  }
  if(!app.engine.restore({&inner,[](void* raw,uint32_t at,uint8_t* out,uint32_t n) {
      const auto& source=((Inner*)raw)->source;return source.read(source.context,48+at,out,n);
    },engine_size})) return false;
  app.history.begin = app.history.end = 0; app.history.cached = UINT32_MAX;
  app.view = app.scene = 0;app.actions=false;app.menu=0;
  const auto& state = app.engine.state();
#if defined(MK61_TARGET_PICOCALC)
  app.history.current_color = urq_color::parse(app.engine.get("style_textcolor"), 0xFFFF);
#endif
  for(unsigned i=0;i<state.context_size;++i) {
#if defined(MK61_TARGET_PICOCALC)
    if(colors) {
      uint8_t wire[2];if(!source.read(source.context,48+engine_size+length+i*2,wire,2)) return false;
      app.history.current_color=urq::le16(wire);
    }
#endif
    if(!app.history.append(state.context+i,1)) return false;
  }
  memcpy(app.draft,draft,length+1);app.length=uint16_t(length);app.cursor=uint16_t(cursor);
  app.russian=(header[44]&1)!=0;app.phone.layout=uint8_t((header[44]>>2)&3);app.phone.lowercase=(header[44]&2)!=0;
  phone_input::finish(app.phone);
  return true;
}
bool truth(const urq::Value& value) { return value.type == 1 ? value.text && *value.text : value.number != 0; }
unsigned inventory(unsigned selected, char* caption = nullptr, char* command = nullptr) {
  auto& state = app.engine.state(); unsigned count = 0;
  for(unsigned i = 0; i < urq::ITEMS; ++i) if(state.items[i]) {
    if(count++ != selected) continue;
    char quantity[32]; number(nullptr, state.quantities[i], false, quantity, sizeof(quantity));
    mk61_app_snprintf(app.services, caption, 128, "%s (%s)", app.engine.text(state.items[i]), quantity);
    command[0] = 0;
  }
  for(unsigned i = 0; i < app.pack.labels(); ++i) {
    char name[128], key[144]; uint32_t position;
    if(!app.pack.label_at(i, name, sizeof(name), position)) break;
    if(strncmp(name, "use_", 4)) continue;
    bool eligible = !strncmp(name, "use_inv", 7) && (!name[7] || name[7] == '_');
    for(unsigned v = 0; !eligible && v < urq::ITEMS; ++v) if(state.items[v]) {
      const char* item = app.engine.text(state.items[v]); const unsigned n = strlen(item);
      if(strncmp(name + 4, item, n) || (name[4 + n] && name[4 + n] != '_')) continue;
      mk61_app_snprintf(app.services, key, sizeof(key), "hide_use_%s", item);
      eligible = !truth(app.engine.get("hide_use")) && !truth(app.engine.get(key));
    }
    if(!eligible) continue;
    mk61_app_snprintf(app.services, key, sizeof(key), "hide_%s", name);
    if(truth(app.engine.get(key))) continue;
    if(count++ != selected) continue;
    urq::copy_string(command, name);
    mk61_app_snprintf(app.services, key, sizeof(key), "display_%s", name);
    const auto display_name = app.engine.get(key);
    const char* label = truth(display_name) && display_name.type == 1 ? display_name.text : name + 4;
    mk61_app_snprintf(app.services, caption, 128, "%s", label);
    for(char* at = caption; *at; ++at) if(*at == '_') *at = ' ';
  }
  return count;
}
int menu_label(void* raw, uint32_t index, char* text, uint32_t capacity) {
  const Screen kind = Screen(uintptr_t(raw));
  if(kind == Screen::MENU) {
    static const char* const labels[] = {M8("Продолжить"), M8("Сохранить"), M8("Загрузить"),
        M8("Инвентарь"), M8("Начать заново"), M8("Выход")};
    urq::copy_string(text, labels[index]);
  } else if(kind == Screen::CONFIRM) urq::copy_string(text, index ? M8("Отмена") : M8("Выйти"));
  else if(kind == Screen::INVENTORY) {
    char command[128];
    if(index >= inventory(index, text, command)) return 0;
  } else mk61_app_snprintf(app.services, text, capacity, M8("Слот %u"), unsigned(index + 1));
  return 1;
}
int menu_choose(Screen kind, uint32_t count) {
  mk61_service_menu_source request{kind == Screen::SAVE ? M8("СОХРАНИТЬ") :
      kind == Screen::LOAD ? M8("ЗАГРУЗИТЬ") : kind == Screen::INVENTORY ? M8("ИНВЕНТАРЬ") :
      kind == Screen::CONFIRM ? M8("ВЫЙТИ ИЗ ИГРЫ?") : M8("МЕНЮ ИГРЫ"),
      (void*)(uintptr_t)kind, count, 0, menu_label};
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact) return classic_view::menu(app.services,request);
#endif
  return app.services->call(MK61_SERVICE_MENU, 0, 0, sizeof(request), &request) ? int(request.selected) : -1;
}
#endif
void open_menu() {
  end_typing();phone_input::finish(app.phone);
#if defined(MK61_URQ_SPLIT) && !defined(MK61_URQ_COLD)
  app.request = Request::MENU;
#else
  if(app.engine.state().status==urq::Status::QUIT) notice(M8("Конец"));
  if(app.engine.state().status==urq::Status::ERROR) {
    char error[64];mk61_app_snprintf(app.services,error,sizeof(error),"URQ E%u / L%lu",
        unsigned(app.engine.state().error),(unsigned long)app.engine.state().pc);
    notice(error);draw_game();mk61_api->key_wait();app.notice[0]=0;
  }
  const int selected = menu_choose(Screen::MENU, 6);
  if(selected == 1 || selected == 2) {
    const int slot = menu_choose(selected == 1 ? Screen::SAVE : Screen::LOAD, 5);
    if(slot >= 0) notice((selected == 1 ? save_slot(unsigned(slot)) : load_slot(unsigned(slot))) ?
        M8("Готово") : M8("Ошибка файла"));
  } else if(selected == 3) {
    const unsigned count=inventory(UINT32_MAX);
    if(!count) notice(M8("Инвентарь пуст"));
    const int item = menu_choose(Screen::INVENTORY, count);
    if(item >= 0) { char name[128], caption[128]; inventory(unsigned(item), caption, name); if(*name) app.engine.use(name); }
  } else if(selected == 4) {
    app.engine.start(); app.history.begin = app.history.end = app.view = app.scene = 0;
    app.history.cached = UINT32_MAX; app.length = app.cursor = 0;
  } else if(selected == 5 && menu_choose(Screen::CONFIRM, 2) == 0) app.quitting = true;
#endif
  app.last_ms = mk61_api->millis_ms(); app.dirty = true;
}
void game_key(int key);
void input_event(unsigned kind, uint8_t value = 0) {
  if(kind == MK61_TEXT_SUBMIT) {
    end_typing();
    app.engine.submit(app.input); app.length = app.cursor = 0; app.input[0] = 0;
  } else if(kind == MK61_TEXT_CANCEL || kind == MK61_TEXT_MENU) open_menu();
#if defined(MK61_TARGET_PICOCALC)
  else if(kind == MK61_TEXT_PAGE_UP) game_key(MK61_APP_KEY_LEFT);
  else if(kind == MK61_TEXT_PAGE_DOWN) game_key(MK61_APP_KEY_RIGHT);
#endif
  else if(kind == MK61_TEXT_LEFT && app.cursor) --app.cursor;
  else if(kind == MK61_TEXT_RIGHT && app.cursor < app.length) ++app.cursor;
  else if(kind == MK61_TEXT_HOME) app.cursor = 0;
  else if(kind == MK61_TEXT_END_LINE) app.cursor = app.length;
#if defined(MK61_TARGET_PICOCALC)
  else if(kind == MK61_TEXT_UP) {
    urq::copy_string(app.input, app.engine.text(app.engine.state().last_input));
    app.length = app.cursor = uint16_t(strlen(app.input));
  }
  else if(kind == MK61_TEXT_DOWN) { app.length = app.cursor = 0; app.input[0] = 0; }
#endif
  else if(kind == MK61_TEXT_BACKSPACE && app.cursor) {
    memmove(app.input + app.cursor - 1, app.input + app.cursor, app.length - app.cursor + 1);
    --app.cursor; --app.length;
  }
#if defined(MK61_TARGET_PICOCALC)
  else if(kind == MK61_TEXT_DELETE && app.cursor < app.length) {
    memmove(app.input + app.cursor, app.input + app.cursor + 1, app.length - app.cursor);
    --app.length;
  }
#endif
  else if(kind == MK61_TEXT_CHAR) {
    if(unsigned(app.length) + 1 >= 256) notice(full_line.data());
    else {
      memmove(app.input + app.cursor + 1, app.input + app.cursor, app.length - app.cursor + 1);
      app.input[app.cursor++] = char(value); ++app.length;
    }
  }
  app.dirty = true;
}
[[maybe_unused]] void input_key(int key) {
  app.notice[0]=0;
#if !defined(MK61_TARGET_PICOCALC)
  const bool pending = app.phone.key != 0;
  if(key >= 0 && key <= 9) {
    if(!phone_input::tap(app.phone, app.input, app.length, app.cursor, 256,
                         uint8_t(key), mk61_api->millis_ms())) notice(full_line.data());
    app.dirty = true; return;
  }
  phone_input::finish(app.phone);
  if(key == MK61_APP_KEY_K) { app.phone.layout = uint8_t((app.phone.layout + 1) % 3); app.dirty = true; return; }
  if(key == MK61_APP_KEY_F) { app.phone.lowercase = !app.phone.lowercase; app.dirty = true; return; }
  if(key == MK61_APP_KEY_RIGHT && pending) { app.dirty = true; return; }
#endif
  if(key == MK61_APP_KEY_OK) input_event(MK61_TEXT_SUBMIT);
  else if(key == MK61_APP_KEY_ESC || key == MK61_APP_KEY_USER) open_menu();
  else if(key == MK61_APP_KEY_CLEAR) input_event(MK61_TEXT_BACKSPACE);
  else if(key == MK61_APP_KEY_LEFT) input_event(MK61_TEXT_LEFT);
  else if(key == MK61_APP_KEY_RIGHT) input_event(MK61_TEXT_RIGHT);
  else if(up(key)) input_event(MK61_TEXT_HOME);
  else if(down(key)) input_event(MK61_TEXT_END_LINE);
}
void game_key(int key) {
  app.notice[0]=0;
  if(key == MK61_APP_KEY_ESC || key == MK61_APP_KEY_USER) { open_menu(); return; }
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact && app.engine.state().status==urq::Status::CHOICE) {
    if(key==MK61_APP_KEY_OK && !app.actions) {app.actions=true;app.dirty=true;return;}
    if(!app.actions && key>=0 && key<=9) return;
    if(app.actions) {
      uint16_t indices[urq::ACTIONS];const unsigned count=action_indices(indices);
      if(up(key) || key==MK61_APP_KEY_LEFT) {
        if(app.menu) app.menu=0;else if(app.selected) --app.selected;
      } else if(down(key) || key==MK61_APP_KEY_RIGHT) {
        if(app.action_next) app.menu=app.action_next;
        else if(unsigned(app.selected)+1<count) {++app.selected;app.menu=0;}
      } else if(key==MK61_APP_KEY_OK || (key>=0 && key<=9)) {
        const unsigned index=key==MK61_APP_KEY_OK?app.selected:key?unsigned(key-1):9;
        if(index<count) {app.engine.choose(app.engine.state().actions[indices[index]].id);app.actions=false;app.menu=0;}
      }
      app.dirty=true;return;
    }
  }
#endif
  if(key == MK61_APP_KEY_LEFT
#if defined(MK61_TARGET_PICOCALC)
     || key == MK61_APP_KEY_RAW_BASE + 0xD6
#endif
     ) {
    uint32_t at = app.view > 1024 ? app.view - 1024 : app.history.begin;
    if(at < app.history.begin) at = app.history.begin;
    uint32_t previous = at;
    while(at < app.view) { const auto next = page(at, false); if(next >= app.view || next == at) break; previous = at; at = next; }
    app.view = previous;
  } else if(key == MK61_APP_KEY_RIGHT
#if defined(MK61_TARGET_PICOCALC)
     || key == MK61_APP_KEY_RAW_BASE + 0xD7
#endif
     ) { if(app.next < app.history.end) app.view = app.next; }
  else if(app.engine.state().status == urq::Status::ANYKEY) app.engine.resume(key == MK61_APP_KEY_OK ? 13U : uint32_t(key));
  else {
    uint16_t indices[urq::ACTIONS]; const unsigned count = action_indices(indices);
    if(up(key) && app.selected) --app.selected;
    else if(down(key) && unsigned(app.selected) + 1 < count) ++app.selected;
    else if((key == MK61_APP_KEY_OK || (key >= 0 && key <= 9)) && count) {
      unsigned index = app.selected;
      if(key >= 0 && key <= 9) index = key ? unsigned(key - 1) : 9;
      if(index < count) app.engine.choose(app.engine.state().actions[indices[index]].id);
    }
  }
  app.dirty = true;
}
bool bind_session() {
  if(!app.pack.open({nullptr, read, size})) return false;
  auto& state = *(urq::State*)app.lease.data;
  urq::Host host;
  host.print = print; host.clear = clear; host.number = number; host.clock = clock;
  host.parse = parse;
#if defined(MK61_URQ_SPLIT) && !defined(MK61_URQ_COLD)
  host.save = [](void*) { app.request = Request::SAVE; return true; };
  host.resource=[](void*,bool url,const char* path) {
    if(!app.engine.set(url?"file_url":"file_content",{0,path,1})) return false;
    app.request=url?Request::URL:Request::CONTENT;return true;
  };
  host.deferred_save = true;
#else
  host.save = [](void*) { return save_slot(0); };
#if defined(MK61_TARGET_PICOCALC)
  host.resource=[](void*,bool url,const char* path) {
    char content[urq::LINE_BYTES];return app.pack.resource(path,content,sizeof(content),url) &&
      app.engine.set(url?"file_url":"file_content",{0,content,1});
  };
#endif
#endif
  host.power = [](void*, double a, double b) { return app.services->math(MK61_SERVICE_POW, a, b); };
  host.service = [](void*) { mk61_api->service(); };
  app.engine.attach(app.pack, state, host);
  return true;
}
void finish_session();
[[maybe_unused]] uint32_t begin_session(uint32_t id) {
  const auto* services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FILES |
      MK61_SERVICE_CAP_MEMORY | MK61_SERVICE_CAP_NUMBER_IO | MK61_SERVICE_CAP_FILE_WRITE_SOURCE |
      MK61_SERVICE_CAP_MENU_SOURCE | MK61_SERVICE_CAP_ECMA_NUMBERS);
  if(!services) return MK61_APP_RUNTIME_ERROR;
  if(!(services->call(MK61_SERVICE_SETUP,MK61_SETUP_FEATURES,0,0,nullptr)&MK61_SETUP_FEATURE_RTC_VALUE))
    return MK61_APP_RUNTIME_ERROR;
#if defined(MK61_TARGET_PICOCALC)
  if(!(services->call(MK61_SERVICE_CAPABILITIES, 0, 0, 0, nullptr) & MK61_SERVICE_CAP_TEXT_INPUT))
    return MK61_APP_RUNTIME_ERROR;
#endif
  mk61_service_file file{};
  if(!services->call(MK61_SERVICE_FILE_ENTRY, 0, id, 0, &file) || file.type != MK61_SERVICE_FILE_URQ)
    return MK61_APP_INVALID_FILE;
  mk61_service_lease shell_lease{};
  if(!services->call(MK61_SERVICE_MEMORY_ACQUIRE, MK61_SERVICE_SCRATCH,
                     MK61_SERVICE_OWNER_APP, sizeof(App), &shell_lease)) return MK61_APP_BUSY;
  app_state = ::new(shell_lease.data) App{};
  app.services = services; app.shell_lease = shell_lease;
#if !defined(MK61_TARGET_PICOCALC)
  app.compact=classic_view::available(services);
#endif
#if defined(MK61_TARGET_PICOCALC)
  app.colored = (services->call(MK61_SERVICE_CAPABILITIES, 0, 0, 0, nullptr) & MK61_SERVICE_CAP_TEXT_COLORS) != 0;
#endif
  app.file = id; app.parent = file.parent; app.part = app.part_id = 0xFFFF;
  if(!app.pack.open({nullptr, read, size})) {
    services->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_SCRATCH, 0, 0, &shell_lease);
    return MK61_APP_INVALID_FILE;
  }
  app.lease = {};
  if(!app.services->call(MK61_SERVICE_MEMORY_ACQUIRE, MK61_SERVICE_WORKSPACE,
                          MK61_SERVICE_OWNER_APP, sizeof(urq::State), &app.lease)) {
    services->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_SCRATCH, 0, 0, &shell_lease);
    return MK61_APP_BUSY;
  }
  ::new(app.lease.data) urq::State{};
  app.input = app.draft;
  app.history.init(app.services);
  app.view = app.scene = 0; app.quitting = false; app.russian = true;
  app.dirty = true; app.typing = false; app.notice[0] = 0; app.selected = app.menu = 0;
  app.length = app.cursor = 0; app.input[0] = 0; app.phone = {};
  if(!bind_session()) { finish_session(); return MK61_APP_INVALID_FILE; }
  app.engine.start();
  return MK61_APP_OK;
}
[[maybe_unused]] void run_session() {
  auto& state = app.engine.state();
  uint32_t revision=UINT32_MAX;
  app.last_ms = mk61_api->millis_ms();
  while(!app.quitting && app.request == Request::NONE) {
    mk61_api->service();
    const uint32_t now = mk61_api->millis_ms(), elapsed = now - app.last_ms; app.last_ms = now;
    {
      app.engine.tick(elapsed);
      if(state.status == urq::Status::RUNNING) { app.engine.run(64); app.dirty = true; }
      if(state.status == urq::Status::ERROR) {
        open_menu();
      } else if(state.status == urq::Status::INPUT && !app.typing) {
#if defined(MK61_URQ_SPLIT) && !defined(MK61_URQ_COLD)
        app.request=Request::INPUT;
#else
        begin_typing(false);
#endif
      }
      else if(state.status == urq::Status::QUIT) open_menu();
    }
    if(app.request != Request::NONE) break;
    if(screen_changed(revision)) app.dirty=true;
    if(app.dirty) draw_game();
#if defined(MK61_TARGET_PICOCALC)
    if(app.typing) {
      mk61_service_text_event event{};
      if(app.services->call(MK61_SERVICE_TEXT_INPUT, MK61_TEXT_POLL, 0, sizeof(event), &event)) {
        app.russian = event.layout != 0;
        input_event(event.kind, uint8_t(event.value));
      }
    } else
#endif
    {
      const int key = mk61_api->key_poll();
      if(key >= 0) {
#if !defined(MK61_URQ_SPLIT) || defined(MK61_URQ_COLD)
        if(app.typing) input_key(key);else
#endif
        game_key(key);
      }
    }
    if(phone_input::expire(app.phone, now)) app.dirty = true;
    mk61_api->delay_ms(1);
  }
}
[[maybe_unused]] void finish_session() {
  const auto* services = app.services;
  mk61_service_lease shell_lease = app.shell_lease;
  end_typing(); app.history.close();
#if !defined(MK61_TARGET_PICOCALC)
  if(app.compact) mk61_api->graphics_end();
#endif
  display(MK61_SERVICE_DISPLAY_END_UI_TEXT);
  app.services->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_WORKSPACE, 0, 0, &app.lease);
  services->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_SCRATCH, 0, 0, &shell_lease);
  app_state = nullptr;
}
[[maybe_unused]] uint32_t choose_file() {
  const auto* services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_DIALOGS);
  if(!services) return MK61_SERVICE_INVALID_ID;
  mk61_service_choice choice{}; choice.parent = MK61_SERVICE_ROOT_ID;
  if(!services->call(MK61_SERVICE_FILE_CHOOSE, MK61_SERVICE_FILE_URQ, choice.parent, 1, &choice))
    return MK61_SERVICE_INVALID_ID;
  return choice.file.id;
}
#if defined(MK61_URQ_SPLIT)
struct FlowContext {
  uint32_t magic;
  App* state;
  uint16_t root, helper, file;
};
// Version the private shared shell layout independently of public APP ABI 6.
constexpr uint32_t FLOW_CONTEXT_MAGIC = 0x32515255;
static_assert(sizeof(FlowContext) <= MK61_APP_FLOW_USER_CONTEXT_SIZE, "URQ flow context");
#endif
}
#if defined(MK61_URQ_SPLIT)
extern "C" uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->context_size < sizeof(FlowContext)) return 0;
  auto& context = *(FlowContext*)flow->context;
#if defined(MK61_URQ_COLD)
  if(context.magic == FLOW_CONTEXT_MAGIC && flow->current.phase == uint32_t(Request::INIT)) {
    const uint32_t result=begin_session(context.file);
    if(!result) context.state=app_state;
    mk61_app_flow_return(flow,result,MK61_FLOW_OK);return 1;
  }
  if(context.magic != FLOW_CONTEXT_MAGIC || !context.state) return 0;
  app_state = context.state;
  if(!bind_session()) { mk61_app_flow_return(flow, MK61_APP_IO_ERROR, MK61_FLOW_OK); return 1; }
  const auto request = Request(flow->current.phase); app.request = Request::NONE;
  if(request == Request::MENU) open_menu();
  else if(request == Request::INPUT) {
    begin_typing(false);
    uint32_t revision=UINT32_MAX;
    while(app.typing && !app.quitting) {
      mk61_api->service();
      if(screen_changed(revision)) app.dirty=true;
      if(app.dirty) draw_game();
      const int key=mk61_api->key_poll();if(key>=0) input_key(key);
      if(phone_input::expire(app.phone,mk61_api->millis_ms())) app.dirty=true;
      if(app.engine.state().status!=urq::Status::INPUT) end_typing();
      else if(!app.typing && !app.quitting) begin_typing(false);
      mk61_api->delay_ms(1);
    }
  }
  else if(request == Request::SAVE) {
    const bool ok=save_slot(0);notice(ok?M8("Готово"):M8("Ошибка файла"));
    mk61_app_flow_return(flow,ok?MK61_APP_OK:MK61_APP_IO_ERROR,MK61_FLOW_OK);return 1;
  }
  else if(request==Request::CONTENT || request==Request::URL) {
    const bool url=request==Request::URL;const char* key=url?"file_url":"file_content";
    const urq::Value path=app.engine.get(key);char content[urq::LINE_BYTES];
    const bool ok=path.type==1 && app.pack.resource(path.text,content,sizeof(content),url) && app.engine.set(key,{0,content,1});
    mk61_app_flow_return(flow,ok?MK61_APP_OK:MK61_APP_IO_ERROR,MK61_FLOW_OK);return 1;
  }
  else return 0;
  mk61_app_flow_return(flow, MK61_APP_OK, MK61_FLOW_OK);
#else
  if(context.magic != FLOW_CONTEXT_MAGIC) {
    const uint32_t file = flow->current.phase == MK61_APP_FLOW_FILE_PHASE ?
        *(const uint32_t*)flow->context : choose_file();
    if(file == MK61_SERVICE_INVALID_ID) { mk61_app_flow_exit(flow, 0, MK61_FLOW_OK); return 1; }
    context = {}; context.root = flow->current.file_id;context.file=uint16_t(file);
    const auto* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
    mk61_service_file parent{}, helper{};
    const bool found = services && services->call(MK61_SERVICE_FILE_ENTRY, 0, context.root, 0, &parent) &&
        services->call(MK61_SERVICE_FILE_RESOLVE, parent.parent, MK61_SERVICE_FILE_APP,
            uint32_t(uintptr_t("URQUI.APP")), &helper) == 0;
    if(!found) {
      mk61_app_flow_exit(flow, MK61_APP_INVALID_FILE, MK61_FLOW_OK); return 1;
    }
    context.helper = uint16_t(helper.id);context.magic=FLOW_CONTEXT_MAGIC;
    mk61_app_flow_call(flow,mk61_app_flow_to(MK61_APP_KIND_APPLICATION,context.helper,uint32_t(Request::INIT)),1);
    return 1;
  } else {
    if(!context.state) {mk61_app_flow_exit(flow,flow->result?flow->result:uint32_t(MK61_APP_IO_ERROR),MK61_FLOW_OK);context={};return 1;}
    app_state = context.state;
    if(!bind_session()) {
      finish_session(); mk61_app_flow_exit(flow, MK61_APP_IO_ERROR, MK61_FLOW_OK); return 1;
    }
    app.request = Request::NONE;
    app.engine.finish_save(flow->status == MK61_FLOW_OK && !flow->result);
    if(flow->status != MK61_FLOW_OK || flow->result) notice(M8("Ошибка файла"));
  }
  run_session();
  if(app.quitting) {
    finish_session(); context = {};
    mk61_app_flow_exit(flow, MK61_APP_OK, MK61_FLOW_OK);
  } else mk61_app_flow_call(flow, mk61_app_flow_to(MK61_APP_KIND_APPLICATION, context.helper,
                    uint32_t(app.request)), 1);
#endif
  return 1;
}
#if !defined(MK61_URQ_COLD)
extern "C" uint32_t mk61_app_file_flow(void) { return MK61_APP_FLOW_MAGIC; }
#endif
extern "C" uint32_t mk61_app_open_file(uint32_t) { return MK61_APP_RUNTIME_ERROR; }
int main() { return MK61_APP_RUNTIME_ERROR; }
#else
extern "C" uint32_t mk61_app_open_file(uint32_t id) {
  const uint32_t result = begin_session(id);
  if(result) return result;
  run_session(); finish_session(); return MK61_APP_OK;
}
int main() {
  const uint32_t file = choose_file();
  return file == MK61_SERVICE_INVALID_ID ? MK61_APP_OK : int(mk61_app_open_file(file));
}
#endif
