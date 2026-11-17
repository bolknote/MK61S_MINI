// Compare full integer powers without allocating their full coefficients.
#pragma once
#include "native_eabi_m0_pow_exact.inc"
#include "native_eabi_m0_uint128.hpp"

#if defined(__arm__) || defined(__thumb__)
#define MK61_POW_STREAM __attribute__((noinline,cold,optimize("no-jump-tables"),section(".m0_pow_stream_extension")))
#else
#define MK61_POW_STREAM
#endif

namespace m0_pow_stream {
namespace {
using Index = mk61_u128;
using Word = uint16_t;
using NodeId = uint8_t;
using U = uint64_t;
constexpr unsigned RadixBits = 16;
constexpr unsigned NodeCount = 224;
constexpr unsigned MaximumDepth = 125;
constexpr unsigned MaterializedWords = 1792;
constexpr unsigned CacheSize = 8;
constexpr U AbsMask = UINT64_C(0x7fffffffffffffff);

using Progress = void (*)();

// Includes the incoming carry. At most (54 * 2^115 + 15)/16 terms in a
// column have two 16-bit factors. The accumulator fits well below 160 bits.
struct Accumulator {
    Index low;
    uint32_t high;

    static void add(Index& low, uint32_t& high, uint32_t value) {
        const auto before = low.low;
        low.low += value;
        if (low.low < before && ++low.high == 0)
            ++high;
    }
    static Word take(Index& low, uint32_t& high) {
        const Word digit = Word(low.low);
        const auto high_word = low.high;
        low.low = (low.low >> RadixBits) | (high_word << (64 - RadixBits));
        low.high = (high_word >> RadixBits) | (uint64_t(high) << (64 - RadixBits));
        high >>= RadixBits;
        return digit;
    }
};

struct Node {
    NodeId left, right;
};

struct CacheEntry {
    Index column;
    Word word;
    NodeId node = 0; // A cached product always has a nonzero node number.
};

struct Diagonal {
    Index first, end;
};

enum class State : uint8_t { begin, left, right, accumulate };

struct Frame {
    Index current, first, carry_low;
    uint32_t carry_high;
    Word left_word;
    NodeId node;
    State state;
};
static_assert(sizeof(Frame) <= 56, "Bound the explicit multiplication stack");

struct Operand {
    Word word[MaterializedWords];
    unsigned start = 0;
    NodeId node = 0;
};

struct Retained {
    const Word* word;
    unsigned count;
};

unsigned word_bits(U value) {
    unsigned bits = 0;
    for (; value; value >>= 1)
        ++bits;
    return bits;
}

Index words(Index bits) {
    return (bits + RadixBits - 1) >> 4;
}

class Products {
public:
    Products(U a, U b, Progress progress)
        : coefficients{a, b}, progress(progress) {
        bit_limits[0] = word_bits(a);
        bit_limits[1] = word_bits(b);
        for (unsigned j = 0; j < 2; ++j)
            for (unsigned i = 0; i < 4; ++i)
                literals[j][i] = Word(coefficients[j] >> (i*RadixBits));
    }

    void tick() {
        if (++steps % 1024 == 0 && progress)
            progress();
    }

    MK61_POW_STREAM NodeId multiply(NodeId left, NodeId right, Operand* store = nullptr) {
        if (left < 2 && coefficients[left] == 1)
            return right;
        if (right < 2 && coefficients[right] == 1)
            return left;
        const NodeId id = NodeId(next_node++);
        bit_limits[id] = bit_limits[left] + bit_limits[right];
        nodes[id] = {left, right};
        if (store)
            materialize(id, *store);
        return id;
    }

    NodeId power(NodeId factor, U exponent) {
        NodeId result = factor;
        U leading = UINT64_C(1) << (word_bits(exponent)-1);
        while (leading >>= 1) {
            result = multiply(result, result, &operands[factor]);
            if (exponent & leading)
                result = multiply(result, factor, &operands[factor]);
        }
        return result;
    }

