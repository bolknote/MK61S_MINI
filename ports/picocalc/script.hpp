#ifndef MK61_PICOCALC_SCRIPT_HPP
#define MK61_PICOCALC_SCRIPT_HPP
#include "calculator.hpp"
#include "program_store.hpp"
#include "text_screen.hpp"
#include "audio.hpp"
namespace picocalc {
class Services;
namespace script {
void attach(Calculator &calculator, Services &services);
void memory_mode(u8 mode);
bool start(const char *path);
bool start_source(const char *path, const char *source, u16 length,
                  u16 *snapshot_id = nullptr);
bool register_source(const char *path, const char *source, u16 length,
                     program_store::Entry &out);
void reset_files();
void prepare_files();
bool register_file(const char *path, program_store::Entry &out);
const char *file_path(u16 id);
bool normalize_path(const char* base,const char* name,char out[384]);
program_store::ProgramType file_type(const char* path);
bool press_scan(u8 code);
bool write_program(u16 address, const u8 *bytes, u16 count);
u16 program_limit();
bool input(u8 code);
void output(const char *text);
bool print(const char *arguments);
const u8 *frame();
u32 frame_revision();
const u8* native_frame();
void show_native_frame(const u8* frame,bool compatibility_crop=true);
void show_frame(const u8 *frame);
void show_text(const char *text);
void write_text(unsigned column, unsigned row, const char* text, unsigned length);
void show_lines(const char *lines, unsigned stride, unsigned count,
                unsigned cursor_x, unsigned cursor_y,bool incremental=false);
u8 open_entry(const program_store::Entry &entry);
void text_row(unsigned row, char *out, unsigned capacity);
void tone(unsigned frequency, unsigned milliseconds, unsigned percent=100);
audio::Plan tone_status();
void led(bool on);
bool led_blink(unsigned count,unsigned on_ms,unsigned off_ms);
bool led_status();
bool led_blinking();
void led_stop();
void service_effects();
bool font_rows(u16 codepoint, u8 rows[8]);
unsigned graphic_text(u8* frame,double x,double y,const char* text,unsigned length);
bool font_active();
unsigned columns();
unsigned rows();
text_screen::FontGeometry text_profile();
bool text_profile(text_screen::FontGeometry profile);
bool activate_font();
bool install_prepared(const u8* data,unsigned size);
const u8* active_font_data(unsigned& size);
u32 font_revision();
void write_codepoint(unsigned column,unsigned row,u16 codepoint);
void record_codepoint(unsigned column,unsigned row,u16 codepoint);
void clear_text_record();
int flow_text(const char* text,unsigned length,unsigned first,unsigned maximum,bool tail=false,bool empty=false);
} // namespace script
} // namespace picocalc
#endif
