#include "mk61_ai_linear.hpp"
#include "mk61_ai_kernels.h"
#include "mk61_ai_half_product.hpp"
#include <cmath>
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "pico.h"
#define MK61_AI_RAM(name) __not_in_flash_func(name)
#else
#define MK61_AI_RAM(name) name
#endif
#if defined(__GNUC__) || defined(__clang__)
#define MK61_AI_INLINE inline __attribute__((always_inline))
#else
#define MK61_AI_INLINE inline
#endif

namespace mk61ai {
namespace {
MK61_AI_INLINE float half(std::uint16_t h) {
  const unsigned sign = h >> 15, exponent = (h >> 10) & 31, mantissa = h & 1023;
  if (exponent == 31)
    return mantissa ? NAN : sign ? -INFINITY : INFINITY;
  float value;
  if (exponent) {
    const std::uint32_t bits = ((exponent + 112) << 23) | (mantissa << 13);
    std::memcpy(&value, &bits, 4);
  } else
    value = float(mantissa) * 0x1p-24f;
  return sign ? -value : value;
}
MK61_AI_INLINE unsigned unpack(const std::uint8_t *p, unsigned j,
                               unsigned bits, bool planes) {
  if (!planes) {
    const unsigned at = j * bits, shift = at & 7;
    unsigned u = p[at / 8] >> shift;
    if (shift + bits > 8)
      u |= unsigned(p[at / 8 + 1]) << (8 - shift);
    return u & ((1U << bits) - 1);
  }
  unsigned u = 0;
  const unsigned quartet = (j % 32) / 4, lane = j % 4;
  for (unsigned b = 0; b < bits; ++b)
    u |= ((p[j / 32 * bits * 4 + b * 4 + quartet / 2] >>
           (4 * (quartet % 2) + lane)) & 1U) << b;
  return u;
}

// Keep the FP32 addition order of the original per-plane implementation.
// In particular, interleaving bit planes would change cancellation/rounding.
MK61_AI_INLINE float plane_float(const float *t, const std::uint8_t *p) {
  float sum = 0;
  sum += t[(p[0] & 15)];
  sum += t[16 + (p[0] >> 4)];
  sum += t[32 + (p[1] & 15)];
  sum += t[48 + (p[1] >> 4)];
  sum += t[64 + (p[2] & 15)];
  sum += t[80 + (p[2] >> 4)];
  sum += t[96 + (p[3] & 15)];
  sum += t[112 + (p[3] >> 4)];
  return sum;
}
MK61_AI_INLINE std::int32_t plane_integer(const std::int16_t *t,
                                         const std::uint8_t *p) {
  return t[p[0] & 15] + t[16 + (p[0] >> 4)] +
         t[32 + (p[1] & 15)] + t[48 + (p[1] >> 4)] +
         t[64 + (p[2] & 15)] + t[80 + (p[2] >> 4)] +
         t[96 + (p[3] & 15)] + t[112 + (p[3] >> 4)];
}
MK61_AI_INLINE std::int32_t nibble_dot(const std::uint8_t *p,
                                      const std::int8_t *x) {
  std::int32_t sum = 0;
  for (unsigned i = 0; i < 16; i += 4) {
    sum += int(p[i] & 15) * int(x[2 * i]);
    sum += int(p[i] >> 4) * int(x[2 * i + 1]);
    sum += int(p[i + 1] & 15) * int(x[2 * i + 2]);
    sum += int(p[i + 1] >> 4) * int(x[2 * i + 3]);
    sum += int(p[i + 2] & 15) * int(x[2 * i + 4]);
    sum += int(p[i + 2] >> 4) * int(x[2 * i + 5]);
    sum += int(p[i + 3] & 15) * int(x[2 * i + 6]);
    sum += int(p[i + 3] >> 4) * int(x[2 * i + 7]);
  }
  return sum;
}
template <Arithmetic Mode>
MK61_AI_INLINE void fast_q4(LinearBatch &b) {
  for (unsigned r = 0; r < b.rows; ++r) {
    const auto *weights = b.weights + r * b.columns / 2;
    const auto *scales = b.scales + r * b.columns / 16;
    float value = 0;
    for (unsigned g = 0; g < b.columns / 32; ++g) {
      const auto scale_bits=std::uint16_t(std::uint16_t(scales[2*g]) |
                               (std::uint16_t(scales[2*g+1])<<8));
      const auto *p = weights + 16 * g;
      if constexpr (Mode == Arithmetic::LUT_FLOAT32) {
        const float scale=half(scale_bits);
        const float *t = b.lookup + g * 128;
        float weighted = 0;
        weighted += plane_float(t, p);
        weighted += plane_float(t, p + 4) * 2.0f;
        weighted += plane_float(t, p + 8) * 4.0f;
        weighted += plane_float(t, p + 12) * 8.0f;
        value += (weighted - 8.0f * b.input_sums[g]) * scale;
      } else if constexpr (Mode == Arithmetic::LUT_INT8) {
        const float scale=half(scale_bits);
        const auto *t = reinterpret_cast<const std::int16_t *>(b.lookup) + g * 128;
        const std::int32_t sum = plane_integer(t, p) +
            2 * plane_integer(t, p + 4) + 4 * plane_integer(t, p + 8) +
            8 * plane_integer(t, p + 12) - 8 * int(b.input_sums[g]);
        value += float(sum) * scale * b.activation_scales[g];
      } else {
        const auto *x = b.quant + 32 * g;
        std::int32_t sum = 0;
        if (!(b.grid & 256)) {
          sum = nibble_dot(p, x);
          // sum((u-8)*x) = sum(u*x)-8*sum(x). The correction is
          // shared by every output row and stays entirely in int32.
          std::int32_t activation_sum=0;
          if(b.quant_sums) activation_sum=b.quant_sums[g];
          else for(unsigned j=0;j<32;++j) activation_sum+=x[j];
          sum-=8*activation_sum;
        } else {
          for (unsigned quartet = 0; quartet < 8; ++quartet) {
            const unsigned shift = (quartet & 1) * 4, i = quartet / 2;
            const unsigned a = p[i] >> shift, c = p[4 + i] >> shift;
            const unsigned d = p[8 + i] >> shift, e = p[12 + i] >> shift;
            for (unsigned lane = 0; lane < 4; ++lane) {
              const int u = int(((a >> lane) & 1) | (((c >> lane) & 1) << 1) |
                                (((d >> lane) & 1) << 2) | (((e >> lane) & 1) << 3));
              sum += (u - 8) * int(x[quartet * 4 + lane]);
            }
          }
        }
        value += half_scaled_q4_dot(sum,scale_bits) * b.activation_scales[g];
      }
    }
    if (!std::isfinite(value)) {
      b.status = ModelStatus::NUMERIC;
      return;
    }
    b.output[r] = value;
  }
}

void generic(LinearBatch &b) {
  const bool integer = b.arithmetic == Arithmetic::INT8 ||
                       b.arithmetic == Arithmetic::LUT_INT8;
  const bool tables = b.arithmetic == Arithmetic::LUT_INT8 ||
                      b.arithmetic == Arithmetic::LUT_FLOAT32;
  const bool planes = (b.grid & 256) != 0, symmetric = (b.grid & 1) != 0;
  const unsigned mask = (1U << b.bits) - 1;
  for (unsigned r = 0; r < b.rows; ++r) {
    const auto *weights = b.weights + r * b.columns * b.bits / 8;
    const auto *scales = b.scales + r * b.columns / 16;
    float value = 0;
    for (unsigned g = 0; g < b.columns / 32; ++g) {
      float scale = half(std::uint16_t(scales[2 * g]) |
                          (std::uint16_t(scales[2 * g + 1]) << 8));
      if (b.arithmetic == Arithmetic::FLOAT32) {
        for (unsigned j = 0; j < 32; ++j) {
          const unsigned u = unpack(weights, g * 32 + j, b.bits, planes);
          const float coefficient = symmetric ? float(u) * (2.0f / float(mask)) - 1.0f
                                               : float(int(u) - 8);
          value += b.input[g * 32 + j] * (coefficient * scale);
        }
      } else if (!tables) {
        std::int32_t sum = 0;
        for (unsigned j = 0; j < 32; ++j) {
          const int u = int(unpack(weights, g * 32 + j, b.bits, planes));
          sum += (symmetric ? 2 * u - int(mask) : u - 8) * int(b.quant[g * 32 + j]);
        }
        if (symmetric) scale /= float(mask);
        value += float(sum) * scale * b.activation_scales[g];
      } else {
        std::uint8_t converted[16]{};
        const auto *p = weights + g * b.bits * 4;
        if (!planes) {
          for (unsigned bit = 0; bit < b.bits; ++bit)
            for (unsigned quartet = 0; quartet < 8; ++quartet) {
              unsigned index = 0;
              for (unsigned lane = 0; lane < 4; ++lane)
                index |= ((unpack(p, quartet * 4 + lane, b.bits, false) >> bit) & 1) << lane;
              converted[bit * 4 + quartet / 2] |= std::uint8_t(index << (4 * (quartet % 2)));
            }
          p = converted;
        }
        float weighted = 0;
        std::int32_t iweighted = 0;
        for (unsigned bit = 0; bit < b.bits; ++bit) {
          if (integer)
            iweighted += plane_integer(reinterpret_cast<const std::int16_t *>(b.lookup) + g * 128,
                                       p + bit * 4) * int(1U << bit);
          else
            weighted += plane_float(b.lookup + g * 128, p + bit * 4) * float(1U << bit);
        }
        if (integer) {
          const int sum = symmetric ? 2 * iweighted - int(mask) * int(b.input_sums[g])
                                    : iweighted - 8 * int(b.input_sums[g]);
          value += float(sum) * (symmetric ? scale / float(mask) : scale) * b.activation_scales[g];
        } else
          value += (symmetric ? weighted * (2.0f / float(mask)) - b.input_sums[g]
                               : weighted - 8.0f * b.input_sums[g]) * scale;
      }
    }
    if (!std::isfinite(value)) {
      b.status = ModelStatus::NUMERIC;
      return;
    }
    b.output[r] = value;
  }
}
MK61_AI_INLINE void dispatch(LinearBatch &b) {
  b.status = ModelStatus::OK;
  if (b.bits == 4 && !(b.grid & 1)) {
    if (b.arithmetic == Arithmetic::LUT_FLOAT32 && (b.grid & 256))
      return fast_q4<Arithmetic::LUT_FLOAT32>(b);
    if (b.arithmetic == Arithmetic::LUT_INT8 && (b.grid & 256))
      return fast_q4<Arithmetic::LUT_INT8>(b);
    if (b.arithmetic == Arithmetic::INT8)
      return fast_q4<Arithmetic::INT8>(b);
  }
  generic(b);
}
} // namespace
void linear_batch_flash(void *raw) { dispatch(*static_cast<LinearBatch *>(raw)); }
void MK61_AI_RAM(linear_batch_sram)(void *raw) { dispatch(*static_cast<LinearBatch *>(raw)); }
} // namespace mk61ai
