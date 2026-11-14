#include "../examples/portable-apps/ANOTHER/prepared.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t bank[128], store[4097], cache[128]; unsigned bank_reads, cache_reads; } memory;
static bool bank_read(void *v, uint8_t bank, uint32_t at, void *out, uint32_t n) {
    memory *m = v; if (bank != 1 || at > sizeof(m->bank) || n > sizeof(m->bank) - at) return false;
    memcpy(out, m->bank + at, n); ++m->bank_reads; return true;
}
static bool store_read(void *v, uint32_t at, void *out, uint32_t n) {
    memory *m = v; if (at > sizeof(m->store) || n > sizeof(m->store) - at) return false;
    memcpy(out, m->store + at, n); return true;
}
static bool store_write(void *v, uint32_t at, const void *in, uint32_t n) {
    memory *m = v; if (at > sizeof(m->store) || n > sizeof(m->store) - at) return false;
    memcpy(m->store + at, in, n); return true;
}
static bool cache_read(void *v, uint32_t at, void *out, uint32_t n) {
    memory *m = v; if (at > sizeof(m->cache) || n > sizeof(m->cache) - at) return false;
    memcpy(out, m->cache + at, n); ++m->cache_reads; return true;
}
static uint32_t fnv(const uint8_t *p, unsigned n) {
    uint32_t h = 2166136261u; while (n--) h = (h ^ *p++) * 16777619u; return h;
}
static void le32(uint8_t *p, uint32_t n) { p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24); }
static void be16(uint8_t *p, uint16_t n) { p[0] = (uint8_t)(n >> 8); p[1] = (uint8_t)n; }
static void be32(uint8_t *p, uint32_t n) { p[0] = (uint8_t)(n >> 24); p[1] = (uint8_t)(n >> 16); p[2] = (uint8_t)(n >> 8); p[3] = (uint8_t)n; }
static void entry(uint8_t *p, uint32_t offset, uint16_t packed, uint16_t size) {
    p[7] = 1; be32(p + 8, offset); be16(p + 14, packed); be16(p + 18, size);
}
static void compressed(uint8_t *out) {
    uint8_t bits[36]; unsigned n = 0;
#define FIELD(value, count) do { for (int bit = (count) - 1; bit >= 0; --bit) bits[n++] = (uint8_t)(((value) >> bit) & 1); } while (0)
    FIELD(0, 2); FIELD(0, 3); FIELD('A', 8); FIELD(1, 1); FIELD(2, 2); FIELD(22, 8); FIELD(1, 12);
#undef FIELD
    assert(n == 36); uint32_t initial = 0x80000000u, previous = 0;
    for (unsigned i = 0; i < 31; ++i) initial |= (uint32_t)bits[i] << i;
    for (unsigned i = 31; i < n; ++i) previous |= (uint32_t)bits[i] << (i - 31);
    be32(out, previous); be32(out + 4, initial); be32(out + 8, initial ^ previous); be32(out + 12, 24);
}
static void setup(memory *m, uint8_t *list) {
    memset(m, 0, sizeof(*m)); memset(list, 0, 41);
    entry(list, 0, 24, 24); entry(list + 20, 32, 16, 24); list[40] = 0xFF;
    for (unsigned i = 0; i < 24; ++i) m->bank[i] = (uint8_t)(i + 1);
    compressed(m->bank + 32);
    memcpy(m->cache, "AWC1", 4); le32(m->cache + 4, 1); le32(m->cache + 8, 2);
    le32(m->cache + 12, 41); le32(m->cache + 16, fnv(list, 41)); le32(m->cache + 20, 24);
    le32(m->cache + 24, 48); le32(m->cache + 28, fnv(m->bank, 24));
    memcpy(m->cache + 48, m->bank, 24); le32(m->cache + 32, fnv(m->cache + 48, 24));
    le32(m->cache + 36, 72); le32(m->cache + 40, fnv(m->bank + 32, 16));
    memset(m->cache + 72, 'A', 24); le32(m->cache + 44, fnv(m->cache + 72, 24));
}
static void init(memory *m, aw_assets *a, aw_prepared_cache *c, uint8_t *list, uint8_t *scratch) {
    assert(aw_assets_init(a, list, 41, sizeof(m->store), m, bank_read, store_read, store_write));
    assert(aw_prepared_open(c, list, 41, 2, 96, scratch, 24, m, cache_read));
}
int main(void) {
    memory m; aw_assets assets; aw_prepared_cache c; uint8_t list[41], table[24], out[24];
    setup(&m, list); init(&m, &assets, &c, list, table);
    assert(aw_prepared_load(&c, &assets, 0) && aw_prepared_load(&c, &assets, 1));
    assert(aw_assets_read(&assets, assets.entries[0].store_offset, out, sizeof(out)) && !memcmp(out, m.bank, sizeof(out)));
    assert(aw_assets_read(&assets, assets.entries[1].store_offset, out, sizeof(out)));
    for (unsigned i = 0; i < sizeof(out); ++i) assert(out[i] == 'A');
    unsigned reads = m.bank_reads; assert(aw_assets_load(&assets, 1) && reads == m.bank_reads);

    setup(&m, list); m.cache[72] ^= 1; init(&m, &assets, &c, list, table);
    assert(!aw_prepared_load(&c, &assets, 1) && !assets.entries[1].decoded && !assets.fault);
    assert(aw_assets_load(&assets, 1) && aw_assets_read(&assets, 24, out, sizeof(out)));
    for (unsigned i = 0; i < sizeof(out); ++i) assert(out[i] == 'A');

    setup(&m, list); m.bank[0] ^= 0x80; init(&m, &assets, &c, list, table);
    assert(!aw_prepared_load(&c, &assets, 0) && !assets.entries[0].decoded);
    assert(aw_assets_load(&assets, 0) && aw_assets_read(&assets, 0, out, sizeof(out)) && !memcmp(out, m.bank, sizeof(out)));

    setup(&m, list); list[1] = 1;
    assert(!aw_prepared_open(&c, list, 41, 2, 96, table, sizeof(table), &m, cache_read));
    list[1] = 0; assert(!aw_prepared_open(&c, list, 41, 2, 47, table, sizeof(table), &m, cache_read));
    assert(!aw_prepared_open(&c, list, 41, 2, 96, table, 23, &m, cache_read));
    puts("Prepared sound cache: source/payload validation and original-data fallback passed");
    return 0;
}
