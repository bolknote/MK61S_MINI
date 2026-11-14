#include "display_compact.h"
#include <string.h>

#define BAND_ROWS 10u
#define MAX_ROWS 80u
#define MERGE_EXTRA_PIXELS 800u
typedef struct {
    unsigned x0, x1, y0, y1;
} rectangle;

bool aw_display_compact_init(aw_display_compact *d, aw_assets *a, uint32_t base, uint8_t *previous,
                             uint32_t capacity, uint8_t *scratch, uint32_t scratch_bytes) {
    if (!d || !a || !previous || !scratch || (previous == scratch && scratch_bytes > capacity) ||
        capacity > UINT16_MAX ||
        scratch_bytes < 3200 || scratch_bytes > 12800 || base > a->capacity ||
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

bool aw_display_compact_present(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                                aw_display_rect_fn present, void *ctx) {
    if (!d || !pixels || !palette || !present || pixels == d->previous || pixels == d->scratch)
        return false;
    const bool full = !d->valid || memcmp(d->palette, palette, sizeof(d->palette));
    rectangle rects[AW_VIDEO_HEIGHT / BAND_ROWS];
    unsigned count = 0;
    if (full) {
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += MAX_ROWS) {
            unsigned end = y + MAX_ROWS;
            if (end > AW_VIDEO_HEIGHT)
                end = AW_VIDEO_HEIGHT;
            rects[count++] = (rectangle){0, AW_VIDEO_STRIDE, y, end};
        }
    } else
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += BAND_ROWS) {
            unsigned left = AW_VIDEO_STRIDE, right = 0, top = AW_VIDEO_HEIGHT, bottom = 0;
            uint8_t row_previous[AW_VIDEO_STRIDE];
            if (d->external && !aw_assets_read(d->assets, d->external_base + y * AW_VIDEO_STRIDE, d->scratch,
                                               BAND_ROWS * AW_VIDEO_STRIDE)) {
                d->valid = false;
                return false;
            }
            if (d->external)
                aw_assets_progress(d->assets);
            for (unsigned row = y; row < y + BAND_ROWS; ++row) {
                const uint8_t *now = pixels + row * AW_VIDEO_STRIDE;
                const uint8_t *old = d->scratch + (row - y) * AW_VIDEO_STRIDE;
                if (!d->external) {
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
    const bool clear = !d->valid;
    unsigned transfers = 0;
    for (unsigned i = 0; i < count; ++i) {
        const rectangle r = rects[i];
        const unsigned row_bytes = r.x1 - r.x0;
        const unsigned max_rows = d->scratch_bytes / row_bytes;
        for (unsigned y = r.y0; y < r.y1;) {
            unsigned rows = r.y1 - y;
            if (rows > max_rows)
                rows = max_rows;
            for (unsigned row = 0; row < rows; ++row)
                memcpy(d->scratch + row * row_bytes, pixels + (y + row) * AW_VIDEO_STRIDE + r.x0, row_bytes);
            if (!present(ctx, 2 * r.x0, y, 2 * row_bytes, rows, d->scratch, palette, clear && !transfers)) {
                d->valid = false;
                return false;
            }
            ++transfers;
            y += rows;
        }
    }
    if (count) {
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
