#include "display_compact.h"
#include <string.h>

#define COMPACT_ROWS 10u
#define BAND_BYTES (AW_VIDEO_BAND_ROWS * AW_VIDEO_STRIDE)
/* 3200 bytes is the minimum scratch capacity accepted by this renderer. */
#define MIN_SCRATCH_BYTES 3200u
#define MAX_ROWS 80u
#define MERGE_EXTRA_PIXELS 800u
_Static_assert(AW_VIDEO_HEIGHT % AW_VIDEO_BAND_ROWS == 0 && AW_VIDEO_BANDS < 32, "display band geometry");
typedef struct {
    unsigned x0, x1, y0, y1;
} rectangle;

bool aw_display_compact_init(aw_display_compact *d, aw_assets *a, uint32_t base, uint8_t *previous,
                             uint32_t capacity, uint8_t *scratch, uint32_t scratch_bytes) {
    if (!d || !a || !previous || !scratch || (previous == scratch && scratch_bytes > capacity) ||
        capacity > UINT16_MAX ||
        scratch_bytes < MIN_SCRATCH_BYTES || scratch_bytes > 12800 || base > a->capacity ||
        AW_VIDEO_PAGE_BYTES > a->capacity - base)
        return false;
    memset(d, 0, sizeof(*d));
    d->assets = a;
    d->external_base = base;
    d->previous = previous;
    d->capacity = capacity;
    d->scratch = scratch;
    d->scratch_bytes = scratch_bytes;
    return true;
}

/* Each row has independent run and literal packets, with lengths 1..128. */
static bool decode(const aw_display_compact *d, unsigned y, uint8_t *out) {
    unsigned pos = d->offsets[y], end = d->offsets[y + 1], n = 0;
    if (pos > end || end > d->capacity)
        return false;
    while (pos < end) {
        const uint8_t code = d->previous[pos++];
        const unsigned count = (code & 127u) + 1u;
        if (count > AW_VIDEO_STRIDE - n)
            return false;
        if (code & 128u) {
            if (pos >= end)
                return false;
            memset(out + n, d->previous[pos++], count);
        } else {
            if (count > end - pos)
                return false;
            memcpy(out + n, d->previous + pos, count);
            pos += count;
        }
        n += count;
    }
    return n == AW_VIDEO_STRIDE;
}

static bool compress(aw_display_compact *d, const uint8_t *pixels) {
    unsigned used = 0;
    for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y) {
        d->offsets[y] = (uint16_t)used;
        const uint8_t *row = pixels + y * AW_VIDEO_STRIDE;
        unsigned x = 0;
        while (x < AW_VIDEO_STRIDE) {
            unsigned run = 1;
            while (x + run < AW_VIDEO_STRIDE && run < 128 && row[x + run] == row[x])
                ++run;
            if (run >= 3) {
                if (used + 2 > d->capacity)
                    return false;
                d->previous[used++] = (uint8_t)(128u | (run - 1));
                d->previous[used++] = row[x];
                x += run;
            } else {
                unsigned n = 0;
                while (x + n < AW_VIDEO_STRIDE && n < 128) {
                    unsigned at = x + n, r = 1;
                    while (at + r < AW_VIDEO_STRIDE && r < 3 && row[at + r] == row[at])
                        ++r;
                    if (r >= 3)
                        break;
                    ++n;
                }
                if (!n || used + 1 + n > d->capacity)
                    return false;
                d->previous[used++] = (uint8_t)(n - 1);
                memcpy(d->previous + used, row + x, n);
                used += n;
                x += n;
            }
        }
        if ((y & 31u) == 31u)
            aw_assets_progress(d->assets);
    }
    d->offsets[AW_VIDEO_HEIGHT] = (uint16_t)used;
    return true;
}

