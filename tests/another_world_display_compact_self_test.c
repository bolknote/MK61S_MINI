#include "../examples/portable-apps/ANOTHER/display_compact.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint16_t pixels[320 * 200]; unsigned calls, bytes, clears; bool fail; } panel;
static bool send_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                      const uint8_t *pixels, const uint16_t *palette, bool clear) {
    panel *p = ctx;
    assert(!(x & 1) && !(width & 1) && width && height && height <= 80);
    assert(x + width <= 320 && y + height <= 200 && width * height / 2 <= 12800);
    ++p->calls; p->bytes += width * height / 2; p->clears += clear;
    if (p->fail) return false;
    for (unsigned row = 0; row < height; ++row) for (unsigned col = 0; col < width; ++col) {
        uint8_t packed = pixels[row * (width / 2) + col / 2];
        unsigned index = (packed >> ((col & 1) ? 0 : 4)) & 15;
        p->pixels[(y + row) * 320 + x + col] = palette[index];
    }
    return true;
}
static void equal(const panel *p, const uint8_t *frame, const uint16_t *palette) {
    for (unsigned i = 0; i < 320u * 200u; ++i) {
        unsigned index = (frame[i / 2] >> ((i & 1) ? 0 : 4)) & 15;
        assert(p->pixels[i] == palette[index]);
    }
}
static uint32_t random32(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s; }
static bool rd(void *ctx, uint32_t offset, void *data, uint32_t size) {
    memcpy(data, (uint8_t *)ctx + offset, size); return true;
}
static bool wr(void *ctx, uint32_t offset, const void *data, uint32_t size) {
    memcpy((uint8_t *)ctx + offset, data, size); return true;
}
static void run(unsigned capacity, bool shared_scratch) {
    uint8_t *frame = calloc(1, AW_VIDEO_PAGE_BYTES), *previous = malloc(capacity);
    const unsigned scratch_bytes = shared_scratch ? capacity : 4096;
    uint8_t *scratch = shared_scratch ? previous : malloc(scratch_bytes), *store = calloc(1, AW_VIDEO_PAGE_BYTES);
    panel *p = calloc(1, sizeof(*p)); assert(frame && previous && scratch && store && p);
    aw_assets a = {0}; a.capacity=AW_VIDEO_PAGE_BYTES; a.ctx=store; a.store_read=rd; a.store_write=wr;
    uint16_t palette[16]; for (unsigned i = 0; i < 16; ++i) palette[i] = (uint16_t)(i * 0x1111);
    aw_display_compact d; assert(aw_display_compact_init(&d,&a,0,previous,capacity,scratch,scratch_bytes));
    if (shared_scratch)
        assert(!aw_display_compact_init(&d,&a,0,previous,capacity,previous,capacity + 1));
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p));
    unsigned calls=p->calls; assert(calls >= 3 && p->bytes == AW_VIDEO_PAGE_BYTES && p->clears == 1); equal(p, frame, palette);
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p) && p->calls == calls);
    frame[47 * AW_VIDEO_STRIDE + 35] ^= 0x10;
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p));
    assert(p->calls == calls + 1 && p->bytes == AW_VIDEO_PAGE_BYTES + 1); equal(p, frame, palette);
    palette[3] ^= 0x1234;
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p));
    assert(p->bytes == 2 * AW_VIDEO_PAGE_BYTES + 1); equal(p, frame, palette);
    frame[50] ^= 1; p->fail = true;
    assert(!aw_display_compact_present(&d, frame, palette, send_rect, p));
    p->fail = false; calls = p->calls;
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p));
    assert(p->calls > calls + 2 && p->clears == 2); equal(p, frame, palette);
    uint32_t random = 0xA613u;
    /* An incompressible picture must use PSRAM; a later simple picture must
     * switch back to the borrowed framebuffer without losing any pixels. */
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) frame[i] = (uint8_t)(random32(&random) >> 24);
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p) && d.external);
    equal(p, frame, palette); calls = p->calls;
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p) && p->calls == calls);
    memset(frame, 0, AW_VIDEO_PAGE_BYTES);
    assert(aw_display_compact_present(&d, frame, palette, send_rect, p)); equal(p, frame, palette);
    if (capacity >= 800) assert(!d.external);
    for (unsigned iteration = 0; iteration < 1000; ++iteration) {
        unsigned changes = iteration % 11 == 0 ? 1200 : 1 + iteration % 50;
        for (unsigned j = 0; j < changes; ++j)
            frame[random32(&random) % AW_VIDEO_PAGE_BYTES] ^= (uint8_t)(1u << (random32(&random) & 7));
        if (iteration % 127 == 0) palette[iteration % 16] ^= 0x421;
        assert(aw_display_compact_present(&d, frame, palette, send_rect, p));
        equal(p, frame, palette);
    }
    if (capacity==400) assert(d.external);
    free(store); if (!shared_scratch) free(scratch); free(p); free(previous); free(frame);
}
static void scrolled(unsigned capacity) {
    uint8_t *storage = malloc(AW_VIDEO_PAGE_BYTES + 1), *previous = malloc(capacity);
    uint8_t *store = calloc(1, AW_VIDEO_PAGE_BYTES), *old_frame = malloc(AW_VIDEO_PAGE_BYTES);
    panel *p = calloc(1, sizeof(*p));
    uint16_t *rotated = malloc(sizeof(p->pixels));
    assert(storage && previous && store && old_frame && p && rotated);
    uint8_t *frame = storage + 1; /* Packed row scans must also accept unaligned frames. */
    aw_assets a = {0}; a.capacity = AW_VIDEO_PAGE_BYTES; a.ctx = store; a.store_read = rd; a.store_write = wr;
    aw_display_compact d;
    assert(aw_display_compact_init(&d, &a, 0, previous, capacity, previous, capacity));
    uint16_t palette[16];
    for (unsigned n = 0; n < 16; ++n) palette[n] = (uint16_t)(n * 0x1111);
    uint32_t random = 17;
    for (unsigned step = 0; step < 150; ++step) {
        const unsigned shifts[] = {0, 1, 199, 2, 198, 17, 183, 99, 101};
        const unsigned shift = shifts[step % 9];
        const bool only_scroll = step % 10 == 1 && step % 31 != 0;
        if (only_scroll) memcpy(old_frame, frame, AW_VIDEO_PAGE_BYTES);
        const unsigned calls = p->calls;
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y) {
            memcpy(rotated + y * 320, p->pixels + ((y + shift) % AW_VIDEO_HEIGHT) * 320, 640);
            for (unsigned x = 0; x < AW_VIDEO_STRIDE; ++x)
                frame[y * AW_VIDEO_STRIDE + x] = only_scroll ? old_frame[((y + shift) % AW_VIDEO_HEIGHT) * AW_VIDEO_STRIDE + x]
                    : step < 75 ? (uint8_t)((y / 4 + x / 8 + step) * 17u)
                    : (uint8_t)(random32(&random) >> 24);
        }
        memcpy(p->pixels, rotated, sizeof(p->pixels));
        if (step % 31 == 0) palette[step % 16] ^= 0x421;
        assert(aw_display_compact_present_scrolled(&d, frame, palette, shift, send_rect, p));
        equal(p, frame, palette);
        if (only_scroll) assert(p->calls == calls);
    }
    assert(d.external);
    assert(!aw_display_compact_present_scrolled(&d, frame, palette, AW_VIDEO_HEIGHT, send_rect, p));
    free(rotated); free(p); free(old_frame); free(store); free(previous); free(storage);
}
int main(void) {
    run(12800, false); run(400, false); run(12800, true); run(3200, true);
    scrolled(12800); scrolled(3200);
    puts("Another World compact display tests passed"); return 0;
}
