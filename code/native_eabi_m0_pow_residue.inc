// Recover the sign of a bounded integer difference from its low bits.
#pragma once
#include "native_eabi_m0_pow_stream.inc"

#if defined(__arm__) || defined(__thumb__)
#define M0_POW_RESIDUE __attribute__((noinline,cold,section(".m0_pow_stream_extension")))
#else
#define M0_POW_RESIDUE
#endif

namespace m0_pow_residue {
namespace {
using m0_pow_stream::Dyadic;
using m0_pow_stream::Index;
using m0_pow_stream::Progress;
using m0_pow_stream::U;
using m0_pow_stream::Word;
using m0_pow_stream::signed_less;
using m0_pow_stream::word_bits;
constexpr unsigned MaximumWords = 3072;
constexpr unsigned MaximumBits = 16*MaximumWords;
constexpr U Infinity = UINT64_C(0x7ff0000000000000);

struct Residue {
    Word* data;
    unsigned used;
};

static void replace(Residue& value, Word*& work, unsigned used) {
    // Every retained power has an odd coefficient, so the low word is nonzero.
    while (used > 1 && !work[used-1])
        --used;
    Word* previous = value.data;
    value = {work, used};
    work = previous;
}

// A square needs a single copy of each off-diagonal term. Only the
// low columns that can contribute to the residue are computed.
M0_POW_RESIDUE static void square(Residue& value, Word*& work, unsigned limit, Progress progress) {
    const unsigned used = value.used;
    const unsigned length = 2*used < limit ? 2*used : limit;
    uint64_t carry = 0;
    for (unsigned i = 0; i < length; ++i) {
        if (!(i & 31) && progress)
            progress();
        const unsigned first = i >= used ? i+1-used : 0;
        const unsigned end = (i+1)/2;
        uint64_t sum = first < end ? 2*m0_pow_stream::diagonal_sum(
            value.data+first, value.data+end, value.data+(i-first+1)) : 0;
        if (!(i & 1))
            sum += uint32_t(value.data[i/2])*value.data[i/2];
        sum += carry;
        work[i] = Word(sum);
        carry = sum >> 16;
    }
    replace(value, work, length);
}

M0_POW_RESIDUE static void multiply(Residue& value, Residue other, Word*& work,
                                    unsigned limit, Progress progress) {
    unsigned length = value.used + other.used;
    if (length > limit)
        length = limit;
    for (unsigned i = 0; i < length; ++i)
        work[i] = 0;
    for (unsigned j = 0; j < other.used && j < length; ++j) {
        if (!(j & 15) && progress)
            progress();
        const uint32_t digit = other.data[j];
        const unsigned count = value.used < length-j ? value.used : length-j;
        uint32_t carry = 0;
        for (unsigned i = 0; i < count; ++i) {
            const uint32_t sum = uint32_t(value.data[i])*digit+work[i+j]+carry;
            work[i+j] = Word(sum);
            carry = sum >> 16;
        }
        if (j+count < length)
            work[j+count] = Word(carry);
    }
    replace(value, work, length);
}

M0_POW_RESIDUE static void power(Residue& value, U coefficient, U exponent, unsigned squarings,
                                 Word*& work, unsigned limit, Progress progress) {
    Word base[4];
    unsigned used = (word_bits(coefficient)+15)/16;
    if (used > limit)
        used = limit;
    value.used = used;
    for (unsigned i = 0; i < used; ++i)
        value.data[i] = base[i] = Word(coefficient>>(16*i));
    if (coefficient == 1)
        return;
    const Residue factor{base, used};
    for (U bit = (U(1) << (word_bits(exponent)-1)) >> 1; bit; bit >>= 1) {
        square(value, work, limit, progress);
        if (exponent & bit)
            multiply(value, factor, work, limit, progress);
    }
    for (unsigned i = 0; i < squarings; ++i)
        square(value, work, limit, progress);
}

static unsigned value_at(Residue value, unsigned i) {
    return i < value.used ? value.data[i] : 0;
}

M0_POW_RESIDUE static unsigned shifted_word(Residue value, unsigned i, unsigned shift) {
    const unsigned skip = shift/16, bit = shift%16;
    if (i < skip)
        return 0;
    i -= skip;
    const unsigned low = value_at(value, i) << bit;
    const unsigned high = i ? value_at(value, i-1) >> (16-bit) : 0;
    return Word(low | high);
}

static Index power_width(U coefficient, Index exponent) {
    return coefficient == 1 ? Index(0) : Index(word_bits(coefficient))*exponent;
}

M0_POW_RESIDUE static int modulo_side(Dyadic x, U p, Dyadic m, unsigned k, bool inverse,
                                      unsigned x_shift, unsigned m_shift, unsigned width,
                                      int tie, Progress progress) {
    Word a[MaximumWords], b[MaximumWords], scratch[MaximumWords];
    Residue left{a, 0}, right{b, 0};
    Word* work = scratch;
    const unsigned limit = (width+15)/16;
    if (x_shift < width)
        power(left, x.odd, p, 0, work, limit, progress);
    if (m_shift < width)
        power(right, m.odd, 1, k, work, limit, progress);
    if (inverse) {
        // The aligned 1 becomes 2^s and is zero modulo 2^width.
        multiply(left, right, work, limit, progress);
        right.used = 0;
    }

    uint32_t borrow = 0;
    unsigned nonzero = 0;
    Word digit = 0;
    for (unsigned i = 0; i < limit; ++i) {
        const uint32_t difference = shifted_word(left, i, x_shift)-
                                    shifted_word(right, i, m_shift)-borrow;
        borrow = difference >> 31;
        if (i+1 < limit)
            nonzero |= Word(difference);
        digit = Word(difference);
    }
    const unsigned sign_bit = 1U << ((width-1)%16);
    if (!(nonzero | (digit & (2*sign_bit-1))))
        return tie;
    return bool(digit & sign_bit) != inverse ? -1 : 1;
}

// Only call after establishing |y*log(x)-log(m)| < 2^-gap.
// Return zero if the bound does not fit in the residue buffers.
M0_POW_RESIDUE static int side(U xb, U yb, U lower, unsigned gap, Progress progress) {
    const U magnitude = yb & m0_pow_stream::AbsMask;
    if (!xb || xb >= Infinity || lower >= Infinity || magnitude < UINT64_C(0x3bf0000000000000) ||
        magnitude >= UINT64_C(0x43e0000000000000))
        return 0;
    const Dyadic x = m0_pow_stream::decode(xb);
    const Dyadic e = m0_pow_stream::decode(magnitude);
    Dyadic m;
    if (!m0_pow_exact::midpoint(lower, lower+1, m.odd, m.exponent))
        return 0;

    const U p = e.exponent >= 0 ? e.odd << unsigned(e.exponent) : e.odd;
    const unsigned k = e.exponent < 0 ? unsigned(-e.exponent) : 0;
    if (gap < k+2)
        return 0;
    const bool inverse = bool(yb >> 63);
    const int tie = lower & 1 ? 1 : -1;
    const Index xe = Index(x.exponent)*p, me = Index(m.exponent)<<k;
    Index bound, x_shift = 0, m_shift = 0;
    if (inverse) {
        const Index scale = xe+me;
        if (!signed_less(scale, 0))
            return !scale && x.odd == 1 && m.odd == 1 ? tie : -1;
        bound = -scale;
    } else {
        if (signed_less(xe, me))
            m_shift = me-xe;
        else
            x_shift = xe-me;
        const Index x_width = power_width(x.odd, p) + x_shift;
        const Index m_width = power_width(m.odd, Index(1)<<k) + m_shift;
        bound = x_width < m_width ? x_width : m_width;
    }
    // After aligning the powers, one magnitude is at most
    // 2^bound. Their log ratio has magnitude below 2^(k-gap). Thus
    // |A-B| < 2^(bound+1+k-gap), using |exp(t)-1| < 2*|t|.
    bound += 2+k;
    if (bound <= Index(gap)+1)
        return tie;
    if (bound > Index(gap)+MaximumBits)
        return 0;
    const unsigned width = unsigned(bound-gap);
    return modulo_side(x, p, m, k, inverse,
                       x_shift < width ? unsigned(x_shift) : width,
                       m_shift < width ? unsigned(m_shift) : width, width, tie, progress);
}
}
}
#undef M0_POW_RESIDUE
