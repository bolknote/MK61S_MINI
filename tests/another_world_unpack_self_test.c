#include "../examples/portable-apps/ANOTHER/assets.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { PREFIX = 997, OUTPUT = 5000, BANK_CAP = 16000, STORE_CAP = 8192, MAX_BITS = 100000 };
typedef struct { uint8_t bank[BANK_CAP], store[STORE_CAP]; unsigned bank_size; } memory;
static bool bank_read(void *ctx, uint8_t bank, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx; if (bank != 1 || at > m->bank_size || size > m->bank_size - at) return false;
    memcpy(out, m->bank + at, size); return true;
}
static bool store_read(void *ctx, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx; if (at > STORE_CAP || size > STORE_CAP - at) return false;
    memcpy(out, m->store + at, size); return true;
}
static bool store_write(void *ctx, uint32_t at, const void *in, uint32_t size) {
    memory *m = ctx; if (at > STORE_CAP || size > STORE_CAP - at) return false;
    memcpy(m->store + at, in, size); return true;
}
static uint32_t random32(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s; }
static void put16(uint8_t *p, uint16_t n) { p[0] = (uint8_t)(n >> 8); p[1] = (uint8_t)n; }
static void put32(uint8_t *p, uint32_t n) { p[0] = (uint8_t)(n >> 24); p[1] = (uint8_t)(n >> 16); p[2] = (uint8_t)(n >> 8); p[3] = (uint8_t)n; }
static void bits_add(uint8_t *bits, unsigned *n, unsigned value, unsigned count) {
    assert(*n + count <= MAX_BITS);
    while (count--) bits[(*n)++] = (uint8_t)((value >> count) & 1u);
}
static unsigned make_stream(uint8_t *out, uint8_t *expected, uint32_t seed, bool dense) {
    static uint8_t bits[MAX_BITS]; unsigned n = 0, remaining = OUTPUT;
    while (remaining) {
        const unsigned written = OUTPUT - remaining;
        if (!written || ((random32(&seed) >> 24) % 10u) < (dense ? 7u : 2u)) {
            unsigned count = 1 + random32(&seed) % 8u; if (count > remaining) count = remaining;
            bits_add(bits, &n, 0, 2); bits_add(bits, &n, count - 1, 3);
            for (unsigned i = 0; i < count; ++i) {
                const uint8_t b = (uint8_t)(random32(&seed) >> 24);
                bits_add(bits, &n, b, 8); expected[--remaining] = b;
            }
        } else {
            unsigned count = 1 + random32(&seed) % (dense ? 16u : 256u); if (count > remaining) count = remaining;
            const unsigned max_distance = written < 4095 ? written : 4095;
            const unsigned distance = 1 + random32(&seed) % max_distance;
            bits_add(bits, &n, 1, 1); bits_add(bits, &n, 2, 2);
            bits_add(bits, &n, count - 1, 8); bits_add(bits, &n, distance, 12);
            for (unsigned i = 0; i < count; ++i) { --remaining; expected[remaining] = expected[remaining + distance]; }
        }
    }
    assert(n > 31);
    const unsigned words = 1 + (n - 31 + 31) / 32;
    assert((words + 2) * 4 < OUTPUT && (words + 2) * 4 <= BANK_CAP);
    uint32_t crc = 0;
    for (unsigned j = 0; j < words; ++j) {
        const unsigned first = j ? 31 + (j - 1) * 32 : 0, width = j ? 32 : 31;
        uint32_t word = j ? 0 : 0x80000000u;
        for (unsigned i = 0; i < width && first + i < n; ++i) word |= (uint32_t)bits[first + i] << i;
        put32(out + (words - j - 1) * 4, word); crc ^= word;
    }
    put32(out + words * 4, crc); put32(out + (words + 1) * 4, OUTPUT);
    return (words + 2) * 4;
}
int main(void) {
    static memory m; static aw_assets assets; static uint8_t expected[OUTPUT], actual[OUTPUT]; uint8_t list[41];
    for (uint32_t test = 0; test < 64; ++test) {
        memset(&m, 0, sizeof(m)); memset(list, 0, sizeof(list));
        m.bank_size = make_stream(m.bank, expected, 0x6c47a53bu + test, (test & 1) != 0);
        if (test & 1) assert(m.bank_size > 2048);
        list[7] = 1; put16(list + 14, PREFIX); put16(list + 18, PREFIX);
        list[27] = 1; put16(list + 34, (uint16_t)m.bank_size); put16(list + 38, OUTPUT); list[40] = 0xFF;
        assert(aw_assets_init(&assets, list, sizeof(list), STORE_CAP, &m, bank_read, store_read, store_write));
        if (test & 1) assets.clock = UINT32_MAX - 3;
        assert(aw_assets_load(&assets, 1));
        assert(aw_assets_read(&assets, PREFIX, actual, OUTPUT));
        assert(!memcmp(actual, expected, OUTPUT));
        m.bank[m.bank_size - 5] ^= 1;
        assert(aw_assets_init(&assets, list, sizeof(list), STORE_CAP, &m, bank_read, store_read, store_write));
        assert(!aw_assets_load(&assets, 1) && !assets.entries[1].decoded);
    }
    puts("ByteKiller public decoding: 64 mixed streams, overlap, pages and CRC passed"); return 0;
}
