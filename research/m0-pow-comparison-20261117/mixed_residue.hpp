// Experimental bounded exact comparison. Not used by firmware.
#pragma once
#include "native_eabi_m0_pow_stream.inc"

namespace m0_pow_mixed {
using m0_pow_stream::Dyadic;
using m0_pow_stream::Index;
using m0_pow_stream::U;
using m0_pow_stream::Word;
using m0_pow_stream::word_bits;
using m0_pow_stream::signed_less;
constexpr unsigned BudgetWords = 3*3072;
constexpr U Infinity = UINT64_C(0x7ff0000000000000);

enum Mode : unsigned { automatic, binary, binary_minus, binary_plus, odd_pair, triple };
enum Modulus : unsigned { power_of_two, minus_one, plus_one };

struct Plan {
    unsigned mode, words, scratch;
    uint64_t products;
};
struct Work {
    uint64_t products = 0, columns = 0;
};
struct Number {
    Word* data;
    unsigned used;
    unsigned operator[](unsigned i) const { return i < used ? data[i] : 0; }
};

static unsigned rings(unsigned mode) {
    return mode == binary ? 1 : mode == triple ? 3 : 2;
}
static unsigned loses_bit(unsigned mode) {
    return mode == binary || mode == binary_plus ? 0 : 1;
}
static unsigned extra_word(unsigned mode) {
    return mode >= binary_plus ? 1 : 0;
}
static unsigned max_width(unsigned mode, unsigned budget) {
    const unsigned per = budget/(rings(mode)+2);
    return per > extra_word(mode) ? 16*rings(mode)*(per-extra_word(mode))-loses_bit(mode) : 0;
}

static uint64_t pair_count(unsigned n, unsigned left, unsigned right, bool square, bool truncated) {
    if (!truncated)
        return square ? uint64_t(left)*(left+1)/2 : uint64_t(left)*right;
    const unsigned first = square ? (left < (n+1)/2 ? left : (n+1)/2) : left;
    const unsigned end_full = n-right+1;
    const unsigned full = first < end_full ? first : end_full;
    const uint64_t sum_full_indices = uint64_t(full)*(full ? full-1 : 0)/2;
    const uint64_t sum_all_indices = uint64_t(first)*(first ? first-1 : 0)/2;
    return uint64_t(full)*right-(square ? sum_full_indices : 0)
        + uint64_t(first-full)*n-(square ? 2 : 1)*(sum_all_indices-sum_full_indices);
}

static unsigned bound_power(U coefficient, U p, unsigned squarings, unsigned n,
                            bool truncated, uint64_t& work) {
    if (coefficient == 1)
        return 1;
    const unsigned bits = word_bits(coefficient), capacity = n*16;
    unsigned active = bits < capacity ? bits : capacity;
    auto step = [&](bool multiply) {
        const unsigned used = (active+15)/16;
        work += pair_count(n, used, used, true, truncated);
        active = 2*active < capacity ? 2*active : capacity;
        if (multiply) {
            work += pair_count(n, (active+15)/16,
                               ((bits < capacity ? bits : capacity)+15)/16, false, truncated);
            active = active+bits < capacity ? active+bits : capacity;
        }
    };
    for (U bit = (U(1) << (word_bits(p)-1)) >> 1; bit; bit >>= 1)
        step(p & bit);
    for (unsigned i = 0; i < squarings; ++i)
        step(false);
    return (active+15)/16;
}

static uint64_t bound_modulus(Dyadic x, U p, Dyadic m, unsigned k,
                             bool inverse, unsigned n, bool truncated) {
    uint64_t work = 0;
    const unsigned a = bound_power(x.odd, p, 0, n, truncated, work);
    const unsigned b = bound_power(m.odd, 1, k, n, truncated, work);
    if (inverse)
        work += pair_count(n, a, b, false, truncated);
    return work;
}

static Plan choose(Dyadic x, U p, Dyadic m, unsigned k, bool inverse,
                   unsigned width, unsigned requested, unsigned budget) {
    Plan best{};
    for (unsigned mode = binary; mode <= triple; ++mode) {
        if ((requested && mode != requested) || width > max_width(mode, budget))
            continue;
        const unsigned count = rings(mode);
        const unsigned n = (width+loses_bit(mode)+16*count-1)/(16*count);
        const bool has_binary = mode != odd_pair;
        const unsigned odd = count-unsigned(has_binary);
        const uint64_t work = (has_binary ? bound_modulus(x,p,m,k,inverse,n,true) : 0)
                            + odd*(odd ? bound_modulus(x,p,m,k,inverse,n,false) : 0);
        const unsigned space = (count+2)*(n+extra_word(mode));
        if (!best.mode || work < best.products || (work == best.products && space < best.scratch))
            best = {mode, n, space, work};
    }
    return best;
}

static unsigned shift_mod(Index value, unsigned modulus) {
    unsigned remainder = 0;
    for (unsigned i = 0; i < 2; ++i) {
        const U part = i ? value.low : value.high;
        for (U bit = U(1) << 63; bit; bit >>= 1) {
            remainder = 2*remainder+unsigned(bool(part & bit));
            if (remainder >= modulus)
                remainder -= modulus;
        }
    }
    return remainder;
}

class Ring {
public:
    Ring(unsigned words, Modulus modulus, Work& stats)
        : n(words), modulus(modulus), stats(stats) {}

