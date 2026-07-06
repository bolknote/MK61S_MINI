#ifndef M61_TEXT_HPP
#define M61_TEXT_HPP

#include "rust_types.h"

namespace m61_text {

bool execute(const u8* text, u16 len);
bool format_current_program(u8* out, u16 capacity, u16* out_len);

} // namespace m61_text

#endif
