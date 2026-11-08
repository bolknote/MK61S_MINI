#pragma once
#include <stdint.h>
inline void hw_set_bits(uint32_t *p,uint32_t v) { *p |= v; }
inline void hw_clear_bits(uint32_t *p,uint32_t v) { *p &= ~v; }
inline void __dmb() { __asm__ volatile("" ::: "memory"); }
