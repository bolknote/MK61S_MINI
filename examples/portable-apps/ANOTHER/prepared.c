#include "prepared.h"
#include <string.h>

enum { HEADER_BYTES = 24, RECORD_BYTES = 12 };
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint32_t hash(uint32_t h, const uint8_t *p, uint32_t size) {
    while (size--) h = (h ^ *p++) * 16777619u;
    return h;
}

bool aw_prepared_open(aw_prepared_cache *c, const uint8_t *list, size_t bytes,
                      unsigned count, uint32_t size, void *scratch, size_t capacity,
                      void *ctx, aw_prepared_read read) {
    if (!c || !list || !scratch || !read || count > AW_ASSET_LIMIT || bytes > UINT32_MAX) return false;
    memset(c, 0, sizeof(*c));
    uint8_t header[HEADER_BYTES];
    const uint32_t table_size = count * RECORD_BYTES;
    if (size < HEADER_BYTES || table_size > size - HEADER_BYTES || capacity < table_size ||
        !read(ctx, 0, header, sizeof(header)) || memcmp(header, "AWC1", 4) ||
        le32(header + 4) != 1 || le32(header + 8) != count || le32(header + 12) != bytes ||
        le32(header + 16) != hash(2166136261u, list, (uint32_t)bytes) ||
        le32(header + 20) != table_size || !read(ctx, HEADER_BYTES, scratch, table_size)) return false;
    c->ctx = ctx; c->read = read; c->table = scratch; c->size = size;
    c->count = count; c->payload = HEADER_BYTES + table_size;
    return true;
}

bool aw_prepared_load(aw_prepared_cache *c, aw_assets *a, unsigned id) {
    if (!c || !c->read || !a || a->fault || id >= c->count || id >= a->count) return false;
    aw_asset_entry *e = &a->entries[id];
    if (e->decoded) return true;
    if (e->type || !e->bank || !e->size || !e->packed_size) return false;
    const uint8_t *record = c->table + id * RECORD_BYTES;
    const uint32_t start = le32(record), source_hash = le32(record + 4), raw_hash = le32(record + 8);
    if (start < c->payload || start > c->size || e->size > c->size - start) return false;
    a->prefetch.input_valid = false;
    uint8_t input[2048];
    uint32_t h = 2166136261u;
    for (uint32_t at = 0; at < e->packed_size;) {
        uint32_t n = e->packed_size - at;
        if (n > sizeof(input)) n = sizeof(input);
        if (!a->bank_read(a->ctx, e->bank, e->bank_offset + at, input, n)) return false;
        h = hash(h, input, n); at += n; aw_assets_progress(a);
    }
    if (h != source_hash) return false;
    h = 2166136261u;
    for (uint32_t at = 0; at < e->size;) {
        uint32_t n = e->size - at;
        if (n > sizeof(input)) n = sizeof(input);
        if (!c->read(c->ctx, start + at, input, n)) return false;
        h = hash(h, input, n);
        if (!aw_assets_write(a, e->store_offset + at, input, n)) return false;
        at += n; aw_assets_progress(a);
    }
    if (h != raw_hash || !aw_assets_flush(a)) return false;
    e->decoded = 1;
    return true;
}
