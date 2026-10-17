#ifndef MK61_PICOCALC_M61_PLATFORM_HPP
#define MK61_PICOCALC_M61_PLATFORM_HPP
#include "calculator_control.hpp"
#include "m61_text.hpp"
#include "program_store.hpp"
#include "storage_path.hpp"

u32 millis();
void MK61Emu_ClearCodePage();
void reinit_mk61_calculator_state();
bool load_binary_program(u16 directory, const char *arguments);
i32 program_store_text_font_begin();
i32 program_store_text_font_load_from(const char *name, u16 directory);
i32 program_store_text_font_restore();
i32 program_store_text_font_end();
namespace picocalc {
namespace script {
u8 open_entry(
    const program_store::Entry &entry); // completed / stopped / failed
void report_error(const m61_text::Error &error);
} // namespace script
} // namespace picocalc
#endif
