#include "kernels.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(mk61ai_lut32) == 258, "Unexpected LUT padding");
static unsigned checks;
static uint32_t seed = 0x61c0ffeeU;
static uint32_t random_word(void) {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return seed;
}

static void check(const int8_t weights[32], const int8_t x[32], unsigned bits) {
    const int bias = 1 << (bits - 1);
    uint8_t codes[16] = {0}, planes[16] = {0};
    int32_t expected = 0;
    mk61ai_lut32 table;
    for (unsigned i = 0; i < 32; ++i) {
        const unsigned position = i * bits;
        const unsigned code = (unsigned)(weights[i] + bias);
        codes[position / 8] |= (uint8_t)(code << (position % 8));
        expected += (int32_t)weights[i] * x[i];
    }
    mk61ai_prepare_lut32(x, &table);
    int32_t scalar, lookup;
    if (bits == 2) {
        mk61ai_pack_q2_planes32(codes, planes);
        scalar = mk61ai_dot_q2_a8_32(codes, x);
        lookup = mk61ai_dot_lut_q2_a8_32(planes, &table);
    } else {
        mk61ai_pack_q4_planes32(codes, planes);
        scalar = mk61ai_dot_q4_a8_32(codes, x);
        lookup = mk61ai_dot_lut_q4_a8_32(planes, &table);
    }
    if (scalar != expected || lookup != expected) {
        fprintf(stderr, "Q%u case %u: oracle=%ld scalar=%ld lut=%ld\n", bits, checks,
                (long)expected, (long)scalar, (long)lookup);
        exit(1);
    }
    /* Also verify every bit independently of dot products, including zeros. */
    for (unsigned i = 0; i < 32; ++i) {
        unsigned code = 0;
        const unsigned g = i / 4, lane = i % 4;
        for (unsigned b = 0; b < bits; ++b) {
            const unsigned index = (planes[4 * b + g / 2] >> (4 * (g % 2))) & 15U;
            code |= ((index >> lane) & 1U) << b;
        }
        if ((int)code - bias != weights[i]) exit(2);
    }
    ++checks;
}

int main(void) {
    int8_t weights[32], x[32];
    static const int8_t patterns[][4] = {
        {0, 0, 0, 0}, {-128, -128, -128, -128}, {127, 127, 127, 127},
        {-128, 127, -17, 1}, {1, -1, 1, -1}, {127, 0, 0, 0},
        {0, -128, 0, 0}, {0, 0, 127, 0}, {0, 0, 0, -128}
    };
    for (unsigned bits = 2; bits <= 4; bits += 2) {
        const unsigned levels = 1U << bits;
        const unsigned mask = levels - 1;
        /* All Q2/Q4 weight combinations in a quartet, with extremal inputs. */
        for (unsigned c = 0; c < (1U << (4 * bits)); ++c) {
            const unsigned g = c % 8;
            memset(weights, 0, sizeof(weights));
            for (unsigned j = 0; j < 4; ++j)
                weights[4 * g + j] = (int8_t)((int)((c >> (j * bits)) & mask) - (int)(levels / 2));
            for (unsigned p = 0; p < sizeof(patterns) / sizeof(patterns[0]); ++p) {
                for (unsigned i = 0; i < 32; ++i) x[i] = patterns[p][i % 4];
                check(weights, x, bits);
            }
        }
        /* Full groups catch group ordering, cancellation and input extrema. */
        for (unsigned n = 0; n < 20000; ++n) {
            for (unsigned i = 0; i < 32; ++i) {
                weights[i] = (int8_t)((int)(random_word() & mask) - (int)(levels / 2));
                x[i] = (int8_t)((int)(random_word() & 255U) - 128);
            }
            check(weights, x, bits);
        }
        for (unsigned wi = 0; wi < levels; ++wi) {
            memset(weights, (int)wi - (int)(levels / 2), sizeof(weights));
            for (unsigned xi = 0; xi < 256; ++xi) {
                memset(x, (int)xi - 128, sizeof(x));
                check(weights, x, bits);
            }
        }
    }
    printf("{\"status\":\"ok\",\"group_cases\":%u,\"dot_products\":%u,\"lut_bytes\":%zu}\n",
           checks, 2 * checks, sizeof(mk61ai_lut32));
    return 0;
}
