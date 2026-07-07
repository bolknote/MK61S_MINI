#ifndef SOUND_DRIVER_HPP
#define SOUND_DRIVER_HPP

#include "rust_types.h"

// Hardware sound driver for the buzzer. Firmware code should use the public
// sound()/sound_stop() facade from tools.hpp; this file owns timer setup.
void sound_driver_init(usize pin);
void sound_driver_play(usize pin, isize frequency_Hz, usize duration_ms, usize volume);
void sound_driver_play_scaled(usize pin, isize frequency_Hz, usize duration_ms, usize volume, usize volume_percent);
void sound_driver_stop(void);
void sound_driver_poll(void);

#endif
