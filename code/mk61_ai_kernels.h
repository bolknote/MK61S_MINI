#ifndef MK61AI_KERNELS_H
#define MK61AI_KERNELS_H

#include <stdint.h>

/* Portable scalar kernels for the native model runtime.
 * Each call consumes exactly 32 int8 activations and 32 Q2/Q4 weight codes.
 * Codes are offset binary: q = code - 2^(bits-1), low code first in a byte.
 * Q4 matches MKQ4v1. Scales are applied by the future caller per group of 32.
 * Activation quantization and float/fixed-point scales are NOT implemented.
 * Input/output arguments must be valid, non-overlapping SRAM buffers.
 */
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  int16_t subset[8][16];
  int16_t sum;
} mk61ai_lut32;

/* Experimental g=8 tables. Same bit-plane weight bytes as g=4, eight times
 * the table storage. Not selected by the production model dispatcher. */
typedef struct {
  int16_t subset[4][256];
  int16_t sum;
} mk61ai_lut8x32;

void mk61ai_prepare_lut32(const int8_t x[32], mk61ai_lut32 *table);
int32_t mk61ai_dot_q2_a8_32(const uint8_t codes[8], const int8_t x[32]);
int32_t mk61ai_dot_q4_a8_32(const uint8_t codes[16], const int8_t x[32]);
int32_t mk61ai_dot_lut_q2_a8_32(const uint8_t planes[8],
                                const mk61ai_lut32 *table);
int32_t mk61ai_dot_lut_q4_a8_32(const uint8_t planes[16],
                                const mk61ai_lut32 *table);
void mk61ai_prepare_lut8x32(const int8_t x[32], mk61ai_lut8x32 *table);
int32_t mk61ai_dot_lut8_q4_a8_32(const uint8_t planes[16],
                                const mk61ai_lut8x32 *table);

/* Offline repacking only; the device should load an already repacked file.
 * Each bit plane has eight 4-bit indices, packed low nibble first.
 * Repacking changes neither quantized weights nor their total byte count.
 */
void mk61ai_pack_q2_planes32(const uint8_t codes[8], uint8_t planes[8]);
void mk61ai_pack_q4_planes32(const uint8_t codes[16], uint8_t planes[16]);

#ifdef __cplusplus
}
#endif
#endif