    NodeId power_of_two(NodeId factor, unsigned squarings) {
        for (unsigned i = 0; i < squarings; ++i)
            factor = multiply(factor, factor, &operands[1]);
        return factor;
    }

    Index bit_limit(NodeId node) const { return bit_limits[node]; }

    Word next(NodeId node, Index at, Accumulator& carry) {
        Word value;
        return retained(node, at, value) ? value : column(node, at, carry);
    }

private:
    U coefficients[2];
    Word literals[2][4];
    Index bit_limits[NodeCount];
    Node nodes[NodeCount];
    Operand operands[2];
    CacheEntry cache[CacheSize];
    unsigned next_node = 2, steps = 0;
    Progress progress;

    Retained retained(NodeId node) const {
        if (node < 2)
            return {literals[node], unsigned(words(bit_limits[node]))};
        for (const auto& operand : operands) {
            if (operand.node == node)
                return {operand.word + operand.start, unsigned(words(bit_limits[node]))};
        }
        return {nullptr, 0};
    }

    bool retained(NodeId node, Index at, Word& value) const {
        const auto view = retained(node);
        if (view.word) {
            value = view.word[unsigned(at)];
            return true;
        }
        return false;
    }

    MK61_POW_STREAM void materialize(NodeId id, Operand& storage) {
        const Node& product = nodes[id];
        const NodeId previous = product.left; // The right factors are the base or the left factor.
        const Index left = words(bit_limits[previous]);
        const Index right = words(bit_limits[product.right]);
        if (left+right > MaterializedWords || (previous >= 2 && storage.node != previous))
            return;

        // Right-align the old operand before writing the output from low to
        // high. At output column i, any word overwritten there was last read
        // at or before column i-1. A square shares the same retained input.
        if (previous >= 2) {
            const unsigned start = unsigned(right);
            for (unsigned j = unsigned(left); j--;)
                storage.word[start+j] = storage.word[j];
            storage.start = start;
        }
        Accumulator carry{};
        const unsigned length = unsigned(words(bit_limits[id]));
        for (unsigned i = 0; i < length; ++i)
            storage.word[i] = column(id, i, carry);
        storage.node = id;
        storage.start = 0;
    }

    Index first_term(const Node& node, Index at) const {
        const Index right_length = words(bit_limits[node.right]);
        const Index after = at + 1;
        return after > right_length ? after - right_length : Index(0);
    }

    Diagonal diagonal(const Node& node, Index at) const {
        const Index left_length = words(bit_limits[node.left]);
        const Index after = at + 1;
        Index end = left_length < after ? left_length : after;
        if (node.left == node.right && end > (at >> 1) + 1)
            end = (at >> 1) + 1;
        return {first_term(node, at), end};
    }

    // Its remaining high bits are the incoming carry for the next diagonal.
    MK61_POW_STREAM Word column(NodeId id, Index at, Accumulator& carry) {
        tick();
        const Node& node = nodes[id];
        const auto a = retained(node.left);
        const auto b = retained(node.right);
        if (a.word && b.word)
            return retained_column(a, b, unsigned(at), carry);
        auto [first, end] = diagonal(node, at);
        for (Index reverse = at - first; first < end; ++first, --reverse) {
            tick();
            const uint32_t product = uint32_t(digit(node.left, first)) *
                                     digit(node.right, reverse);
            accumulate(carry.low, carry.high, product, node.left == node.right && first != reverse);
        }
        return Accumulator::take(carry.low, carry.high);
    }