static bool repeat_above(const uint8_t *row, const uint8_t *above, unsigned x) {
    return above && x + 2 < AW_VIDEO_STRIDE && row[x] == above[x] &&
           row[x + 1] == above[x + 1] && row[x + 2] == above[x + 2];
}
static bool repeat_byte(const uint8_t *row, unsigned x) {
    return x + 2 < AW_VIDEO_STRIDE && row[x] == row[x + 1] && row[x] == row[x + 2];
}
static uint32_t word_at(const uint8_t *p) {
    uint32_t word;
    __builtin_memcpy(&word, __builtin_assume_aligned(p, sizeof(word)), sizeof(word));
    return word;
}
static unsigned end_of_match(const uint8_t *row, const uint8_t *above, unsigned x, unsigned end) {
    if (!(((uintptr_t)row | (uintptr_t)above) & 3u)) {
        while (x < end && (x & 3u)) {
            if (row[x] != above[x]) return x;
            ++x;
        }
        while (x + 4 <= end && word_at(row + x) == word_at(above + x)) x += 4;
    }
    while (x < end && row[x] == above[x]) ++x;
    return x;
}

/* Each packet is limited to its row. The first row in a band is independent
 * of the preceding band; subsequent rows also permit a copy from above. */
static unsigned pack_band(const uint8_t *pixels, uint8_t *packed, unsigned capacity) {
    unsigned used = 0;
    for (unsigned y = 0; y < AW_VIDEO_BAND_ROWS; ++y) {
        const uint8_t *row = pixels + y * AW_VIDEO_STRIDE;
        const uint8_t *above = y ? row - AW_VIDEO_STRIDE : NULL;
        for (unsigned x = 0; x < AW_VIDEO_STRIDE;) {
            const unsigned start = x;
            if (repeat_above(row, above, x)) {
                const unsigned end = x + 128 < AW_VIDEO_STRIDE ? x + 128 : AW_VIDEO_STRIDE;
                x = end_of_match(row, above, x + 3, end);
                if (used == capacity) return 0;
                packed[used++] = (uint8_t)(x - start - 1);
                continue;
            }
            const unsigned end = x + 64 < AW_VIDEO_STRIDE ? x + 64 : AW_VIDEO_STRIDE;
            if (repeat_byte(row, x)) {
                x += 3;
                while (x < end && row[x] == row[start]) ++x;
                if (capacity - used < 2) return 0;
                packed[used++] = (uint8_t)(0x80u | (x - start - 1));
                packed[used++] = row[start];
            } else {
                ++x;
                while (x < end && !repeat_above(row, above, x) && !repeat_byte(row, x)) ++x;
                const unsigned count = x - start;
                if (capacity - used < 1 + count) return 0;
                packed[used++] = (uint8_t)(0xc0u | (count - 1));
                memcpy(packed + used, row + start, count);
                used += count;
            }
        }
    }
    return used;
}
static bool unpack_band(const uint8_t *packed, unsigned size, uint8_t *pixels) {
    unsigned at = 0;
    for (unsigned y = 0; y < AW_VIDEO_BAND_ROWS; ++y) {
        uint8_t *row = pixels + y * AW_VIDEO_STRIDE;
        for (unsigned x = 0; x < AW_VIDEO_STRIDE;) {
            if (at == size) return false;
            const unsigned tag = packed[at++];
            const unsigned count = (tag & (tag < 128 ? 127u : 63u)) + 1;
            if (count > AW_VIDEO_STRIDE - x) return false;
            if (tag < 128) {
                if (!y) return false;
                memcpy(row + x, row - AW_VIDEO_STRIDE + x, count);
            } else if (tag < 192) {
                if (at == size) return false;
                memset(row + x, packed[at++], count);
            } else {
                if (count > size - at) return false;
                memcpy(row + x, packed + at, count);
                at += count;
            }
            x += count;
        }
    }
    return at == size;
}

/* Keep the compressed buffer disjoint from both the decoded band and any
 * rectangle being offered to the LCD service. */
