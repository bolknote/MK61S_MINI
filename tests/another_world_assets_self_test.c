#include "../examples/portable-apps/ANOTHER/assets.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t bank[256], store[4097];
    unsigned reads, writes, store_reads;
    bool fail_bank, fail_store;
} test_memory;

static bool bank_read(void *v, uint8_t bank, uint32_t at, void *out, uint32_t n) {
    test_memory *m = v;
    if (m->fail_bank || bank != 1 || at > sizeof(m->bank) || n > sizeof(m->bank) - at) return false;
    memcpy(out, m->bank + at, n); ++m->reads; return true;
}
static bool store_read(void *v, uint32_t at, void *out, uint32_t n) {
    test_memory *m = v;
    if (m->fail_store || at > sizeof(m->store) || n > sizeof(m->store) - at) return false;
    memcpy(out, m->store + at, n); ++m->store_reads; return true;
}
static bool store_write(void *v, uint32_t at, const void *in, uint32_t n) {
    test_memory *m = v;
    if (m->fail_store || at > sizeof(m->store) || n > sizeof(m->store) - at) return false;
    memcpy(m->store + at, in, n); ++m->writes; return true;
}
static void put16(uint8_t *p, uint16_t n) { p[0] = (uint8_t)(n >> 8); p[1] = (uint8_t)n; }
static void put32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)(n >> 24); p[1] = (uint8_t)(n >> 16); p[2] = (uint8_t)(n >> 8); p[3] = (uint8_t)n;
}
static void entry(uint8_t *p, uint32_t offset, uint16_t packed, uint16_t unpacked) {
    memset(p, 0, 20); p[7] = 1; put32(p + 8, offset); put16(p + 14, packed); put16(p + 18, unpacked);
}
static void append_bits(uint8_t *bits, unsigned *n, unsigned value, unsigned count) {
    while (count--) bits[(*n)++] = (uint8_t)((value >> count) & 1u);
}
static void make_compressed(uint8_t *out) {
    /* One literal 'A' followed by a distance-1 copy of 23 bytes. The first
     * source word holds 31 bits plus a sentinel; the remaining bits are in
     * the preceding word, as in ByteKiller's backwards bitstream. */
    uint8_t bits[64]; unsigned n = 0;
    append_bits(bits, &n, 0, 2); append_bits(bits, &n, 0, 3);
    append_bits(bits, &n, 'A', 8); append_bits(bits, &n, 1, 1);
    append_bits(bits, &n, 2, 2); append_bits(bits, &n, 22, 8);
    append_bits(bits, &n, 1, 12);
    assert(n == 36);
    uint32_t initial = 0x80000000u, previous = 0;
    for (unsigned i = 0; i < 31; ++i) initial |= (uint32_t)bits[i] << i;
    for (unsigned i = 31; i < n; ++i) previous |= (uint32_t)bits[i] << (i - 31);
    put32(out, previous); put32(out + 4, initial);
    put32(out + 8, initial ^ previous); put32(out + 12, 24);
}

int main(void) {
    test_memory m = {0}; aw_assets a; uint8_t list[61] = {0};
    entry(list, 0, 24, 24); entry(list + 20, 32, 16, 24);
    entry(list + 40, 64, 16, 24); list[60] = 0xFF;
    for (unsigned i = 0; i < 24; ++i) m.bank[i] = (uint8_t)(i + 1);
    make_compressed(m.bank + 32); memcpy(m.bank + 64, m.bank + 32, 16); m.bank[72] ^= 1;
    assert(aw_assets_init(&a, list, sizeof(list), sizeof(m.store), &m, bank_read, store_read, store_write));
    assert(a.count == 3 && a.used == 72);
    assert(aw_assets_load(&a, 0));
    uint8_t out[24];
    assert(aw_assets_read(&a, a.entries[0].store_offset, out, sizeof(out)));
    assert(!memcmp(out, m.bank, sizeof(out)));
    const unsigned reads = m.reads;
    assert(aw_assets_load(&a, 0) && m.reads == reads);
    assert(aw_assets_load(&a, 1));
    assert(aw_assets_read(&a, a.entries[1].store_offset, out, sizeof(out)));
    for (unsigned i = 0; i < sizeof(out); ++i) assert(out[i] == 'A');
    assert(!aw_assets_load(&a, 2) && !a.entries[2].decoded);
    assert(!aw_assets_load(&a, 3));
    assert(!aw_assets_read(&a, sizeof(m.store), out, 1));
    assert(!aw_assets_write(&a, UINT32_MAX, out, 1));
    for (uint32_t page = 0; page < 4; ++page) {
        uint8_t value = (uint8_t)(page + 17);
        assert(aw_assets_write(&a, page * AW_ASSET_PAGE, &value, 1));
    }
    assert(aw_assets_flush(&a));
    for (unsigned page = 0; page < 4; ++page) assert(m.store[page * AW_ASSET_PAGE] == page + 17);
    assert(m.writes > 0);
    /* Long direct I/O must see dirty cache data and preserve dirty bytes
     * outside its range, even when the endpoints cut through cache pages. */
    uint8_t expected[sizeof(m.store)], bulk[sizeof(m.store)];
    for (unsigned i = 0; i < sizeof(expected); ++i) expected[i] = m.store[i] = (uint8_t)(i * 19u);
    assert(aw_assets_init(&a, list, sizeof(list), sizeof(m.store), &m, bank_read, store_read, store_write));
    uint8_t marker = 0xD3; expected[5] = marker;
    assert(aw_assets_write(&a, 5, &marker, 1));
    marker = 0x39; expected[1500] = marker;
    assert(aw_assets_write(&a, 1500, &marker, 1));
    unsigned store_reads = m.store_reads;
    assert(aw_assets_read(&a, 300, bulk, 3000));
    assert(m.store_reads == store_reads + 1 && !memcmp(bulk, expected + 300, 3000));
    assert(m.store[5] == expected[5]);
    marker = 0x42; expected[250] = marker;
    assert(aw_assets_write(&a, 250, &marker, 1));
    marker = 0xB7; expected[3000] = marker;
    assert(aw_assets_write(&a, 3000, &marker, 1));
    assert(aw_assets_read(&a, 1000, &marker, 1) && marker == expected[1000]);
    memset(bulk, 0x6A, 3000); memset(expected + 500, 0x6A, 3000);
    assert(aw_assets_write(&a, 500, bulk, 3000));
    /* Direct writes invalidate the most recently used page too. */
    assert(aw_assets_read(&a, 1000, &marker, 1) && marker == expected[1000]);
    assert(aw_assets_read(&a, 0, bulk, sizeof(bulk)) && !memcmp(bulk, expected, sizeof(bulk)));
    assert(aw_assets_flush(&a) && !memcmp(m.store, expected, sizeof(expected)));
    assert(!aw_assets_init(&a, list, 60, sizeof(m.store), &m, bank_read, store_read, store_write));
    assert(!aw_assets_init(&a, list, sizeof(list), 32, &m, bank_read, store_read, store_write));
    assert(aw_assets_init(&a, list, sizeof(list), sizeof(m.store), &m, bank_read, store_read, store_write));
    m.fail_bank = true; assert(!aw_assets_load(&a, 0) && !a.entries[0].decoded); m.fail_bank = false;
    m.fail_store = true; assert(!aw_assets_load(&a, 0) && a.fault && !a.entries[0].decoded);
    puts("Another World asset tests passed");
    return 0;
}