    MK61_POW_STREAM Word retained_column(Retained a, Retained b, unsigned at, Accumulator& carry) {
        const bool square = a.word == b.word;
        const unsigned begin = at >= b.count ? at+1-b.count : 0;
        unsigned end = at < a.count ? at+1 : a.count;
        if (square && end > at/2+1)
            end = at/2+1;

        // The 1,792-word operands have fewer than 2^11 terms per diagonal.
        // The carry and the diagonal sum fit in 43 bits.
        uint64_t sum = carry.low.low;
        for (unsigned i = begin; i < end; ++i) {
            tick();
            const uint32_t term = uint32_t(a.word[i])*b.word[at-i];
            sum += term;
            if (square && i != at-i)
                sum += term;
        }
        carry.low.low = sum >> RadixBits;
        return Word(sum);
    }

    static void accumulate(Index& low, uint32_t& high, uint32_t product, bool twice) {
        Accumulator::add(low, high, product);
        if (twice)
            Accumulator::add(low, high, product);
    }

    static unsigned cache_slot(NodeId id, Index at) {
        return unsigned((at.low ^ (at.low >> 7) ^ at.high ^ (unsigned(id)*97U))) &
               (CacheSize-1);
    }

    bool lookup(NodeId id, Index at, Word& value) const {
        if (retained(id, at, value))
            return true;
        const CacheEntry& previous = cache[cache_slot(id, at)];
        if (previous.node != id || previous.column != at)
            return false;
        value = previous.word;
        return true;
    }

    Word digit(NodeId id, Index at) {
        Word value;
        return lookup(id, at, value) ? value : recompute(id, at);
    }

    // An uncached child restarts at column zero. The parent resumes with
    // the exact requested digit. Each frame descends to a smaller node.
    MK61_POW_STREAM Word recompute(NodeId id, Index at) {
        Frame frames[MaximumDepth];
        auto* frame = frames;
        *frame = {{}, {}, {}, {}, 0, id, State::begin};
        Word value = 0;
        for (;;) {
            tick();
            auto& f = *frame;
            const Node& node = nodes[f.node];
            switch (f.state) {
            case State::begin:
                f.first = first_term(node, f.current);
                f.state = State::left;
                break;
            case State::left:
                if (f.first > f.current || f.first >= words(bit_limits[node.left]) ||
                    (node.left == node.right && f.first > (f.current >> 1))) {
                    value = Accumulator::take(f.carry_low, f.carry_high);
                    Index requested = at;
                    if (frame != frames) {
                        const auto& parent = frame[-1];
                        requested = parent.state == State::right ? parent.first :
                                    parent.current-parent.first;
                    }
                    if (f.current == requested) {
                        cache[cache_slot(f.node, requested)] = {requested, value, f.node};
                        if (frame == frames)
                            return value;
                        --frame;
                    } else {
                        ++f.current;
                        f.state = State::begin;
                    }
                } else {
                    f.state = State::right;
                    if (!lookup(node.left, f.first, value))
                        *++frame = {{}, {}, {}, {}, 0, node.left, State::begin};
                }
                break;
            case State::right: {
                f.left_word = value;
                f.state = State::accumulate;
                const Index child_at = f.current - f.first;
                if (!lookup(node.right, child_at, value))
                    *++frame = {{}, {}, {}, {}, 0, node.right, State::begin};
                break;
            }
            case State::accumulate:
                accumulate(f.carry_low, f.carry_high, uint32_t(f.left_word)*value,
                           node.left == node.right && f.first != f.current-f.first);
                ++f.first;
                f.state = State::left;
                break;
            }
        }
    }
};

struct Shifted {
    Index first, after;
    unsigned shift;
    NodeId node;
    Word pending = 0;
    Accumulator carry{};

    Shifted(Index shift_bits, NodeId node, Index bits)
        : first(shift_bits >> 4), after(first + words(bits)),
          shift(unsigned(shift_bits.low) & (RadixBits-1)), node(node) {}

