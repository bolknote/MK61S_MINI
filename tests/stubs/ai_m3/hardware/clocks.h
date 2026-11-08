#pragma once
#include <stdint.h>
enum { clk_peri };
inline uint32_t clock_get_hz(int) { return 48000000; }
