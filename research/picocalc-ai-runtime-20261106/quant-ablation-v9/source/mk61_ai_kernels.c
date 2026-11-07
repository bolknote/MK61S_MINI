#include "mk61_ai_kernels.h"

/* Scalar adaptation of the bit-plane/table principle described in T-MAC:
 * https://arxiv.org/abs/2407.00088 (EuroSys 2025).
 * This independent prototype has no SIMD, table quantization, or TVM code.
 * For a quartet x, subset[m] = sum(x[j] where bit j of m is set).
 * dot(q,x) = sum(2^b * subset[weight_plane_b]) - bias * sum(x).
 * For int8 input each table entry is in [-512,508], so int16 is exact.
 * Multiplications by small constants below are intentional: a left shift of
 * a negative signed value would be undefined C, even when a CPU shift is safe.
 */

void mk61ai_prepare_lut32(const int8_t x[32], mk61ai_lut32 *table) {
  int32_t total = 0;
  for (unsigned g = 0; g < 8; ++g) {
    int16_t *t = table->subset[g];
    t[0] = 0;
    for (unsigned j = 0; j < 4; ++j) {
      const unsigned half = 1U << j;
      for (unsigned m = 0; m < half; ++m)
        t[m + half] = (int16_t)(t[m] + x[4 * g + j]);
    }
    total += t[15];
  }
  table->sum = (int16_t)total;
}

int32_t mk61ai_dot_q2_a8_32(const uint8_t codes[8], const int8_t x[32]) {
  int32_t result = 0;
  for (unsigned i = 0; i < 8; ++i) {
    unsigned c = codes[i];
    for (unsigned j = 0; j < 4; ++j) {
      result += ((int32_t)(c & 3U) - 2) * x[4 * i + j];
      c >>= 2;
    }
  }
  return result;
}

int32_t mk61ai_dot_q4_a8_32(const uint8_t codes[16], const int8_t x[32]) {
  int32_t result = 0;
  for (unsigned i = 0; i < 16; ++i) {
    result += ((int32_t)(codes[i] & 15U) - 8) * x[2 * i];
    result += ((int32_t)(codes[i] >> 4) - 8) * x[2 * i + 1];
  }
  return result;
}

int32_t mk61ai_dot_lut_q2_a8_32(const uint8_t planes[8],
                                const mk61ai_lut32 *table) {
  int32_t result = -2 * (int32_t)table->sum;
  for (unsigned g = 0; g < 8; ++g) {
    const unsigned i = g >> 1, shift = (g & 1U) * 4;
    const int16_t *t = table->subset[g];
    result +=
        t[(planes[i] >> shift) & 15U] + 2 * t[(planes[4 + i] >> shift) & 15U];
  }
  return result;
}

int32_t mk61ai_dot_lut_q4_a8_32(const uint8_t planes[16],
                                const mk61ai_lut32 *table) {
  int32_t result = -8 * (int32_t)table->sum;
  for (unsigned g = 0; g < 8; ++g) {
    const unsigned i = g >> 1, shift = (g & 1U) * 4;
    const int16_t *t = table->subset[g];
    result += t[(planes[i] >> shift) & 15U] +
              2 * t[(planes[4 + i] >> shift) & 15U] +
              4 * t[(planes[8 + i] >> shift) & 15U] +
              8 * t[(planes[12 + i] >> shift) & 15U];
  }
  return result;
}

static void pack_planes(const uint8_t *codes, uint8_t *planes, unsigned bits) {
  for (unsigned i = 0; i < 4 * bits; ++i)
    planes[i] = 0;
  for (unsigned b = 0; b < bits; ++b) {
    for (unsigned g = 0; g < 8; ++g) {
      unsigned index = 0;
      for (unsigned j = 0; j < 4; ++j) {
        const unsigned position = (4 * g + j) * bits;
        const unsigned code = codes[position >> 3] >> (position & 7U);
        index |= ((code >> b) & 1U) << j;
      }
      planes[4 * b + (g >> 1)] |= (uint8_t)(index << ((g & 1U) * 4));
    }
  }
}

void mk61ai_pack_q2_planes32(const uint8_t codes[8], uint8_t planes[8]) {
  pack_planes(codes, planes, 2);
}
void mk61ai_pack_q4_planes32(const uint8_t codes[16], uint8_t planes[16]) {
  pack_planes(codes, planes, 4);
}
