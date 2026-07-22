#ifndef M61_TEXT_HPP
#define M61_TEXT_HPP

#include "rust_types.h"

namespace m61_text {

struct Error {
  char script[16];
  u16 line;
  char message[64];
};

bool load_program(const char* name);
bool load_program(u16 id);
bool open_program(const char* name);
bool open_program(u16 id);
bool active(void);
bool calculator_suspended(void);
bool display_owned(void);
void claim_display(void);
void service(void);
void cancel(void);
bool last_error(Error& out);
bool format_current_program(u8* out, u16 capacity, u16* out_len);

} // пространство имён m61_text

#endif
