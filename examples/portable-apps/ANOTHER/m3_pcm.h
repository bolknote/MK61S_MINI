#ifndef MK61_ANOTHER_M3_PCM_H
#define MK61_ANOTHER_M3_PCM_H
#include <stdint.h>

/* Experimental, pointer-free M3 mixer job. The caller unfolds sample loops
 * and supplies up to four contiguous signed 8-bit source windows.
 * All integers are little-endian. Header:
 *   u32 AWM1, u16 sequence, u8 frames (1..64), u8 active mask,
 *   u16 gain (0..1000), u16 reserved,
 *   4 x {u16 offset, u8 bytes, u8 active frames, u8 fractional phase,
 *        u8 volume, u16 step}.
 * Source offsets are relative to the packet. Output:
 *   u32 PWM1, u8 frames, u8 zero, u16 sequence, frames x PWM8.
 * Each input sample is signed 8-bit; step/phase have eight fractional bits.
 * Active frames can end before the block for a non-looping sound.
 */
#define AW_M3_MAGIC 0x314D5741u
#define AW_M3_PWM 0x314D5750u
#define AW_M3_HEADER 44u
#define AW_M3_MAX_FRAMES 64u
#define AW_M3_MAX_INPUT 512u

static inline uint16_t aw_m3_get16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1] << 8); }
static inline uint32_t aw_m3_get32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static inline void aw_m3_put16(uint8_t *p, uint16_t n) { p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); }
static inline void aw_m3_put32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}
#endif
