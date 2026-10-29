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
// Synchronous lookup/indexing and the initial service slice. Allows only
// memory-only input progress while source/font reads own C9 temporaries.
bool loading_program(void);
bool active(void);
// Remaining monotonic milliseconds of this script's timer; zero when inactive.
u32 timer_remaining_ms(void);
bool calculator_suspended(void);
#if defined(M61_TEXT_HOST_TEST)
  bool test_waiting_for_time(void);
#endif
// A saved trap snapshot forbids writes; an input handler deliberately allows them.
bool trap_handler_active(void);
// Stable logical key numbers from m61_keys.hpp, before native key dispatch.
// Captures the complete gesture; callbacks are serialized at core boundaries.
bool handle_key_event(u8 code, bool down);
bool captures_key(u8 code);
bool key_bindings_active(void);
bool keyboard_available(void);
bool display_owned(void);
void claim_display(void);
void release_display(void);
void service(void);
void cancel(void);
// Снимает все bind/trap (включая таймер и ожидающее событие) во всех кадрах.
// Не прерывает ещё исполняющийся обычный сценарий.
// Возвращает true, если было что снимать.
bool clear_bindings_and_traps(void);
bool last_error(Error& out);
bool format_current_program(u8* out, u16 capacity, u16* out_len);

} // пространство имён m61_text

#endif
