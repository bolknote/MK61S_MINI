#pragma once
#include <stdint.h>
struct clocks_hw_t { uint32_t sleep_en0, sleep_en1; };
extern clocks_hw_t *clocks_hw;
#define CLOCKS_SLEEP_EN1_CLK_SYS_UART1_BITS (1u << 5)
#define CLOCKS_SLEEP_EN1_CLK_PERI_UART1_BITS (1u << 6)
