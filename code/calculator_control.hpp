#ifndef MK61_CALCULATOR_CONTROL_HPP
#define MK61_CALCULATOR_CONTROL_HPP

#include "rust_types.h"

enum class sw : u32;

// Direct calculator-core input used when an intermediate UI or M61 runner
// owns the normal keyboard queue.
void hidden_press_key(sw key);
void hidden_return_to_program_start(void);
void hidden_start_loaded_program(void);
bool hidden_press_scan_code(i32 keycode);

#endif
