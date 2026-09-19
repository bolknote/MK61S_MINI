#include "system_compat.hpp"
#include "storage_path.hpp"
#include "builtin_font.hpp"
#include "mk_math.hpp"
#include <math.h>
#include <stdio.h>

extern "C" { const mk61_system_runtime_function* mk61_system_runtime; }

namespace portable_system {
const mk61_system_api* api;
const mk61_app_api* app;
u32 image_crc;
u32 kind;
bool bind(const mk61_app_api* base, u32 crc, u32 app_kind) {
  // Every newly built APP obtains services through the current public API.
  const auto* sys = mk61_app_get_services(base, 0);
  const u32 required = MK61_APP_CAP_TIME | MK61_APP_CAP_FILES;
  if(!sys || !sys->keyboard_mapping || !sys->math || !sys->format ||
      (base->capabilities & required) != required) return false;
  api = sys; app = base; image_crc = crc; kind = app_kind;
#if defined(MK61_BUILD_FOCAL_MODULE) || defined(MK61_BUILD_TINYBASIC_MODULE)
  if(!sys->runtime) return false;
  for(u32 i = 0; i < MK61_RUNTIME_COUNT; ++i) if(!sys->runtime[i]) return false;
  u32 required_services = MK61_SERVICE_CAP_NUMBER_IO;
#if MK61_APP_LOCAL_FLOAT_MATH_MASK
  required_services |= MK61_SERVICE_CAP_FLOAT_CONVERT;
#endif
  if((sys->call(MK61_SERVICE_CAPABILITIES, 0, 0, 0, nullptr) &
      required_services) != required_services) return false;
  mk61_system_runtime = sys->runtime;
#endif
  return true;
}
void text_rows(const char* const* rows, u32 count) {
  call(MK61_SYS_TEXT_ROWS, count, 0, 0, (void*) rows);
}
void editor(bool draw, const char* source, u16 len, u16 cursor, u16& top, bool sms) {
  mk61_system_editor request = {source, len, cursor, top, sms};
  call(draw ? MK61_SYS_EDITOR_DRAW : MK61_SYS_EDITOR_SCROLL, 0, 0, 0, &request);
  top = (u16) request.top;
}
bool format_number(double value, u8 significant_digits,
                   char* output, usize capacity) {
  mk61_system_number_format request = {
      value, output, (u32) capacity, significant_digits};
  return call(MK61_SYS_NUMBER_FORMAT, 0, 0, 0, &request) != 0;
}
bool parse_number(const char* input, double& value, const char*& end) {
  mk61_system_number_parse request = {0.0, input, 0};
  if(call(MK61_SYS_NUMBER_PARSE, 0, 0, 0, &request) == 0) return false;
  value = request.value;
  end = input + request.consumed;
  return true;
}
}
using portable_system::call;
namespace keyboard_layout { const Mapping& active() { return *portable_system::api->keyboard_mapping; } }
extern "C" u32 millis() { return portable_system::app->millis_ms(); }
extern "C" u32 micros() { return call(MK61_SYS_MICROS); }
extern "C" void delay(u32 ms) { portable_system::app->delay_ms(ms); }
void idle_main_process() { portable_system::app->service(); }
void sound_stop() { portable_system::app->sound_stop(); }
void sound_scaled(u32, isize frequency, usize duration, usize, usize percent) {
  portable_system::app->beep((u32) frequency, duration, percent);
}
namespace entropy_pool { u32 next_u32(Domain domain) { return call(MK61_SYS_RANDOM, (u32) domain); } }
namespace library_mk61 {
bool language_is_ru() { return call(MK61_SYS_SETTINGS, MK61_SYS_LANGUAGE); }
u8 sound_volume() { return (u8) call(MK61_SYS_SETTINGS, MK61_SYS_VOLUME); }
}
AngleUnit read_grade_switch() { return (AngleUnit) call(MK61_SYS_SETTINGS, MK61_SYS_ANGLE); }
namespace kbd {
Event poll_event() { return Event((i32) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_POLL)); }
isize scan() { return (isize) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_SCAN); }
i32 get_key(key_state state) { return (i32) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_GET, (u32) state); }
i32 get_key() { return (i32) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_GET, 0xFFFFFFFFU); }
i32 get_key_wait() { return (i32) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_WAIT); }
i32 last_key() { return (i32) call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_LAST); }
bool is_key_pressed(i32 key) { return call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_PRESSED, (u32) key); }
bool take_immediate_press(i32 key) { return call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_IMMEDIATE, (u32) key); }
void clear_immediate_presses() { call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_CLEAR_IMMEDIATE); }
void clear_hold_key() { call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_CLEAR_HOLD); }
void handoff(Event event) { call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_HANDOFF, (u32) event.code()); }
bool handoff_pending() { return call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_HANDOFF_PENDING); }
bool any_key_pressed() { return call(MK61_SYS_KEYBOARD, MK61_SYS_KEY_ANY); }
}

