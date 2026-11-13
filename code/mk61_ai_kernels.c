#include "mk61_ai_kernels.h"
#if defined(PICO_ON_DEVICE)
#include "pico.h"
#define LUT8_RAM(name) __not_in_flash_func(name)
#define LUT8_OPT __attribute__((optimize("O3")))
#define PACK_COLD __attribute__((section(".ai_diagnostic_extension"),noinline))
#else
#define LUT8_RAM(name) name
#define LUT8_OPT
#define PACK_COLD
#endif

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

LUT8_OPT void LUT8_RAM(mk61ai_prepare_lut8x32)(const int8_t x[32], mk61ai_lut8x32 *table) {
  int32_t total = 0;
  for (unsigned g = 0; g < 4; ++g) {
    int16_t *t = table->subset[g];
    t[0] = 0;
    for (unsigned lane = 0; lane < 8; ++lane) {
      const unsigned half = 1U << lane;
      for (unsigned mask = 0; mask < half; ++mask)
        t[mask + half] = (int16_t)(t[mask] + x[8 * g + lane]);
    }
    total += t[255];
  }
  table->sum = (int16_t)total;
}

#if defined(PICO_ON_DEVICE) && defined(__ARM_ARCH_6M__) && defined(__GNUC__)
/* Word loads are only valid for aligned plane bytes. The public API also
 * accepts unaligned buffers. That uncommon scalar fallback stays in Flash
 * to preserve SRAM for the shared LUT, APPs and inference workspace. */
#define LUT8_SCALAR_NAME mk61ai_dot_lut8_q4_a8_32_unaligned
#define LUT8_SCALAR_LINKAGE static __attribute__((used))
#define LUT8_SCALAR_RAM(name) name
#else
#define LUT8_SCALAR_NAME mk61ai_dot_lut8_q4_a8_32
#define LUT8_SCALAR_LINKAGE
#define LUT8_SCALAR_RAM(name) LUT8_RAM(name)
#endif
LUT8_SCALAR_LINKAGE LUT8_OPT int32_t LUT8_SCALAR_RAM(LUT8_SCALAR_NAME)(const uint8_t planes[16],
                                const mk61ai_lut8x32 *table) {
  int32_t p0 = 0, p1 = 0, p2 = 0, p3 = 0;
  for (unsigned g = 0; g < 4; ++g) {
    const int16_t *t = table->subset[g];
    p0 += t[planes[g]];
    p1 += t[planes[4 + g]];
    p2 += t[planes[8 + g]];
    p3 += t[planes[12 + g]];
  }
  return p0 + 2 * p1 + 4 * p2 + 8 * p3 - 8 * (int32_t)table->sum;
}
#undef LUT8_SCALAR_NAME
#undef LUT8_SCALAR_LINKAGE
#undef LUT8_SCALAR_RAM

#if defined(PICO_ON_DEVICE) && defined(__ARM_ARCH_6M__) && defined(__GNUC__)
_Static_assert(sizeof(mk61ai_lut8x32)==2050,"Packed LUT8 layout");
/* Four index bytes per word, exact signed int16 lookups, reverse Horner
 * combination of planes. Same weight/table format and integer dot result.
 * No SIO state, scratch allocation or change to FP32 reduction order. */
__asm__(
  ".pushsection .time_critical.mk61ai_dot_lut8_q4_a8_32,\"ax\",%progbits\n"
  ".syntax unified\n.thumb\n.balign 4\n"
  ".global mk61ai_dot_lut8_q4_a8_32\n"
  ".type mk61ai_dot_lut8_q4_a8_32,%function\n.thumb_func\n"
  "mk61ai_dot_lut8_q4_a8_32:\n"
  "movs r2,#3\n"
  "tst r0,r2\n"
  "bne 2f\n"
  "push {r4,r5,r6,r7,lr}\n"
  "mov r12,r8\n"
  "movs r6,#128\nlsls r6,r6,#2\n"
  "adds r2,r1,r6\nadds r3,r2,r6\nadds r4,r3,r6\n"
  "movs r7,#255\nlsls r7,r7,#1\n"
  ".macro MK61_LUT8_PLANE offset,first=0\n"
  "ldr r5,[r0,#\\offset]\n"
  "lsls r6,r5,#1\nands r6,r7\nldrsh r6,[r1,r6]\nmov r8,r6\n"
  "lsrs r6,r5,#7\nands r6,r7\nldrsh r6,[r2,r6]\nadd r8,r6\n"
  "lsrs r6,r5,#15\nands r6,r7\nldrsh r6,[r3,r6]\nadd r8,r6\n"
  "lsrs r6,r5,#23\nands r6,r7\nldrsh r6,[r4,r6]\nadd r8,r6\n"
  ".if \\first\nmov lr,r8\n"
  ".else\nadd lr,lr\nadd lr,r8\n.endif\n.endm\n"
  "MK61_LUT8_PLANE 12,1\nMK61_LUT8_PLANE 8\n"
  "MK61_LUT8_PLANE 4\nMK61_LUT8_PLANE 0\n"
  "movs r5,#128\nlsls r5,r5,#4\nldrsh r1,[r1,r5]\nlsls r1,r1,#3\n"
  "mov r0,lr\nsubs r0,r0,r1\nmov r8,r12\n"
  "pop {r4,r5,r6,r7,pc}\n"
  "2: ldr r2,=mk61ai_dot_lut8_q4_a8_32_unaligned\nbx r2\n"
  ".ltorg\n.purgem MK61_LUT8_PLANE\n"
  ".size mk61ai_dot_lut8_q4_a8_32,.-mk61ai_dot_lut8_q4_a8_32\n"
  ".popsection\n");
#endif

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
PACK_COLD void mk61ai_pack_q4_planes32(const uint8_t codes[16], uint8_t planes[16]) {
  pack_planes(codes, planes, 4);
}
