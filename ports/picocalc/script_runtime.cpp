#include "builtin_font.hpp"
#include "canvas.hpp"
#include "cross_hal.h"
#include "fmk_font.hpp"
#include "prepared_font.hpp"
#include "m61_ansi.hpp"
#include "m61_platform.hpp"
#include "m61_print.hpp"
#include "mk8_codec.hpp"
#include "program_load.hpp"
#include "program_memory_policy.hpp"
#include "script.hpp"
#include "clock.hpp"
#include "services.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"
#include "terminal_listing.hpp"
#include "terminal_mnemonics.hpp"
#include "terminal_script.hpp"
#include "terminal_script_backend.hpp"
#include "version.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/rand.h"
#include "pico/stdlib.h"
#else
#include <chrono>
#endif

#include "cross_key_pairs.inc"

namespace picocalc {
namespace script {
namespace {
Calculator *calculator = nullptr;
Services *services = nullptr;
u8 mode = 2;
text_screen::Grid grid;
u8 raster[1536]{};
bool native_visible=true;
u32 frame_generation=1;
m61_ansi::SavedCursor saved_cursor{};
fmk::Face face;
prepared_font::Face prepared;
bool open_face(const u8* data,unsigned size) { face.reset();prepared.reset();return face.open(data,size) || prepared.open(data,size); }
u8 *font_data = nullptr;
unsigned font_size = 0;
u32 font_generation = 1;
text_screen::FontGeometry profile{8,5,8,0};
struct SavedFont { u8* data; unsigned size; text_screen::FontGeometry profile; };
SavedFont saved_fonts[4]{};
unsigned font_depth = 0;
constexpr char classic_isa[] =
#include "terminal_classic_isa.inc"
    ;
constexpr char symbols[16] = {'O', '1', '2', '3', '4', '5',        '6', '7',
                              '8', '9', '-', 'L', 'C', (char)0xC3, 'E', ' '};
struct Effect {
  u16 value, hold;
};
Effect sound[16]{}, light[16]{};
u8 sound_count = 0, sound_index = 0, light_count = 0, light_index = 0;
u32 sound_at = 0, light_at = 0;
audio::Plan current_tone{};
u32 tone_deadline=0;
bool tone_pending=false;
u64 tone_started=0;
struct Blink { u32 left=0,at=0,on_ms=0,off_ms=0;bool on=false; } blinking;
bool led_value=false;
bool default_text_font() {
  return !face.valid() && !prepared.valid();
}
unsigned cell_width() {
  if(default_text_font()) return profile.width<=3?10:16;
  return prepared.valid()?prepared.metrics().default_advance:face.valid() ? face.metrics().default_advance : profile.width + 1;
}
unsigned cell_height() {
  if(default_text_font()) return profile.width<=3?20:profile.width>=10?32:28;
  return prepared.valid()?prepared.metrics().height+prepared.metrics().line_gap:face.valid() ? face.metrics().height + face.metrics().line_gap : profile.height + profile.line_gap;
}
bool native_font_geometry() {
  return default_text_font() || ((face.valid() || prepared.valid()) && (cell_width()>7 || cell_height()>8));
}
void pixel(unsigned x, unsigned y, bool on) {
  if (x >= 192 || y >= 64)
    return;
  u8 &byte = raster[(y / 8) * 192 + x];
  const u8 mask = (u8)(1U << (y % 8));
  if (on)
    byte |= mask;
  else
    byte &= (u8)~mask;
}
void paint(u8 x, u8 y, u16 cp) {
  const bool default_face=default_text_font();
  const unsigned width = default_face?profile.width+1:cell_width(), height = default_face?profile.height+profile.line_gap:cell_height(), left = x * width,
                 top = y * height;
  for (unsigned gy = 0; gy < height; ++gy)
    for (unsigned gx = 0; gx < width; ++gx)
      pixel(left + gx, top + gy, false);
  // M61 coordinates remain character cells. Paint a separate native strike,
  // never an enlarged copy of the compact compatibility bitmap.
  native_visible=true;
  const unsigned nw=cell_width(), nh=cell_height();
  const bool native_font=native_font_geometry();
  const unsigned nx=(native_font?(canvas::WIDTH-grid.cols()*nw)/2:8)+x*nw;
  const unsigned ny=(native_font?(canvas::HEIGHT-grid.rows()*nh)/2:36)+y*nh;
  canvas::rect(canvas::frame(),nx,ny,nw,nh);
  if(default_face) { Settings font{};font.ui_font_family=1;font.ui_font_size=profile.width<=3?12:16;
    mk61_service_ui_glyph glyph{};fonts::glyph(font,cp,glyph);
    canvas::glyph(canvas::frame(),font,cp,nx+(nw-glyph.advance)/2,ny); }
  u8 byte = 0;
  fmk::Glyph glyph{};
  u8 bitmap[fmk::MAX_BITMAP_SIZE]{};
  prepared_font::Glyph pg{};
  const bool has_byte=mk8::from_codepoint(cp,byte);
  const bool has_prepared=prepared.valid() && has_byte && prepared.glyph(byte,pg) && prepared.decode(pg,bitmap,sizeof(bitmap));
  if(has_prepared) { glyph.width=pg.width;glyph.height=pg.height; }
  if (has_prepared || (face.valid() && has_byte &&
      face.glyph(byte, glyph) && face.decode(glyph, bitmap, sizeof(bitmap)))) {
    for (unsigned gy = 0; gy < glyph.height; ++gy)
      for (unsigned gx = 0; gx < glyph.width; ++gx)
        if (fmk::bitmapPixel(bitmap, glyph.width, gx, gy))
          { pixel(left + gx, top + gy, true);
            if(!default_face) canvas::pixel(canvas::frame(),nx+gx,ny+gy); }
  } else {
    builtin_font::Raster glyph{};
    if (builtin_font::decode(profile.width <= 3 && profile.height <= 5
            ? builtin_font::FaceId::FONT_3X5 : builtin_font::FaceId::FONT_5X8, cp, glyph)) {
      // The old wire view keeps its historical cell metrics. The LCD uses
      // the actual strike, including for custom cell envelopes.
      for(unsigned gy=0;gy<profile.height;++gy) for(unsigned gx=0;gx<profile.width;++gx)
        if(fmk::bitmapPixel(glyph.data,glyph.width,gx*glyph.width/profile.width,gy*glyph.height/profile.height))
          pixel(left+gx,top+gy,true);
      if(!default_face) for(unsigned gy=0;gy<glyph.height;++gy) for(unsigned gx=0;gx<glyph.width;++gx)
        if(fmk::bitmapPixel(glyph.data,glyph.width,gx,gy)) canvas::pixel(canvas::frame(),nx+gx,ny+gy);
    }
  }
}
bool put(u8 x, u8 y, u16 cp, void *) {
  ++frame_generation;
  grid.setCursor(x, y);
  grid.writeCodepoint(cp);
  paint(x, y, cp);
  return true;
}
bool clear(void *) {
  ++frame_generation;
  grid.clear();
  std::memset(raster, 0, sizeof(raster));
  canvas::clear();native_visible=true;
  return true;
}
void reshape() {
  ++frame_generation;
  ++font_generation;
  const bool native_font=native_font_geometry();
  unsigned columns = (native_font?canvas::WIDTH:192) / cell_width();
  unsigned rows = (native_font?canvas::HEIGHT:64) / cell_height();
  if (columns > text_screen::MAX_COLS)
    columns = text_screen::MAX_COLS;
  if (rows > text_screen::MAX_ROWS)
    rows = text_screen::MAX_ROWS;
  if(!face.valid() && !prepared.valid() && !default_text_font() && rows>profile.rows) rows=profile.rows;
  grid.reshape((u8)(rows ? rows : 1), (u8)(columns ? columns : 1));
  std::memset(raster, 0, sizeof(raster));
  canvas::clear();native_visible=true;
  for (u8 y = 0; y < grid.rows(); ++y)
    for (u8 x = 0; x < grid.cols(); ++x)
      paint(x, y, grid.cell(x, y));
}
bool write_byte(u8 byte, void *context) {
  return ((m61_ansi::Writer *)context)->writeLiteral(byte);
}
bool write_control(u8 byte, void *context) {
  return ((m61_ansi::Writer *)context)->write(byte);
}
bool write_value(const m61_print::ValueRef &value, void *context) {
  auto &writer = *(m61_ansi::Writer *)context;
  char number[15]{};
  if (value.kind == m61_print::ValueKind::REGISTER)
    MK61Emu_ReadRegister(value.index, number, symbols);
  else if (value.index == (u8)m61_print::StackValue::X2)
    std::snprintf(number, sizeof(number), "%s",
                  MK61Emu_GetIndicatorStr(symbols));
  else {
    const auto s = (m61_print::StackValue)value.index;
    read_stack_register(s == m61_print::StackValue::X   ? X
                        : s == m61_print::StackValue::Y ? Y
                        : s == m61_print::StackValue::Z ? Z
                        : s == m61_print::StackValue::T ? T
                                                        : X1,
                        number, symbols);
  }
  auto digit = [](char c) { return (u8)(c == 'O' ? '0' : c); };
  if (value.format == m61_print::ValueFormat::MANTISSA_HEAD)
    return writer.writeLiteral(digit(number[1]));
  if (value.format == m61_print::ValueFormat::ABS_EXPONENT) {
    return (digit(number[12]) == '0' ||
            writer.writeLiteral(digit(number[12]))) &&
           writer.writeLiteral(digit(number[13]));
  }
  for (const char *p = number; *p; ++p)
    if (!writer.writeLiteral((u8)*p))
      return false;
  return true;
}
bool pattern(const char *p, bool audio) {
  u32 values[32];
  unsigned count = 0;
  while (true) {
    while (*p == ' ' || *p == ',')
      ++p;
    if (!*p)
      break;
    if (count == 32 || *p < '0' || *p > '9')
      return false;
    u32 value = 0;
    while (*p >= '0' && *p <= '9') {
      const unsigned digit = *p++ - '0';
      if (value > (65535 - digit) / 10)
        return false;
      value = value * 10 + digit;
    }
    values[count++] = value;
  }
  if (!count || (audio ? count % 2 : !(count % 2)))
    return false;
  Effect candidate[16];
  const unsigned steps = audio ? count / 2 : (count + 1) / 2;
  for (unsigned i = 0; i < steps; ++i) {
    if (audio && values[i * 2 + 1] == 0)
      return false;
    if (!audio && values[i * 2] > 1)
      return false;
    candidate[i] = {(u16)values[i * 2],
                    (u16)(i * 2 + 1 < count ? values[i * 2 + 1] : 0)};
  }
  if (audio) {
    std::memcpy(sound, candidate, steps * sizeof(Effect));
    sound_count = steps;
    sound_index = 0;
    sound_at = millis();
  } else {
    blinking={};
    std::memcpy(light, candidate, steps * sizeof(Effect));
    light_count = steps;
    light_index = 0;
    light_at = millis();
  }
  service_effects();
  return true;
}
const char *arguments(const char *line) {
  while (*line && !terminal_core::is_space(*line))
    ++line;
  return terminal_core::skip_spaces(line);
}
void expand_for_binary() {
  if (mode != 2 || core_61::expanded_program_is_on())
    return;
  u8 page[core_61::CODE_PAGE_BUFFER_SIZE]{};
  for (unsigned i = 0; i < core_61::MAX_PROGRAM_STEP; ++i)
    (void)core_61::read_absolute_program((u16)i, page[i]);
  const AngleUnit angle = MK61Emu_GetAngleUnit();
  core_61::set_expanded_program_mode(true);
  core_61::enable();
  core_61::set_code_page(page);
  MK61Emu_SetAngleUnit(angle);
}
} // namespace
void attach(Calculator &core, Services &service) {
  if (!calculator)
    grid.reset(8, 32);
  calculator = &core;
  services = &service;
}
void memory_mode(u8 value) { mode = value; }
u16 program_limit() {
  return mode == 0 ? core_61::CLASSIC_PROGRAM_STEP
                   : core_61::EXTENDED_ADDRESS_LIMIT;
}
void output(const char *text) {
  if (text)
    std::fputs(text, stdout);
}
bool start(const char *path) {
  if (!calculator)
    return false;
  if (!m61_text::active())
    prepare_files();
  program_store::Entry entry;
  return register_file(path, entry) &&
         entry.type == program_store::ProgramType::MK61 &&
         m61_text::load_program(entry.id);
}
bool start_source(const char *path, const char *source, u16 length,
                  u16 *snapshot_id) {
  if(!source) return false;
  return start_source(path,language_vm::source::Input{const_cast<char*>(source),
      [](void* raw,u16 at,u8* out,u16 n) { std::memcpy(out,(char*)raw+at,n);return true; },length},snapshot_id);
}
bool start_source(const char *path,language_vm::source::Input source,
                  u16 *snapshot_id) {
  if (snapshot_id)
    *snapshot_id = program_store::INVALID_ID;
  if (!calculator)
    return false;
  if (!m61_text::active())
    prepare_files();
  program_store::Entry entry;
  if (!register_source(path, source, entry))
    return false;
  if (snapshot_id)
    *snapshot_id = entry.id;
  return m61_text::load_program(entry.id);
}
bool write_program(u16 address, const u8 *bytes, u16 count) {
  if (!bytes || !count || address >= program_limit() ||
      count > program_limit() - address)
    return false;
  u8 page[core_61::CODE_PAGE_BUFFER_SIZE]{};
  for (unsigned i = 0; i < core_61::MAX_PROGRAM_STEP; ++i)
    (void)core_61::read_absolute_program((u16)i, page[i]);
  for (unsigned i = 0; i < count; ++i)
    if (address + i < core_61::MAX_PROGRAM_STEP)
      page[address + i] = bytes[i];
  if (mode == 2) {
    const bool expanded =
        address + count > core_61::MAX_PROGRAM_STEP ||
        program_memory_policy::listing_needs_expanded_memory(
            page, core_61::MAX_PROGRAM_STEP, core_61::len_code_command);
    if (expanded != core_61::expanded_program_is_on()) {
      const AngleUnit angle = MK61Emu_GetAngleUnit();
      core_61::set_expanded_program_mode(expanded);
      core_61::enable();
      core_61::set_code_page(page);
      MK61Emu_SetAngleUnit(angle);
    }
  }
  for (u16 i = 0; i < count; ++i)
    if (!core_61::write_absolute_program(address + i, bytes[i]))
      return false;
  return true;
}
bool press_scan(u8 code) { return hidden_press_scan_code(code); }
bool input(u8 code) {
  if (!m61_text::active())
    return false;
  if (code == 0x1B || code == 0xB1) {
    m61_text::cancel();
    if (core_61::is_RUN())
      hidden_press_key(sw::RUN);
    return true;
  }
  if (code == '\n' || code == '\r') {
    if (!core_61::edit_program && m61_text::handle_ok_key())
      return true;
  }
  if (m61_text::calculator_suspended()) {
    const auto key = map_key(code);
    if (key.angle != NONE)
      MK61Emu_SetAngleUnit(key.angle);
    return true;
  }
  return false;
}
bool print(const char *args) {
  const auto control = m61_print::parse_control(args);
  if (control != m61_print::Control::NONE) {
    if (control == m61_print::Control::OFF) {
      clear(nullptr);
      grid.setCursor(0, 0);
      saved_cursor = {};
      m61_text::claim_display();
    } else
      m61_text::release_display();
    return true;
  }
  m61_ansi::Writer writer(grid.cols(), grid.rows(), grid.cursorX(),
                          grid.cursorY(), saved_cursor, {put, clear, nullptr});
  const auto result =
      m61_print::render(args, core_61::expanded_program_is_on(), write_byte,
                        write_value, &writer, write_control);
  grid.setCursor(writer.cursorX(), writer.cursorY());
  if (result.ok())
    m61_text::claim_display();
  else
    output(m61_print::error_message(result.error));
  return result.ok();
}
const u8 *frame() { return raster; }
u32 frame_revision() { return frame_generation; }
const u8* native_frame() { return native_visible?canvas::frame():nullptr; }
void show_native_frame(const u8* bytes,bool compatibility_crop) {
  ++frame_generation;
  if(bytes!=canvas::frame()) std::memcpy(canvas::frame(),bytes,canvas::BYTES);
  native_visible=true;
  // Old USB clients retain a 1:1 cropped view; new clients negotiate 320x320.
  if(compatibility_crop) for(unsigned page=0;page<8;++page) std::memcpy(raster+page*192,bytes+page*320,192);
  m61_text::claim_display();
}
const u8* active_font_data(unsigned& size) { size=font_size;return font_data; }
u32 font_revision() { return font_generation; }
void text_row(unsigned row, char *out, unsigned capacity) {
  unsigned used = 0;
  if (row < grid.rows())
    for (unsigned column = 0; column < grid.cols() && used + 1 < capacity;
         ++column) {
      u8 byte = 32;
      if (grid.cell(column, row))
        (void)mk8::from_codepoint(grid.cell(column, row), byte);
      out[used++] = (char)byte;
    }
  if (capacity)
    out[used] = 0;
}
void show_frame(const u8 *bytes) {
  ++frame_generation;
  native_visible=false;
  std::memcpy(raster, bytes, sizeof(raster));
  m61_text::claim_display();
}
void show_text(const char *text) {
  clear(nullptr);
  grid.setCursor(0, 0);
  m61_ansi::Writer writer(grid.cols(), grid.rows(), 0, 0, saved_cursor,
                          {put, clear, nullptr});
  for (const char *p = text; *p; ++p)
    (void)writer.writeLiteral((u8)*p);
  grid.setCursor(writer.cursorX(), writer.cursorY());
  m61_text::claim_display();
}
void write_text(unsigned column,unsigned row,const char* text,unsigned length) {
  for(unsigned i=0;i<length && column+i<grid.cols() && row<grid.rows();++i)
    put((u8)(column+i),(u8)row,mk8::codepoint((u8)text[i]),nullptr);
}
void write_codepoint(unsigned column,unsigned row,u16 cp) {
  if(column<grid.cols() && row<grid.rows()) put((u8)column,(u8)row,cp,nullptr);
}
void record_codepoint(unsigned column,unsigned row,u16 cp) {
  if(column<grid.cols() && row<grid.rows()) { grid.setCursor((u8)column,(u8)row);grid.writeCodepoint(cp); }
}
void clear_text_record() { grid.clear(); }
int flow_text(const char* text,unsigned length,unsigned first,unsigned maximum,bool tail,bool empty) {
  if(!text || length>65535 || first>=grid.rows() || !maximum || !mk8::text_valid((const u8*)text,length)) return 0;
  if(maximum>grid.rows()-first) maximum=grid.rows()-first;
  const auto next=[&](unsigned at,unsigned& end) {
    end=at;unsigned space=at;
    while(end<length && text[end]!='\n' && end-at<grid.cols()) { if(text[end]==' ' || text[end]=='\t') space=end;++end; }
    if(end<length && text[end]=='\n') return end+1;
    if(end<length && space>at) { end=space;return space+1; }
    return end;
  };
  unsigned total=0;
  for(unsigned at=0;at<length;) { unsigned end;at=next(at,end);++total; }
  if(!length && empty) total=1;
  const unsigned skip=tail && total>maximum?total-maximum:0;unsigned row=0,index=0;
  for(unsigned at=0;at<length;) {
    unsigned end;const unsigned after=next(at,end);
    if(index++>=skip && row<maximum) {
      for(unsigned x=0;x<grid.cols();++x) put((u8)x,(u8)(first+row),x<end-at?mk8::codepoint((u8)text[at+x]):' ',nullptr);
      ++row;
    }
    at=after;
  }
  if(!length && empty) { for(unsigned x=0;x<grid.cols();++x) put((u8)x,(u8)first,' ',nullptr);row=1; }
  return (int)row;
}
void show_lines(const char *lines, unsigned stride, unsigned count,
                unsigned cursor_x, unsigned cursor_y,bool incremental) {
  if(!incremental) clear(nullptr);
  for(unsigned y=0;y<grid.rows();++y) {
    const char* line=y<count?lines+y*stride:nullptr;
    unsigned length=0;
    if(line) while(length<stride && line[length]) ++length;
    for(unsigned x=0;x<grid.cols();++x) {
      const u16 cp=x<length?mk8::codepoint((u8)line[x]):' ';
      if(incremental?grid.cell(x,y)!=cp:cp!=' ')
        put((u8)x,(u8)y,cp,nullptr);
    }
  }
  grid.setCursor((u8)cursor_x, (u8)cursor_y);
  m61_text::claim_display();
}
audio::Plan tone_status() { return current_tone; }
void tone(unsigned frequency, unsigned milliseconds, unsigned percent) {
  const unsigned volume=services ? services->sound_volume() : 10;
  tone_pending=frequency && milliseconds && volume && percent;
  tone_deadline=millis()+milliseconds;
#if defined(PICO_ON_DEVICE)
  current_tone=audio::plan(clock_get_hz(clk_sys),frequency,volume,percent);
  tone_started=time_us_64();
  const unsigned slice = pwm_gpio_to_slice_num(26);
  pwm_set_enabled(slice,false);
  if(current_tone.software) {
    for(unsigned pin=26;pin<=27;++pin) { gpio_init(pin);gpio_set_dir(pin,GPIO_OUT);gpio_put(pin,true); }
    return;
  }
  for (unsigned pin = 26; pin <= 27; ++pin)
    gpio_set_function(pin, GPIO_FUNC_PWM);
  if (!current_tone.wrap) {
    pwm_set_both_levels(slice, 0, 0);
    return;
  }
  pwm_set_clkdiv_int_frac4(slice,(u8)(current_tone.divider16>>4),(u8)(current_tone.divider16&15));
  pwm_set_wrap(slice,(u16)(current_tone.wrap-1));
  pwm_set_both_levels(slice,(u16)current_tone.level,(u16)current_tone.level);
  pwm_set_enabled(slice, true);
#else
  current_tone=audio::plan(125000000,frequency,volume,percent);
#endif
}
void led(bool on) {
  led_value=on;
#if defined(PICO_ON_DEVICE)
  gpio_init(25);
  gpio_set_dir(25, GPIO_OUT);
  gpio_put(25, on);
#else
  (void)on;
#endif
}
bool led_status() { return led_value; }
bool led_blinking() { return blinking.left!=0; }
void led_stop() { blinking={};light_count=0;led(false); }
bool led_blink(unsigned count,unsigned on_ms,unsigned off_ms) {
  if(!count || count>65535 || on_ms>60000 || off_ms>60000) return false;
  light_count=0;blinking={count*2-1,millis()+on_ms,on_ms,off_ms,true};led(true);return true;
}
void service_effects() {
  const u32 now = millis();
  if(tone_pending && (i32)(now-tone_deadline)>=0) tone(0,0);
#if defined(PICO_ON_DEVICE)
  if(current_tone.software) {
    const bool high=(time_us_64()-tone_started)%current_tone.period_us<current_tone.on_us;
    gpio_put(26,high);gpio_put(27,high);
  }
#endif
  if (sound_count && (i32)(now - sound_at) >= 0) {
    if (sound_index == sound_count) {
      sound_count = 0;
      tone(0, 0);
    } else {
      const auto note = sound[sound_index++];
      tone(note.value, note.hold);
      sound_at = now + note.hold;
    }
  }
  if (light_count && (i32)(now - light_at) >= 0) {
    const auto step = light[light_index++];
    led(step.value != 0);
    light_at = now + step.hold;
    if (light_index == light_count)
      light_count = 0;
  }
  if(blinking.left && (i32)(now-blinking.at)>=0) {
    blinking.on=!blinking.on;led(blinking.on);--blinking.left;
    blinking.at=now+(blinking.on?blinking.on_ms:blinking.off_ms);
  }
}
u8 open_entry(const program_store::Entry &entry) {
  const char *path = file_path(entry.id);
  if (!path)
    return 2;
  if (entry.type == program_store::ProgramType::MK61)
    return m61_text::open_program(entry.id) ? 0 : 2;
  if (entry.type == program_store::ProgramType::MK61_BINARY) {
    if (core_61::is_RUN() || program_load::blocked())
      return 2;
    expand_for_binary();
    return program_load::load(entry.id, 0, program_limit()) ? 0 : 2;
  }
  if (entry.type == program_store::ProgramType::IMAGE1)
    return services ? services->view_image(path) : 2;
  if (entry.type == program_store::ProgramType::FONT)
    return program_store_text_font_load_from(path, program_store::ROOT_ID) == 1 &&
                   activate_font() ? 0 : 2;
  return services ? services->run_external(path) : 2;
}
void report_error(const m61_text::Error &error) {
  char message[128];
  std::snprintf(message, sizeof(message), "M61 %s:%u: %s", error.script,
                error.line, error.message);
  std::puts(message);
  if (services)
    services->show_script_error(message);
}
bool font_rows(u16 cp, u8 rows[8]) {
  u8 byte;
  fmk::Glyph glyph;
  return face.valid() && mk8::from_codepoint(cp, byte) &&
         face.glyph(byte, glyph) && fmk::scaleToLcd5x8(face, glyph, rows);
}
unsigned graphic_text(u8* out,double x,double y,const char* text,unsigned length) {
  const bool custom=face.valid() || prepared.valid();
  Settings font{};font.ui_font_family=1;font.ui_font_size=16;
  const auto metrics=fonts::info(font);
  const unsigned pitch=custom?cell_height():metrics.height+metrics.line_gap;
  if(y<=-(double)pitch || y>=320 || x>=320) return pitch;
  for(unsigned i=0;i<length && x<320;++i) {
    const u16 cp=mk8::codepoint((u8)text[i]);
    if(custom) {
      prepared_font::Glyph pg{};fmk::Glyph g{};u8 bits[fmk::MAX_BITMAP_SIZE]{};
      const bool ready=prepared.valid() && prepared_font::glyphForCodepoint(prepared,cp,pg) && prepared.decode(pg,bits,sizeof(bits));
      if(ready) { g.width=pg.width;g.height=pg.height; }
      u8 byte=0;
      const bool found=ready || (face.valid() && mk8::from_codepoint(cp,byte) && face.glyph(byte,g) && face.decode(g,bits,sizeof(bits)));
      const unsigned advance=cell_width();
      if(x>-(double)advance) {
        for(unsigned gy=0;gy<pitch;++gy) for(unsigned gx=0;gx<advance;++gx)
          canvas::pixel(out,(int)x+gx,(int)y+gy,found && gx<g.width && gy<g.height && fmk::bitmapPixel(bits,g.width,gx,gy));
      }
      x+=advance;
    } else {
      mk61_service_ui_glyph g{};fonts::glyph(font,cp,g);
      if(x>-(double)g.advance) {
        canvas::rect(out,(int)x,(int)y,g.advance,pitch);
        canvas::glyph(out,font,cp,(int)x,(int)y);
      }
      x+=g.advance;
    }
  }
  return pitch;
}
bool font_active() { return face.valid() || prepared.valid(); }
text_screen::FontGeometry text_profile() {
  if(prepared.valid()) return {(u8)grid.rows(),prepared.metrics().max_width,prepared.metrics().height,prepared.metrics().line_gap};
  return face.valid() ? text_screen::FontGeometry{(u8)grid.rows(),face.metrics().default_advance,
      face.metrics().height,face.metrics().line_gap} : profile;
}
bool text_profile(text_screen::FontGeometry value) {
  if(!value.rows || value.rows>10 || value.width<3 || value.width>10 || value.height<5 ||
      value.height>16 || value.line_gap>4 || value.rows*(value.height+value.line_gap)>64) return false;
  profile=value;face.reset();prepared.reset();std::free(font_data);font_data=nullptr;font_size=0;reshape();return true;
}
bool activate_font() { reshape();return true; }
bool install_prepared(const u8* data,unsigned size) {
  prepared_font::Face candidate;if(!data || size>prepared_font::MAX_IMAGE_SIZE || !candidate.open(data,size)) return false;
  auto* copy=(u8*)std::malloc(size);if(!copy) return false;std::memcpy(copy,data,size);
  face.reset();prepared.reset();std::free(font_data);font_data=copy;font_size=size;
  prepared.open(copy,size);reshape();return true;
}
unsigned columns() { return grid.cols(); }
unsigned rows() { return grid.rows(); }
} // namespace script
} // namespace picocalc