static uint8_t *band_buffer(const aw_display_compact *d) {
    return d->scratch + d->scratch_bytes - BAND_BYTES;
}
static bool read_band(aw_display_compact *d, unsigned band) {
    const unsigned size = d->band_sizes[band];
    if (!size || size > BAND_BYTES) return false;
    const uint32_t offset = d->external_base + band * BAND_BYTES;
    if (size == BAND_BYTES) return aw_assets_read_direct(d->assets, offset, d->scratch, size);
    uint8_t *packed = band_buffer(d);
    return aw_assets_read_direct(d->assets, offset, packed, size) &&
           unpack_band(packed, size, d->scratch);
}

static bool prepare(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                    aw_display_rect_fn present, aw_display_wait_fn wait, void *ctx,
                    bool banded, uint32_t known, uint32_t *dirty) {
    if (!d || !pixels || !palette || !present || pixels == d->previous || pixels == d->scratch)
        return false;
    const bool full = !d->valid || memcmp(d->palette, palette, sizeof(d->palette));
    const unsigned band_rows = banded ? AW_VIDEO_BAND_ROWS : COMPACT_ROWS;
    const unsigned bands = AW_VIDEO_HEIGHT / band_rows;
    rectangle rects[AW_VIDEO_BANDS];
    unsigned count = 0;
    *dirty = 0;
    if (full) {
        *dirty = (1u << bands) - 1u;
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += MAX_ROWS) {
            unsigned end = y + MAX_ROWS;
            if (end > AW_VIDEO_HEIGHT)
                end = AW_VIDEO_HEIGHT;
            rects[count++] = (rectangle){0, AW_VIDEO_STRIDE, y, end};
        }
    } else {
        for (unsigned band = 0; band < bands; ++band) {
            if (known & (1u << band)) continue;
            const unsigned y = band * band_rows;
            unsigned left = AW_VIDEO_STRIDE, right = 0, top = AW_VIDEO_HEIGHT, bottom = 0;
            uint8_t row_previous[AW_VIDEO_STRIDE];
            if (banded || d->external) {
                const bool ok = banded ? read_band(d, band) :
                    aw_assets_read(d->assets, d->external_base + y * AW_VIDEO_STRIDE, d->scratch,
                                   band_rows * AW_VIDEO_STRIDE);
                if (!ok) {
                    d->valid = false;
                    return false;
                }
                aw_assets_progress(d->assets);
            }
            for (unsigned row = y; row < y + band_rows; ++row) {
                const uint8_t *now = pixels + row * AW_VIDEO_STRIDE;
                const uint8_t *old;
                if (banded || d->external) old = d->scratch + (row - y) * AW_VIDEO_STRIDE;
                else {
                    if (!decode(d, row, row_previous)) {
                        d->valid = false;
                        return false;
                    }
                    old = row_previous;
                }
                if (!memcmp(now, old, AW_VIDEO_STRIDE))
                    continue;
                if (top == AW_VIDEO_HEIGHT)
                    top = row;
                bottom = row + 1;
                for (unsigned x = 0; x < left; ++x)
                    if (now[x] != old[x]) {
                        left = x;
                        break;
                    }
                for (unsigned x = AW_VIDEO_STRIDE; x > right; --x)
                    if (now[x - 1] != old[x - 1]) {
                        right = x;
                        break;
                    }
            }
            if (top == AW_VIDEO_HEIGHT)
                continue;
            *dirty |= 1u << band;
            rectangle next = {left, right, top, bottom};
            if (count) {
                rectangle *prev = &rects[count - 1];
                const unsigned x0 = prev->x0 < next.x0 ? prev->x0 : next.x0;
                const unsigned x1 = prev->x1 > next.x1 ? prev->x1 : next.x1;
                const unsigned area = (x1 - x0) * 2 * (next.y1 - prev->y0);
                const unsigned separate = (prev->x1 - prev->x0) * 2 * (prev->y1 - prev->y0) +
                                          (next.x1 - next.x0) * 2 * (next.y1 - next.y0);
                if (next.y1 - prev->y0 <= MAX_ROWS && area <= separate + MERGE_EXTRA_PIXELS) {
                    *prev = (rectangle){x0, x1, prev->y0, next.y1};
                    continue;
                }
            }
            rects[count++] = next;
        }
    }
    if (wait && !wait(ctx)) return false;
    const bool clear = !d->valid;
    unsigned transfers = 0;
    for (unsigned i = 0; i < count; ++i) {
        const rectangle r = rects[i];
        const unsigned row_bytes = r.x1 - r.x0;
        const bool contiguous = banded && row_bytes == AW_VIDEO_STRIDE;
        const unsigned scratch_bytes = banded && !contiguous ? d->scratch_bytes - BAND_BYTES : d->scratch_bytes;
        const unsigned max_rows = scratch_bytes / row_bytes;
        for (unsigned y = r.y0; y < r.y1;) {
            unsigned rows = r.y1 - y;
            if (rows > max_rows)
                rows = max_rows;
            const uint8_t *source = pixels + y * AW_VIDEO_STRIDE;
            /* The LCD service copies contiguous full rows directly. */
            if (!contiguous) {
                for (unsigned row = 0; row < rows; ++row)
                    memcpy(d->scratch + row * row_bytes, source + row * AW_VIDEO_STRIDE + r.x0, row_bytes);
                source = d->scratch;
            }
            if (!present(ctx, 2 * r.x0, y, 2 * row_bytes, rows, source, palette, clear && !transfers)) {
                d->valid = false;
                return false;
            }
            ++transfers;
            y += rows;
        }
    }
    return true;
}

