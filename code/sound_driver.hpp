#ifndef SOUND_DRIVER_HPP
#define SOUND_DRIVER_HPP

#include "rust_types.h"

// Hardware sound driver for the buzzer. The public sound() wrappers remain in
// tools.cpp so existing firmware code can keep using the same call sites.
void sound_driver_init(usize pin);
void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume);
void sound_driver_stop(void);
void sound_driver_poll(void);

#endif