    void small(Number& out, U value) const {
        if (n < 4) {
            const U base = U(1) << (16*n);
            value %= modulus == minus_one ? base-1 : modulus == plus_one ? base+1 : base;
        } else if (n == 4 && modulus == minus_one && value == UINT64_MAX) {
            value = 0;
        }
        unsigned i = 0;
        for (; value; value >>= 16)
            out.data[i++] = Word(value);
        out.used = i;
    }

    Number copy(Number from, Word* target) const {
        for (unsigned i = 0; i < from.used; ++i)
            target[i] = from.data[i];
        return {target, from.used};
    }

    void power(Number& out, Word*& work, U coefficient, U p, unsigned squarings) const {
        Word short_words[5];
        Number base{short_words,0};
        small(base, coefficient);
        out = copy(base, out.data);
        if (coefficient == 1)
            return;
        for (U bit = (U(1) << (word_bits(p)-1)) >> 1; bit && out.used; bit >>= 1) {
            multiply(out, out, work, true);
            if (p & bit)
                multiply(out, base, work, false);
        }
        for (unsigned i = 0; i < squarings && out.used; ++i)
            multiply(out, out, work, true);
    }

    void multiply(Number& x, Number y, Word*& work, bool square) const {
        if (!x.used || !y.used) {
            x.used = 0;
            return;
        }
        // B represents -1 in the Fermat ring, including in a square.
        if (modulus == plus_one && (x.used > n || y.used > n)) {
            Number other = x.used > n ? y : x;
            Number result = negate_plus(other, work);
            work = x.data;
            x = result;
            return;
        }
        const unsigned length = x.used+y.used;
        const unsigned end_column = modulus == power_of_two && length > n ? n : length;
        uint64_t carry = 0;
        auto next = [&](unsigned column) {
            uint64_t value = carry;
            const unsigned low = column >= y.used ? column+1-y.used : 0;
            const unsigned high = column < x.used ? column+1 : x.used;
            if (square) {
                const unsigned end = (column+1)/2;
                for (unsigned i = low; i < end; ++i)
                    value += 2*uint64_t(uint32_t(x.data[i])*x.data[column-i]);
                if (low < end)
                    stats.products += end-low;
                if (!(column & 1) && column/2 < x.used) {
                    value += uint32_t(x.data[column/2])*x.data[column/2];
                    ++stats.products;
                }
            } else {
                for (unsigned i = low; i < high; ++i)
                    value += uint32_t(x.data[i])*y.data[column-i];
                if (low < high)
                    stats.products += high-low;
            }
            carry = value >> 16;
            return Word(value);
        };
        Number result = fold(work, end_column, next);
        work = x.data;
        x = result;
    }

    void shift(Number& value, Index count, Word*& work) const {
        if (!value.used || !count)
            return;
        const unsigned width = 16*n;
        if (modulus == power_of_two && count >= width) {
            value.used = 0;
            return;
        }
        unsigned shift = modulus == power_of_two ? unsigned(count)
                         : shift_mod(count, modulus == plus_one ? 2*width : width);
        const bool negate = shift >= width;
        if (negate)
            shift -= width;
        if (shift) {
            const unsigned skip = shift/16, bits = shift%16;
            unsigned length = value.used+skip+unsigned(bits != 0);
            if (modulus == power_of_two && length > n)
                length = n;
            if (modulus != power_of_two && length > 2*n)
                length = 2*n; // B is the only input with n+1 limbs.
            Number result = fold(work, length, [&](unsigned column) {
                if (column < skip)
                    return Word(0);
                const unsigned i = column-skip;
                return Word((value[i]<<bits) | (i ? value[i-1]>>(16-bits) : 0));
            });
            work = value.data;
            value = result;
        }
        if (negate) {
            Number result = negate_plus(value, work);
            work = value.data;
            value = result;
        }
    }

