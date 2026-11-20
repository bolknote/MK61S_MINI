// Bounded exact midpoint comparison using coprime 32-bit moduli.
#pragma once
#include "native_eabi_m0_pow_residue.inc"

namespace m0_pow_coprime {
using m0_pow_stream::Dyadic;
using m0_pow_stream::Index;
using m0_pow_stream::Progress;
using m0_pow_stream::U;
using m0_pow_stream::signed_less;
constexpr unsigned MaximumModuli = 4608;
constexpr U Infinity = UINT64_C(0x7ff0000000000000);

#include "coprime_residue_table.inc"
static_assert(sizeof(ModulusGaps) == MaximumModuli);
static_assert(sizeof(PrefixInverse)/sizeof(uint32_t) == MaximumModuli);

struct Ring {
    uint32_t offset;
    uint32_t modulus() const { return 0U-offset; }

    // For high < 2**16, fold modulo 2**32-offset and subtract at most once.
    uint32_t narrow(uint32_t low, uint32_t high) const {
        const uint32_t sum = low+high*offset;
        return sum < low || sum >= modulus() ? sum+offset : sum;
    }

    uint32_t reduce(uint64_t value) const {
        const uint64_t first = uint32_t(value)+mk61_m0_wide32(uint32_t(value>>32),offset);
        return narrow(uint32_t(first),uint32_t(first>>32));
    }
    uint32_t mul(uint32_t a, uint32_t b) const { return reduce(mk61_m0_wide32(a,b)); }
    uint32_t subtract(uint32_t a, uint32_t b) const { return a-b+(a < b ? modulus() : 0U); }

    uint32_t multiply_add_short(uint32_t value, uint16_t weight, uint32_t addend) const {
        const uint32_t high = ((value>>16)*weight+(uint32_t(uint16_t(value))*weight>>16))>>16;
        const uint32_t low = value*weight;
        const uint32_t sum = low+addend;
        return narrow(sum,high+unsigned(sum<low));
    }

    uint32_t power(uint32_t base, U exponent) const {
        uint32_t value = 1;
        for (; exponent; exponent >>= 1) {
            if (exponent & 1)
                value = mul(value,base);
            if (exponent > 1)
                base = mul(base,base);
        }
        return value;
    }

    uint32_t scale(uint32_t value, U shift) const {
        return shift ? mul(value,power(2,shift)) : value;
    }
};

// Keep the inner conversion loop separate so its temporaries fit in registers.
__attribute__((noinline)) static uint32_t prefix_modulo(unsigned i, const uint32_t* digits, Ring ring) {
    uint32_t previous = 0, multiplier = 0;
    for (unsigned j = i; j; --j) {
        // Modulo m_i, m_(j-1) is the difference of the two offsets.
        multiplier += ModulusGaps[j];
        previous = ring.multiply_add_short(previous,uint16_t(multiplier),digits[j-1]);
    }
    return previous;
}

template<class Residue>
int reconstruct(unsigned count, uint32_t* digits, Residue residue, Progress progress) {
    uint32_t offset = 0, nonzero = 0;
    int order = 0;
    for (unsigned i = 0; i < count; ++i) {
        offset += ModulusGaps[i];
        const Ring ring{offset};
        const uint32_t previous = prefix_modulo(i,digits,ring);
        const uint32_t digit = ring.mul(ring.subtract(residue(i,ring),previous),PrefixInverse[i]);
        digits[i] = digit;
        nonzero |= digit;
        // All mixed-radix digits of (product-1)/2 are (m_i-1)/2.
        const uint32_t half = ring.modulus()/2;
        if (digit != half)
            order = digit < half ? 1 : -1;
        if (progress && !(i&7))
            progress();
    }
    return nonzero ? (order ? order : 1) : 0;
}

// Requires a previous enclosure proving |y*ln(x)-ln(m)| < 2**-gap.
// Return zero when the certified difference does not fit the available moduli.
static int side(U xb, U yb, U lower, unsigned gap, uint32_t* digits,
                unsigned capacity, Progress progress = nullptr) {
    const U magnitude = yb & m0_pow_stream::AbsMask;
    if (!xb || xb >= Infinity || lower >= Infinity || magnitude < UINT64_C(0x3bf0000000000000)
        || magnitude >= UINT64_C(0x43e0000000000000) || !capacity || capacity > MaximumModuli
        || !digits)
        return 0;
    const Dyadic x = m0_pow_stream::decode(xb), e = m0_pow_stream::decode(magnitude);
    Dyadic m;
    if (!m0_pow_exact::midpoint(lower,lower+1,m.odd,m.exponent))
        return 0;
    const U p = e.exponent >= 0 ? e.odd << unsigned(e.exponent) : e.odd;
    const unsigned k = e.exponent < 0 ? unsigned(-e.exponent) : 0;
    if (gap < k+2)
        return 0;
    const bool inverse = bool(yb>>63);
    const int tie = lower & 1 ? 1 : -1;
    const Index xe = Index(x.exponent)*p, me = Index(m.exponent)<<k;
    Index bound, x_shift = 0, m_shift = 0;
    if (inverse) {
        const Index scale = xe+me;
        if (!signed_less(scale,0))
            return !scale && x.odd == 1 && m.odd == 1 ? tie : -1;
        m_shift = bound = -scale;
    } else {
        if (signed_less(xe,me))
            m_shift = me-xe;
        else
            x_shift = xe-me;
        const Index a = m0_pow_residue::power_width(x.odd,p)+x_shift;
        const Index b = m0_pow_residue::power_width(m.odd,Index(1)<<k)+m_shift;
        bound = a < b ? a : b;
    }
    const Index target = bound+2+k;
    if (target <= Index(gap)+1)
        return tie;
    // Both aligned operands are below 2**(bound+1) under the gap hypothesis.
    if (target > Index(gap)+32*capacity-1 || x_shift > bound+1 || m_shift > bound+1)
        return 0;
    const unsigned width = unsigned(target-gap);
    const unsigned count = (width+32)/32;
    const auto difference = [&](unsigned, const Ring& ring) {
        uint32_t a = x.odd == 1 ? 1 : ring.power(ring.reduce(x.odd),p);
        uint32_t b = ring.reduce(m.odd);
        if (b != 1)
            for (unsigned i = 0; i < k; ++i)
                b = ring.mul(b,b);
        if (inverse) {
            a = ring.mul(a,b);
            b = 1;
        }
        return ring.subtract(ring.scale(a,U(x_shift)),ring.scale(b,U(m_shift)));
    };
    const int order = reconstruct(count,digits,difference,progress);
    return order ? (inverse ? -order : order) : tie;
}
}