u32 millis() {
#if defined(PICO_ON_DEVICE)
  return (u32)(time_us_64() / 1000);
#else
  return (u32)std::chrono::duration_cast<std::chrono::milliseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
#endif
}
void lcd_std_display_redraw() {}
void mk61_program_started() {}
void reinit_mk61_calculator_state() {
  using namespace picocalc::script;
  const AngleUnit angle = MK61Emu_GetAngleUnit();
  core_61::clear_extended_program_banks();
  if (calculator)
    calculator->init(mode == 1);
  else {
    core_61::set_expanded_program_mode(mode == 1);
    core_61::enable();
  }
  MK61Emu_SetAngleUnit(angle);
}
bool load_binary_program(u16 directory, const char *args) {
  program_load::Request request{};
  if (program_load::parse(args, request) != program_load::Syntax::BINARY)
    return program_load::reject("Usage: load <four-digit-address> <path.bin>");
  program_store::Entry entry;
  if (storage_path::resolve_file(directory, request.path,
                                 program_store::ProgramType::MK61_BINARY,
                                 entry) != storage_path::Status::OK)
    return program_load::reject("Cannot open binary program");
  using namespace picocalc::script;
  if (core_61::is_RUN() || program_load::blocked())
    return false;
  if (entry.data_len <= 4 ||
      entry.data_len > program_store::MAX_MK61_BINARY_SIZE)
    return program_load::reject("Invalid binary program file");
  expand_for_binary();
  return program_load::load(entry.id, request.address, program_limit());
}
i32 program_store_text_font_begin() {
  using namespace picocalc::script;
  if(font_depth==4) return -3;
  u8* copy=nullptr;
  if(font_data) { copy=(u8*)std::malloc(font_size);if(!copy) return -3;std::memcpy(copy,font_data,font_size); }
  saved_fonts[font_depth++]={font_data,font_size,profile};
  font_data=copy;if(copy) open_face(copy,font_size);
  return 1;
}
i32 program_store_text_font_restore() {
  using namespace picocalc::script;
  u8* copy=nullptr;unsigned size=0;
  if(font_depth) {
    const auto& saved=saved_fonts[font_depth-1];size=saved.size;
    if(saved.data) { copy=(u8*)std::malloc(size);if(!copy) return -3;std::memcpy(copy,saved.data,size); }
    profile=saved.profile;
  }
  face.reset();prepared.reset();std::free(font_data);font_data=copy;font_size=size;
  if(copy) open_face(copy,size);
  reshape();
  return 1;
}
i32 program_store_text_font_end() {
  using namespace picocalc::script;
  if(!font_depth) return program_store_text_font_restore();
  const auto saved=saved_fonts[--font_depth];saved_fonts[font_depth]={};
  face.reset();prepared.reset();std::free(font_data);font_data=saved.data;font_size=saved.size;profile=saved.profile;
  if(font_data) open_face(font_data,font_size);
  reshape();
  return 1;
}
i32 program_store_text_font_load_from(const char *name, u16 directory) {
  using namespace picocalc::script;
  program_store::Entry entry;
  if (storage_path::resolve_file(directory, name,
                                 program_store::ProgramType::FONT,
                                 entry) != storage_path::Status::OK)
    return 0;
  auto *bytes = (u8 *)std::malloc(fmk::MAX_FILE_SIZE);
  if (!bytes)
    return -3;
  unsigned used = 0;
  fmk::Face candidate;
  if (!picocalc::files::read(file_path(entry.id), bytes, fmk::MAX_FILE_SIZE,
                             used) ||
      !candidate.open(bytes, used)) {
    std::free(bytes);
    return -1;
  }
  u8 *old = font_data;
  font_data = bytes;
  font_size = used;
  face = candidate;prepared.reset();
  std::free(old);
  reshape();
  return 1;
}