bool aw_display_compact_present(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                                aw_display_rect_fn present, void *ctx) {
    uint32_t dirty;
    if (!prepare(d, pixels, palette, present, NULL, ctx, false, 0, &dirty)) return false;
    if (dirty) {
        /* Some frames do not fit in the borrowed framebuffer. Keep those
         * exactly in PSRAM and try the compact form again on the next frame. */
        d->external = !compress(d, pixels);
        if (d->external)
            for (unsigned offset = 0; offset < AW_VIDEO_PAGE_BYTES;) {
                unsigned n = AW_VIDEO_PAGE_BYTES - offset;
                if (n > AW_ASSET_MAX_TRANSFER)
                    n = AW_ASSET_MAX_TRANSFER;
                if (!aw_assets_write(d->assets, d->external_base + offset, pixels + offset, n)) {
                    d->valid = false;
                    return false;
                }
                offset += n;
                aw_assets_progress(d->assets);
            }
    }
    memcpy(d->palette, palette, sizeof(d->palette));
    d->valid = true;
    return true;
}

bool aw_display_bands_prepare(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                              aw_display_rect_fn present, aw_display_wait_fn wait, void *ctx,
                              uint32_t known, uint32_t *dirty) {
    return prepare(d, pixels, palette, present, wait, ctx, true, known, dirty);
}

bool aw_display_band_store(aw_display_compact *d, unsigned band, const uint8_t *source) {
    uint8_t *packed = band_buffer(d);
    unsigned size = pack_band(source, packed, BAND_BYTES - 1);
    if (size) source = packed;
    else size = BAND_BYTES;
    if (!aw_assets_write_direct(d->assets, d->external_base + band * BAND_BYTES, source, size)) return false;
    d->band_sizes[band] = (uint16_t)size;
    return true;
}

bool aw_display_bands_write_one(aw_display_compact *d, const uint8_t *pixels, uint32_t *dirty) {
    if (!*dirty) return true;
    const unsigned band = (unsigned)__builtin_ctz(*dirty);
    if (!aw_display_band_store(d, band, pixels + band * BAND_BYTES)) {
        d->valid = false;
        return false;
    }
    *dirty &= *dirty - 1;
    return true;
}
