/* DOS resource format and ByteKiller decoding based on Raw, Copyright (C)
 * 2004 Gregory Montoir, distributed under GPL-2.0-or-later. */
#include "assets.h"
#include <string.h>

static uint16_t be16(const uint8_t *p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}
static uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

bool aw_assets_init(aw_assets *a, const uint8_t *list, size_t bytes,
                    uint32_t capacity, void *ctx, aw_asset_bank_read bank_read,
                    aw_asset_store_read store_read, aw_asset_store_write store_write) {
    if (!a || !list || !bank_read || !store_read || !store_write || !capacity) return false;
    memset(a, 0, sizeof(*a));
    a->ctx = ctx; a->bank_read = bank_read; a->store_read = store_read;
    a->store_write = store_write; a->capacity = capacity;
    size_t at = 0;
    while (at < bytes) {
        if (list[at] == 0xFF) return a->count != 0;
        if (bytes - at < 20 || a->count == AW_ASSET_LIMIT) return false;
        const uint8_t *p = list + at;
        aw_asset_entry *e = &a->entries[a->count++];
        e->type = p[1]; e->rank = p[6]; e->bank = p[7];
        e->bank_offset = be32(p + 8); e->packed_size = be16(p + 14); e->size = be16(p + 18);
        if (e->packed_size > e->size || e->bank_offset > UINT32_MAX - e->packed_size ||
            a->used > capacity || e->size > capacity - a->used) return false;
        e->store_offset = a->used;
        a->used += e->size;
        at += 20;
    }
    return false;
}

static bool flush_slot(aw_assets *a, aw_asset_cache *c) {
    if (!c->valid || !c->dirty) return true;
    const uint32_t offset = c->page * AW_ASSET_PAGE;
    uint32_t size = a->capacity - offset;
    if (size > AW_ASSET_PAGE) size = AW_ASSET_PAGE;
    if (!a->store_write(a->ctx, offset, c->data, size)) return !(a->fault = true);
    c->dirty = false;
    return true;
}

static aw_asset_cache *cached(aw_assets *a, uint32_t offset) {
    if (a->fault || offset >= a->capacity) { a->fault = true; return NULL; }
    const uint32_t page = offset / AW_ASSET_PAGE;
    /* Bytecode and polygon bytes usually come from the same page as the
     * previous read. Keep the LRU age but avoid scanning every cache slot. */
    aw_asset_cache *recent = a->recent;
    if (recent && recent->valid && recent->page == page) { recent->age = ++a->clock; return recent; }
    aw_asset_cache *oldest = &a->cache[0];
    for (unsigned i = 0; i < AW_ASSET_CACHE_SLOTS; ++i) {
        aw_asset_cache *c = &a->cache[i];
        if (c->valid && c->page == page) { c->age = ++a->clock; a->recent = c; return c; }
        if (!c->valid || (oldest->valid && c->age < oldest->age)) oldest = c;
    }
    if (!flush_slot(a, oldest)) return NULL;
    const uint32_t base = page * AW_ASSET_PAGE;
    uint32_t size = a->capacity - base;
    if (size > AW_ASSET_PAGE) size = AW_ASSET_PAGE;
    if (!a->store_read(a->ctx, base, oldest->data, size)) { a->fault = true; return NULL; }
    oldest->page = page; oldest->age = ++a->clock; oldest->valid = true; oldest->dirty = false;
    a->recent = oldest;
    return oldest;
}

/* Full video pages would evict the bytecode, polygon and audio working set
 * from the small cache. Transfer long spans directly, while preserving dirty
 * bytes on partially covered cache pages and invalidating overwritten ones. */
static bool transfer_direct(aw_assets *a, uint32_t offset, uint8_t *bytes,
                            uint32_t size, bool write) {
    if (a->fault) return false;
    while (size) {
        const uint32_t n = size < AW_ASSET_MAX_TRANSFER ? size : AW_ASSET_MAX_TRANSFER;
        const uint32_t end = offset + n;
        for (unsigned i = 0; i < AW_ASSET_CACHE_SLOTS; ++i) {
            aw_asset_cache *c = &a->cache[i];
            if (!c->valid) continue;
            if (c->page < offset / AW_ASSET_PAGE || c->page > (end - 1) / AW_ASSET_PAGE) continue;
            if (!flush_slot(a, c)) return false;
            if (write) c->valid = false;
        }
        const bool ok = write ? a->store_write(a->ctx, offset, bytes, n)
                              : a->store_read(a->ctx, offset, bytes, n);
        if (!ok) return !(a->fault = true);
        offset += n; bytes += n; size -= n;
    }
    return true;
}

bool aw_assets_read(aw_assets *a, uint32_t offset, void *out, uint32_t size) {
    if (!a || (!out && size) || offset > a->capacity || size > a->capacity - offset) return false;
    uint8_t *p = out;
    if (size >= AW_ASSET_PAGE) return transfer_direct(a, offset, p, size, false);
    while (size) {
        aw_asset_cache *c = cached(a, offset);
        if (!c) return false;
        const uint32_t pos = offset % AW_ASSET_PAGE;
        uint32_t n = AW_ASSET_PAGE - pos;
        if (n > size) n = size;
        memcpy(p, c->data + pos, n);
        p += n; offset += n; size -= n;
    }
    return !a->fault;
}