void MK61Display::clear() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_CLEAR); }
void MK61Display::setCursor(u8 x, u8 y) { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_CURSOR, x, y); }
void MK61Display::write(u8 value) { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_WRITE, value); }
void MK61Display::print(const char* text) { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_PRINT, 0, 0, (void*) text); }
void MK61Display::cursorOn() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_CURSOR_ON); }
void MK61Display::cursorOff() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_CURSOR_OFF); }
bool MK61Display::supportsCursor() const { return call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_SUPPORTS_CURSOR); }
void MK61Display::flush() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_FLUSH); }
void MK61Display::beginUpdate() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_BEGIN_UPDATE); }
void MK61Display::endUpdate() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_END_UPDATE); }
void MK61Display::endShiftedViewport() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_END_VIEWPORT); }
void MK61Display::endUiText() { call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_END_UI_TEXT); }
bool MK61Display::supportsFullscreenBitmap() const { return call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_GRAPHICS); }
u16 MK61Display::fullscreenBitmapWidth() const { return (u16) call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_WIDTH); }
u16 MK61Display::fullscreenBitmapHeight() const { return (u16) call(MK61_SYS_DISPLAY, MK61_SYS_DISPLAY_HEIGHT); }
MK61Display& main_lcd() { static MK61Display display; return display; }
namespace lcd_ru {
void print_lines(const char* a, const char* b) { const char* rows[] = {a, b}; portable_system::text_rows(rows, 2); }
}
void class_menu::select() {
  if(count_ < 1 || count_ > 4) return;
  mk61_system_menu_item items[4];
  for(int i = 0; i < count_; ++i) items[i] = {entries_[i]->text, entries_[i]->action, entries_[i]->size};
  call(MK61_SYS_MENU, (u32) count_, 0, 0, items);
}

