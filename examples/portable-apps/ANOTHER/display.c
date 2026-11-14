#include "display.h"
#include <string.h>

#define BAND_ROWS 20u
#define MAX_ROWS 80u
/* A wider merged rectangle saves one display transaction. */
#define MERGE_EXTRA_PIXELS 400u
typedef struct { unsigned x0, x1, y0, y1; } rectangle;

void aw_display_init(aw_display *d, uint8_t *previous) {
    memset(d, 0, sizeof(*d)); d->previous = previous;
}

bool aw_display_present(aw_display *d, const uint8_t *pixels, const uint16_t *palette,
                        aw_display_rect_fn present, void *ctx) {
    if (!d || !d->previous || !pixels || !palette || !present || d->previous == pixels) return false;
    const bool full = !d->valid || memcmp(d->palette, palette, sizeof(d->palette)) != 0;
    rectangle rects[AW_VIDEO_HEIGHT / BAND_ROWS]; unsigned count = 0;
    if (full) {
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += MAX_ROWS) {
            unsigned bottom = y + MAX_ROWS;
            if (bottom > AW_VIDEO_HEIGHT) bottom = AW_VIDEO_HEIGHT;
            rects[count++] = (rectangle){0, AW_VIDEO_STRIDE, y, bottom};
        }
    } else for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += BAND_ROWS) {
        unsigned left = AW_VIDEO_STRIDE, right = 0, top = AW_VIDEO_HEIGHT, bottom = 0;
        for (unsigned row = y; row < y + BAND_ROWS; ++row) {
            const uint8_t *now = pixels + row * AW_VIDEO_STRIDE;
            const uint8_t *old = d->previous + row * AW_VIDEO_STRIDE;
            if (!memcmp(now, old, AW_VIDEO_STRIDE)) continue;
            if (top == AW_VIDEO_HEIGHT) top = row;
            bottom = row + 1;
            for (unsigned x = 0; x < left; ++x) if (now[x] != old[x]) { left = x; break; }
            for (unsigned x = AW_VIDEO_STRIDE; x > right; --x)
                if (now[x - 1] != old[x - 1]) { right = x; break; }
        }
        if (top == AW_VIDEO_HEIGHT) continue;
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
    for (unsigned i = 0; i < count; ++i) {
        const rectangle r = rects[i];
        const unsigned row_bytes = r.x1 - r.x0, height = r.y1 - r.y0;
        for (unsigned row = 0; row < height; ++row)
            memcpy(d->previous + row * row_bytes,
                   pixels + (r.y0 + row) * AW_VIDEO_STRIDE + r.x0, row_bytes);
        if (!present(ctx, 2 * r.x0, r.y0, 2 * row_bytes, height,
                     d->previous, palette, clear && i == 0)) {
            d->valid = false; return false;
        }
    }
    if (count) memcpy(d->previous, pixels, AW_VIDEO_PAGE_BYTES);
    memcpy(d->palette, palette, sizeof(d->palette));
    d->valid = true; return true;
}