    Word next(Products& products, Index col) {
        const Word raw = col >= first && col < after ? products.next(node, col-first, carry) : 0;
        const Word value = Word((uint32_t(raw) << shift) | pending);
        pending = Word(raw >> (RadixBits-shift));
        return value;
    }
};

struct Dyadic {
    U odd;
    int exponent;
};

Dyadic decode(U bits) {
    Dyadic value;
    m0_pow_exact::decode(bits, value.odd, value.exponent);
    while (!(value.odd & 1)) {
        value.odd >>= 1;
        ++value.exponent;
    }
    return value;
}

bool signed_less(Index a, Index b) {
    constexpr Index sign = Index(1) << 127;
    return (a ^ sign) < (b ^ sign);
}

MK61_POW_STREAM int compare(Dyadic x, U p, unsigned k, bool inverse,
                            Dyadic midpoint, Progress progress) {
    Index left_scale = Index(x.exponent) * p;
    Index right_scale = Index(midpoint.exponent) << k;
    const unsigned left_bits = word_bits(x.odd);
    const unsigned right_bits = word_bits(midpoint.odd);
    Index left_low = Index(left_bits-1)*p + 1;
    Index left_high = x.odd == 1 ? Index(1) : Index(left_bits)*p;
    Index right_low = (Index(right_bits-1) << k) + 1;
    Index right_high = midpoint.odd == 1 ? Index(1) : Index(right_bits) << k;
    if (inverse) {
        left_scale += right_scale;
        right_scale = 0;
        left_low += right_low-1;
        left_high += right_high;
        right_low = right_high = 1;
    }
    if (signed_less(left_scale+left_high, right_scale+right_low))
        return inverse ? 1 : -1;
    if (signed_less(right_scale+right_high, left_scale+left_low))
        return inverse ? -1 : 1;
    if (x.odd == 1 && midpoint.odd == 1) {
        if (left_scale == right_scale)
            return 0;
        return signed_less(left_scale, right_scale) != inverse ? -1 : 1;
    }

    if (progress)
        progress();
    Products products(x.odd, midpoint.odd, progress);
    NodeId left = products.power(0, p);
    const NodeId right = products.power_of_two(1, k);
    if (inverse)
        left = products.multiply(left, right);
    const Index common = signed_less(left_scale, right_scale) ? left_scale : right_scale;
    Shifted a(left_scale-common, left, products.bit_limit(left));
    Shifted b(right_scale-common, right, products.bit_limit(right));

    // The last disagreement in a least-significant-first scan is the most
    // significant disagreement. Scanning forward consumes each root once.
    const Index b_after = inverse ? words(Index(1)-common) : b.after + (b.shift != 0);
    const Index a_after = a.after + (a.shift != 0);
    const Index end = a_after > b_after ? a_after : b_after;
    const Index one_column = (-common) >> 4;
    const Word one = Word(1U << (unsigned((-common).low) & (RadixBits-1)));
    int order = 0;
    for (Index i = 0; i < end; ++i) {
        products.tick();
        const Word av = a.next(products, i);
        const Word bv = inverse ? (i == one_column ? one : Word(0)) : b.next(products, i);
        if (av != bv)
            order = av < bv ? -1 : 1;
    }
    return inverse ? -order : order;
}

// x and y are finite, x > 0, and y is in the active exponent range.
MK61_POW_STREAM int side(U x, U y, U lower, Progress progress) {
    const Dyadic base = decode(x);
    const Dyadic exponent = decode(y & AbsMask);
    Dyadic midpoint;
    m0_pow_exact::midpoint(lower, lower + 1, midpoint.odd, midpoint.exponent);
    const U p = exponent.exponent >= 0 ? exponent.odd << unsigned(exponent.exponent) : exponent.odd;
    const unsigned k = exponent.exponent < 0 ? unsigned(-exponent.exponent) : 0;
    const int relation = compare(base, p, k, bool(y >> 63), midpoint, progress);
    return relation ? relation : (lower & 1 ? 1 : -1);
}

} // namespace
} // namespace m0_pow_stream
#undef MK61_POW_STREAM