    Number subtract(Number x, Number y, Word* dst) const {
        const unsigned size = n+unsigned(modulus == plus_one);
        unsigned borrow = 0;
        for (unsigned i = 0; i < size; ++i) {
            const uint32_t difference = uint32_t(x[i])-y[i]-borrow;
            dst[i] = Word(difference);
            borrow = difference >> 31;
        }
        if (borrow && modulus != power_of_two) {
            unsigned carry = 0;
            for (unsigned i = 0; i < size; ++i) {
                const unsigned digit = modulus == minus_one ? 65535 : unsigned(i == 0 || i == n);
                const unsigned sum = unsigned(dst[i])+digit+carry;
                dst[i] = Word(sum);
                carry = sum >> 16;
            }
        }
        return trim(dst, size);
    }

    Number half_mod_plus(Number x) const {
        // Divide by 2 in Z/(B+1): add the odd modulus if necessary.
        const unsigned add = x[0] & 1;
        unsigned carry = 0;
        for (unsigned i = 0; i <= n; ++i) {
            const unsigned sum = x[i]+carry+add*unsigned(i == 0 || i == n);
            x.data[i] = Word(sum);
            carry = sum >> 16;
        }
        carry = 0;
        for (unsigned i = n+1; i--;) {
            const unsigned limb = x.data[i];
            x.data[i] = Word((limb>>1)|(carry<<15));
            carry = limb & 1;
        }
        return trim(x.data,n+1);
    }

    int compare_half(Number x, bool minus = false) const {
        if (x.used > n)
            return 1;
        for (unsigned i = n; i--;) {
            const unsigned test = i == n-1 ? (minus ? 32767 : 32768) : (minus ? 65535 : 0);
            if (x[i] != test)
                return x[i] < test ? -1 : 1;
        }
        return 0;
    }

private:
    unsigned n;
    Modulus modulus;
    Work& stats;

    static Number trim(Word* dst, unsigned used) {
        while (used && !dst[used-1])
            --used;
        return {dst,used};
    }

    Number negate_plus(Number x, Word* dst) const {
        if (x.used > n) {
            dst[0] = 1;
            return {dst,1};
        }
        if (!x.used)
            return {dst,0};
        unsigned carry = 2;
        for (unsigned i = 0; i < n; ++i) {
            const unsigned value = 65535-x[i]+carry;
            dst[i] = Word(value);
            carry = value >> 16;
        }
        dst[n] = Word(carry);
        return trim(dst,n+1);
    }

