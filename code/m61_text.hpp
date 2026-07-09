#ifndef M61_TEXT_HPP
#define M61_TEXT_HPP

#include "rust_types.h"

namespace m61_text {

bool execute(const u8* text, u16 len);
bool load_program(const char* name);
bool open_program(const char* name);
bool start(const u8* text, u16 len);
bool active(void);
void service(void);
void cancel(void);
bool format_current_program(u8* out, u16 capacity, u16* out_len);

} // namespace m61_text

#endif