static void import_file(const mk61_system_file& file, program_store::Entry& entry) {
  entry = {}; entry.type = (program_store::ProgramType) file.type;
  entry.kind = (program_store::NodeKind) file.kind;
  entry.id = (u16) file.id; entry.parent_id = (u16) file.parent; entry.data_len = (u16) file.size;
  memcpy(entry.name, file.name, sizeof(entry.name));
}
namespace program_store {
int count(ProgramType type) { return (int) call(MK61_SYS_FILE_COUNT, (u32) type); }
bool entry(ProgramType type, int index, Entry& out) {
  mk61_system_file file = {};
  if(!call(MK61_SYS_FILE_ENTRY, 1, (u32) index, (u32) type, &file)) return false;
  import_file(file, out); return true;
}
bool entry_by_id(u16 id, Entry& out) {
  mk61_system_file file = {};
  if(!call(MK61_SYS_FILE_ENTRY, 0, id, 0, &file)) return false;
  import_file(file, out); return true;
}
bool read_range_id(u16 id, u16 offset, u8* data, u16 size, u16* length) {
  const u32 read = portable_system::app->file_read(id, offset, data, size);
  if(length) *length = read <= size ? (u16) read : 0;
  return read <= size;
}
bool read_id(u16 id, u8* data, u16 capacity, u16* length) {
  const u32 size = portable_system::app->file_size(id);
  if(size > capacity) return false;
  return read_range_id(id, 0, data, (u16) size, length);
}
bool exists(ProgramType type, const char* name) {
  return call(MK61_SYS_FILE_EXISTS, (u32) type, 0, 0, (void*) name);
}
bool remove(ProgramType type, const char* name) { return call(MK61_SYS_FILE_REMOVE, (u32) type, 0, 0, (void*) name); }
bool remove_id(u16 id) { return call(MK61_SYS_FILE_REMOVE, id); }
bool write_file(u16 parent, u16 preferred, ProgramType type, const char* name, const u8* data, u16 size, u16* id) {
  mk61_system_write request = {name, data, size, INVALID_ID};
  const bool ok = call(MK61_SYS_FILE_WRITE, parent, preferred, (u32) type, &request);
  if(id) *id = (u16) request.id;
  return ok;
}
}
namespace storage_path {
Status resolve_file(u16 cwd, const char* path, program_store::ProgramType type, program_store::Entry& out) {
  mk61_system_file file = {};
  const auto status = (Status) call(MK61_SYS_FILE_RESOLVE, cwd, (u32) type, (u32) (usize) path, &file);
  if(status == Status::OK) import_file(file, out);
  return status;
}
}
ProgramStoreFileDialogResult program_store_choose_file(program_store::ProgramType type,
    u16 parent, bool allow_new, program_store::Entry& entry, u16& new_parent) {
  mk61_system_choice out = {};
  const auto result = (ProgramStoreFileDialogResult) call(MK61_SYS_FILE_CHOOSE, (u32) type, parent, allow_new, &out);
  import_file(out.file, entry); new_parent = (u16) out.parent;
  return result;
}
bool program_store_choose_save_target(program_store::ProgramType type, u16 parent,
    char* name, usize capacity, u16& new_parent) {
  mk61_system_save_target request = {name, new_parent};
  const bool ok = call(MK61_SYS_FILE_SAVE_TARGET, (u32) type, parent, capacity, &request);
  new_parent = (u16) request.parent; return ok;
}
namespace language_workspace {
Lease::Lease(Owner owner, usize size) : lease_{} {
  (void) owner;
  lease_.image_crc = portable_system::image_crc;
  call(MK61_SYS_MEMORY_ACQUIRE, 0, portable_system::kind, size, &lease_);
}
Lease::~Lease() { if(ok()) call(MK61_SYS_MEMORY_RELEASE, 0, 0, 0, &lease_); }
void* data(Owner owner) {
  (void) owner;
  return (void*) (usize) call(MK61_SYS_MEMORY_DATA, portable_system::kind);
}
}
namespace shared_scratch {
Lease::Lease(Owner owner, usize size) : lease_{} {
  (void) owner;
  call(MK61_SYS_MEMORY_ACQUIRE, 1, portable_system::kind, size, &lease_);
}
Lease::~Lease() { reset(); }
void Lease::reset() { if(ok()) call(MK61_SYS_MEMORY_RELEASE, 1, 0, 0, &lease_); }
}
namespace builtin_font {
bool decode(FaceId face, u16 codepoint, Raster& out) {
  mk61_system_glyph glyph = {};
  if(!call(MK61_SYS_FONT, (u32) face, codepoint, 0, &glyph)) return false;
  out = {}; out.width = (u8) glyph.width; out.height = (u8) glyph.height;
  memcpy(out.data, glyph.pixels, sizeof(glyph.pixels)); return true;
}
}
#if !defined(MK61_BUILD_SETUP_MODULE)
namespace fmk {
bool bitmapPixel(const u8* bitmap, u8 width, u8 x, u8 y) {
  return bitmap && (bitmap[(usize) y * ((width + 7U) / 8U) + x / 8U] & (0x80U >> (x & 7U)));
}
}
#endif
namespace mk_math {
#if MK61_APP_LOCAL_FLOAT_MATH
namespace {
float local_float(double value) {
  mk61_system_float_convert request = {value, 0};
  portable_system::call(MK61_SYS_FLOAT_CONVERT,
                        MK61_SYS_FLOAT_FROM_DOUBLE, 0, 0, &request);
  float result = 0.0f;
  memcpy(&result, &request.bits, sizeof(result));
  return result;
}
double local_double(float value) {
  mk61_system_float_convert request = {0.0, 0};
  memcpy(&request.bits, &value, sizeof(value));
  portable_system::call(MK61_SYS_FLOAT_CONVERT,
                        MK61_SYS_DOUBLE_FROM_FLOAT, 0, 0, &request);
  return request.value;
}
}
#define MK61_LOCAL_UNARY(name, bit, operation, function) \
  double name(double x) { \
    if constexpr((MK61_APP_LOCAL_FLOAT_MATH_MASK & (bit)) != 0) \
      return local_double(::function(local_float(x))); \
    return portable_system::api->math((operation), x, 0.0); \
  }
MK61_LOCAL_UNARY(sin,   MK61_APP_FLOAT_SIN,   MK61_SYS_SIN,   sinf)
MK61_LOCAL_UNARY(cos,   MK61_APP_FLOAT_COS,   MK61_SYS_COS,   cosf)
MK61_LOCAL_UNARY(tan,   MK61_APP_FLOAT_TAN,   MK61_SYS_TAN,   tanf)
MK61_LOCAL_UNARY(asin,  MK61_APP_FLOAT_ASIN,  MK61_SYS_ASIN,  asinf)
MK61_LOCAL_UNARY(acos,  MK61_APP_FLOAT_ACOS,  MK61_SYS_ACOS,  acosf)
MK61_LOCAL_UNARY(atan,  MK61_APP_FLOAT_ATAN,  MK61_SYS_ATAN,  atanf)
MK61_LOCAL_UNARY(ln,    MK61_APP_FLOAT_LN,    MK61_SYS_LN,    logf)
MK61_LOCAL_UNARY(log10, MK61_APP_FLOAT_LOG10, MK61_SYS_LOG10, log10f)
MK61_LOCAL_UNARY(exp,   MK61_APP_FLOAT_EXP,   MK61_SYS_EXP,   expf)
MK61_LOCAL_UNARY(sqrt,  MK61_APP_FLOAT_SQRT,  MK61_SYS_SQRT,  sqrtf)
#undef MK61_LOCAL_UNARY
double pow(double x, double y) {
  if constexpr((MK61_APP_LOCAL_FLOAT_MATH_MASK & MK61_APP_FLOAT_POW) != 0)
    return local_double(::powf(local_float(x), local_float(y)));
  return portable_system::api->math(MK61_SYS_POW, x, y);
}
#else
double sin(double x) { return portable_system::api->math(MK61_SYS_SIN, x, 0); }
double cos(double x) { return portable_system::api->math(MK61_SYS_COS, x, 0); }
double tan(double x) { return portable_system::api->math(MK61_SYS_TAN, x, 0); }
double asin(double x) { return portable_system::api->math(MK61_SYS_ASIN, x, 0); }
double acos(double x) { return portable_system::api->math(MK61_SYS_ACOS, x, 0); }
double atan(double x) { return portable_system::api->math(MK61_SYS_ATAN, x, 0); }
double ln(double x) { return portable_system::api->math(MK61_SYS_LN, x, 0); }
double log10(double x) { return portable_system::api->math(MK61_SYS_LOG10, x, 0); }
double exp(double x) { return portable_system::api->math(MK61_SYS_EXP, x, 0); }
double sqrt(double x) { return portable_system::api->math(MK61_SYS_SQRT, x, 0); }
double pow(double x, double y) { return portable_system::api->math(MK61_SYS_POW, x, y); }
#endif
}
extern "C" int snprintf(char* output, size_t size, const char* format, ...) {
  va_list args; va_start(args, format);
  const int result = portable_system::api->format(output, size, format, args);
  va_end(args); return result;
}