    template<class Next> Number fold(Word* dst, unsigned length, Next next) const {
        // Stream the ordinary product digits. Store L, then fold H
        // by L+H or L-H; no buffer for the 2w-bit product is allocated.
        const unsigned low = length < n ? length : n;
        stats.columns += length;
        for (unsigned i = 0; i < low; ++i)
            dst[i] = next(i);
        if (length < n || modulus == power_of_two)
            return trim(dst,low);
        int carry = 0;
        for (unsigned i = 0; i < n; ++i) {
            const int high = i+n < length ? next(i+n) : 0;
            const int value = int(dst[i])+carry+(modulus == minus_one ? high : -high);
            dst[i] = Word(value);
            carry = (value >= 65536)-(value < 0);
        }
        // B == +1 modulo B-1 and B == -1 modulo B+1.
        unsigned add = unsigned(modulus == minus_one ? carry : -carry);
        for (unsigned i = 0; i < n && add; ++i) {
            const unsigned sum = unsigned(dst[i])+add;
            dst[i] = Word(sum);
            add = sum >> 16;
        }
        if (modulus == plus_one) {
            dst[n] = Word(add);
            return trim(dst,n+1);
        }
        for (unsigned i = 0; i < n; ++i)
            if (dst[i] != 65535)
                return trim(dst,n);
        return {dst,0}; // B-1 is zero in the Mersenne ring.
    }
};

static Number difference(Ring ring, Dyadic x, U p, Dyadic m, unsigned k, bool inverse,
                         Index x_shift, Index m_shift, Word* scratch, unsigned stride) {
    Number left{scratch,0}, right{scratch+stride,0};
    Word* work = scratch+2*stride;
    ring.power(left,work,x.odd,p,0);
    ring.power(right,work,m.odd,1,k);
    if (inverse) {
        ring.multiply(left,right,work,false);
        ring.small(right,1);
    }
    ring.shift(left,x_shift,work);
    ring.shift(right,m_shift,work);
    return ring.subtract(left,right,left.data);
}

static int sign(Plan plan, Dyadic x, U p, Dyadic m, unsigned k, bool inverse,
                Index x_shift, Index m_shift, Word* scratch, Work& work) {
    const unsigned n = plan.words, stride = n+extra_word(plan.mode);
    Ring low(n,power_of_two,work), minus(n,minus_one,work), plus(n,plus_one,work);
    auto evaluate = [&](Ring ring) { return difference(ring,x,p,m,k,inverse,x_shift,m_shift,scratch,stride); };
    if (plan.mode == binary) {
        const Number residue = evaluate(low);
        return residue.used ? (low.compare_half(residue) < 0 ? 1 : -1) : 0;
    }
    Number store{scratch+3*stride,0}, r0{nullptr,0}, a{nullptr,0};
    if (plan.mode != odd_pair)
        r0 = low.copy(evaluate(low),store.data);
    if (plan.mode == binary_minus) {
        const Number r = evaluate(minus);
        const Number q = minus.subtract(r,r0,r.data);
        if (!(q.used || r0.used))
            return 0;
        const int high = minus.compare_half(q,true);
        return high > 0 || (!high && low.compare_half(r0) >= 0) ? -1 : 1;
    }
    if (plan.mode == binary_plus) {
        const Number r = evaluate(plus);
        const Number q = plus.subtract(r0,r,r.data);
        if (!(q.used || r0.used))
            return 0;
        const int high = plus.compare_half(q);
        return high > 0 || (!high && low.compare_half(r0) >= 0) ? -1 : 1;
    }
    if (plan.mode == triple)
        a = minus.subtract(evaluate(minus),r0,scratch+4*stride);
    else
        a = minus.copy(evaluate(minus),store.data);
    const Number odd = evaluate(plus);
    const Number b = plan.mode == triple ? plus.subtract(r0,odd,odd.data) : odd;
    const Number t = plus.half_mod_plus(plus.subtract(a,b,b.data));
    if (!(t.used || a.used || r0.used))
        return 0;
    const int high = plus.compare_half(t);
    if (high)
        return high > 0 ? -1 : 1;
    const int middle = minus.compare_half(a,true);
    return middle > 0 || (!middle && plan.mode == triple && low.compare_half(r0) >= 0) ? -1 : 1;
}

// Only call after establishing |y*ln(x)-ln(midpoint)| < 2^-gap.
static int side(U xb, U yb, U lower, unsigned gap, unsigned requested,
                Word* scratch, unsigned budget, Plan& plan, Work& work) {
    plan = {};
    work = {};
    const U magnitude = yb & m0_pow_stream::AbsMask;
    if (!xb || xb >= Infinity || lower >= Infinity || magnitude < UINT64_C(0x3bf0000000000000)
        || magnitude >= UINT64_C(0x43e0000000000000) || budget > BudgetWords
        || requested > triple || !scratch)
        return 0;
    const Dyadic x = m0_pow_stream::decode(xb), e = m0_pow_stream::decode(magnitude);
    Dyadic m;
    if (!m0_pow_exact::midpoint(lower,lower+1,m.odd,m.exponent))
        return 0;
    const U p = e.exponent >= 0 ? e.odd << unsigned(e.exponent) : e.odd;
    const unsigned k = e.exponent < 0 ? unsigned(-e.exponent) : 0;
    if (gap < k+2)
        return 0;
    const bool inverse = bool(yb >> 63);
    const int tie = lower & 1 ? 1 : -1;
    const Index xe = Index(x.exponent)*p, me = Index(m.exponent)<<k;
    Index bound, x_shift=0, m_shift=0;
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
        const Index a = (x.odd == 1 ? Index(0) : Index(word_bits(x.odd))*p)+x_shift;
        const Index b = (m.odd == 1 ? Index(0) : Index(word_bits(m.odd))<<k)+m_shift;
        bound = a < b ? a : b;
    }
    bound += 2+k;
    if (bound <= Index(gap)+1)
        return tie;
    unsigned limit = 0;
    for (unsigned mode = binary; mode <= triple; ++mode)
        if ((!requested || mode == requested) && max_width(mode,budget) > limit)
            limit = max_width(mode,budget);
    if (bound > Index(gap)+limit)
        return 0;
    plan = choose(x,p,m,k,inverse,unsigned(bound-Index(gap)),requested,budget);
    if (!plan.mode)
        return 0;
    const int order = sign(plan,x,p,m,k,inverse,x_shift,m_shift,scratch,work);
    return order ? (inverse ? -order : order) : tie;
}
}