namespace terminal_script_backend {
void reset() {}
u16 program_limit() { return picocalc::script::program_limit(); }
bool write_program(u16 address, const u8 *bytes, u16 count) {
  return picocalc::script::write_program(address, bytes, count);
}
bool press_key(u8 scan) { return picocalc::script::press_scan(scan); }
u32 random_decimal7() {
#if defined(PICO_ON_DEVICE)
  u32 word;
  do {
    word = get_rand_32();
  } while (word >= 4289999571UL);
  return word % 9999999U + 1;
#else
  static u32 word = 0x41C64E6D;
  word = word * 1664525U + 1013904223U;
  return word % 9999999U + 1;
#endif
}
bool assemble(const char *args, isize &next) {
  return terminal_script::assemble(args, next, picocalc::script::classic_isa);
}
void error(const char *text) { std::puts(text); }
terminal_protocol::Result command(u8 id, const char *line, bool) {
  using namespace picocalc::script;
  using Result = terminal_protocol::Result;
  const char *args = arguments(line);
  char buffer[160];
  if(id==CMD_DATE || id==CMD_ALARM) return picocalc::clock::command(id,args)?Result::ok():Result::error();
  if (id == CMD_PRINT)
    return print(args) ? Result::ok() : Result::error();
  if (id == CMD_LED || id == CMD_BEEP)
    return pattern(args, id == CMD_BEEP) ? Result::ok() : Result::error();
  if (id == CMD_VERSION) {
    output("MK61S PicoCalc ");output(picocalc::VERSION);output(" / shared M61 runner\n");
    return Result::ok();
  }
  if (id == CMD_STACK || id == CMD_REG_DUMP) {
    const unsigned count = id == CMD_STACK                     ? 5
                           : core_61::expanded_program_is_on() ? 16
                                                               : 15;
    for (unsigned i = 0; i < count; ++i) {
      char raw[15];
      if (id == CMD_STACK)
        read_stack_register(i == 0   ? X
                            : i == 1 ? Y
                            : i == 2 ? Z
                            : i == 3 ? T
                                     : X1,
                            raw, nullptr);
      else
        MK61Emu_ReadRegister(i, raw, nullptr);
      std::snprintf(buffer, sizeof(buffer), "%s%X = %s\n",
                    id == CMD_STACK ? "S" : "R", i, raw);
      output(buffer);
    }
    return Result::ok();
  }
  if (id == CMD_1302) {
    char raw[43];
    MK61Emu_get_1302_R(raw);
    output(raw);
    output("\n");
    return Result::ok();
  }
  if (id == CMD_RING) {
    for (unsigned i = 0; i < core_61::ring_size(); ++i) {
      std::snprintf(buffer, sizeof(buffer), "%X%c", ringM[i],
                    i % 42 == 41 ? '\n' : ' ');
      output(buffer);
    }
    return Result::ok();
  }
  if (id == CMD_ISA) {
    for (unsigned i = 0; i < 240; ++i) {
      char name[9];
      terminal_mnemonics::english((u8)i, name);
      std::snprintf(buffer, sizeof(buffer), "%02X %s\n", i, name);
      output(buffer);
    }
    return Result::ok();
  }
  if (id == CMD_LIST || id == CMD_DUMP || id == CMD_LASM || id == CMD_PUB ||
      id == CMD_HOUT) {
    usize start = 0, count = core_61::program_steps();
    if (id == CMD_HOUT && !terminal_core::at_end(args)) {
      if (!terminal_core::parse_unsigned(
              args, 10, core_61::EXTENDED_ADDRESS_LIMIT - 1, start) ||
          !terminal_core::parse_unsigned(args, 10, core_61::MAX_PROGRAM_STEP,
                                         count) ||
          !count || !terminal_core::at_end(args) ||
          start + count > program_limit())
        return Result::error();
    }
    for (usize i = 0; i < count; ++i) {
      u8 opcode;
      if (!core_61::read_absolute_program((u16)(start + i), opcode))
        return Result::error();
      if (id == CMD_HOUT) {
        if (i % 24 == 0) {
          std::snprintf(buffer, sizeof(buffer), "hin %04u ",
                        (unsigned)(start + i));
          output(buffer);
        }
        std::snprintf(buffer, sizeof(buffer), "%02X", opcode);
        output(buffer);
        if (i % 24 == 23 || i + 1 == count)
          output("\n");
      } else {
        char name[9];
        if (id == CMD_PUB)
          terminal_mnemonics::csv(classic_isa, opcode, name);
        else
          terminal_mnemonics::english(opcode, name);
        std::snprintf(buffer, sizeof(buffer), "%04u %02X%s%s\n",
                      (unsigned)(start + i), opcode,
                      id == CMD_LASM || id == CMD_PUB ? " " : "",
                      id == CMD_LASM || id == CMD_PUB ? name : "");
        output(buffer);
      }
    }
    return Result::ok();
  }
  return Result::error();
}
} // namespace terminal_script_backend