bool aw_assets_write(aw_assets *a, uint32_t offset, const void *in, uint32_t size) {
    if (!a || (!in && size) || offset > a->capacity || size > a->capacity - offset) return false;
    const uint8_t *p = in;
    if (size >= AW_ASSET_PAGE) return transfer_direct(a, offset, (uint8_t *)p, size, true);
    while (size) {
        aw_asset_cache *c = cached(a, offset);
        if (!c) return false;
        const uint32_t pos = offset % AW_ASSET_PAGE;
        uint32_t n = AW_ASSET_PAGE - pos;
        if (n > size) n = size;
        memcpy(c->data + pos, p, n); c->dirty = true;
        p += n; offset += n; size -= n;
    }
    return !a->fault;
}

bool aw_assets_flush(aw_assets *a) {
    if (!a || a->fault) return false;
    for (unsigned i = 0; i < AW_ASSET_CACHE_SLOTS; ++i)
        if (!flush_slot(a, &a->cache[i])) return false;
    return true;
}
void aw_assets_progress(aw_assets *a) { if (a && a->progress) a->progress(a->progress_ctx); }

typedef struct {
    aw_assets *assets;
    const aw_asset_entry *entry;
    uint32_t input_base, input_size, cursor, output, bits, crc;
    bool input_valid, failed;
} unpacker;

static uint8_t input_byte(unpacker *u, uint32_t at) {
    if (u->failed || at >= u->entry->packed_size) { u->failed = true; return 0; }
    const uint32_t base = at - at % AW_ASSET_PAGE;
    if (!u->input_valid || u->input_base != base) {
        uint32_t size = u->entry->packed_size - base;
        if (size > AW_ASSET_PAGE) size = AW_ASSET_PAGE;
        if (!u->assets->bank_read(u->assets->ctx, u->entry->bank,
                                  u->entry->bank_offset + base, u->assets->input, size)) {
            u->failed = true; return 0;
        }
        u->input_base = base; u->input_size = size; u->input_valid = true;
    }
    return u->assets->input[at - u->input_base];
}

static uint32_t input_word(unpacker *u, uint32_t at) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value = (value << 8) | input_byte(u, at + i);
    return value;
}

static unsigned next_bit(unpacker *u) {
    unsigned bit = u->bits & 1u;
    u->bits >>= 1;
    if (!u->bits) {
        if (u->cursor < 4) { u->failed = true; return 0; }
        u->cursor -= 4;
        u->bits = input_word(u, u->cursor);
        u->crc ^= u->bits;
        bit = u->bits & 1u;
        u->bits = (u->bits >> 1) | 0x80000000u;
    }
    return bit;
}

static uint32_t read_bits(unpacker *u, unsigned count) {
    uint32_t value = 0;
    while (count--) value = (value << 1) | next_bit(u);
    return value;
}

static void literal(unpacker *u, uint32_t count) {
    if (count > u->output) { u->failed = true; return; }
    while (count-- && !u->failed) {
        const uint8_t byte = (uint8_t)read_bits(u, 8);
        --u->output;
        if (!aw_assets_write(u->assets, u->entry->store_offset + u->output, &byte, 1)) u->failed = true;
    }
}

static void backref(unpacker *u, uint32_t count, uint32_t distance) {
    if (count > u->output || !distance || distance > u->entry->size - u->output) {
        u->failed = true; return;
    }
    while (count-- && !u->failed) {
        uint8_t byte;
        --u->output;
        if (!aw_assets_read(u->assets, u->entry->store_offset + u->output + distance, &byte, 1) ||
            !aw_assets_write(u->assets, u->entry->store_offset + u->output, &byte, 1)) u->failed = true;
    }
}

static bool unpack(aw_assets *a, const aw_asset_entry *e) {
    if (e->packed_size < 12 || (e->packed_size & 3u)) return false;
    unpacker u = {0}; u.assets = a; u.entry = e; u.cursor = e->packed_size - 12;
    if (input_word(&u, e->packed_size - 4) != e->size) return false;
    u.crc = input_word(&u, e->packed_size - 8);
    u.bits = input_word(&u, e->packed_size - 12);
    u.crc ^= u.bits; u.output = e->size;
    uint32_t progress_at = u.output;
    while (u.output && !u.failed) {
        if (!next_bit(&u)) {
            if (!next_bit(&u)) literal(&u, read_bits(&u, 3) + 1);
            else backref(&u, 2, read_bits(&u, 8));
        } else {
            const unsigned code = read_bits(&u, 2);
            if (code == 3) literal(&u, read_bits(&u, 8) + 9);
            else if (code < 2) backref(&u, code + 3, read_bits(&u, code + 9));
            else {
                const unsigned count = read_bits(&u, 8) + 1;
                backref(&u, count, read_bits(&u, 12));
            }
        }
        if (progress_at - u.output >= 256) { aw_assets_progress(a); progress_at = u.output; }
    }
    return !u.failed && !u.output && !u.crc;
}

bool aw_assets_load(aw_assets *a, unsigned id) {
    if (!a || a->fault || id >= a->count) return false;
    aw_asset_entry *e = &a->entries[id];
    if (e->decoded) return true;
    if (!e->bank || !e->size || !e->packed_size) return false;
    bool ok = true;
    if (e->size != e->packed_size) ok = unpack(a, e);
    else for (uint32_t at = 0; at < e->size && ok;) {
        uint32_t n = e->size - at;
        if (n > AW_ASSET_PAGE) n = AW_ASSET_PAGE;
        ok = a->bank_read(a->ctx, e->bank, e->bank_offset + at, a->input, n) &&
             aw_assets_write(a, e->store_offset + at, a->input, n);
        at += n;
        aw_assets_progress(a);
    }
    if (!ok || a->fault || !aw_assets_flush(a)) return false;
    e->decoded = 1;
    return true;
}
