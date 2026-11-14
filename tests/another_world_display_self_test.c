#include "../examples/portable-apps/ANOTHER/display.h"
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
int main(void) {
    uint8_t *frame = calloc(1, AW_VIDEO_PAGE_BYTES), *previous = malloc(AW_VIDEO_PAGE_BYTES);
    panel *p = calloc(1, sizeof(*p)); assert(frame && previous && p);
    uint16_t palette[16]; for (unsigned i = 0; i < 16; ++i) palette[i] = (uint16_t)(i * 0x1111);
    aw_display d; aw_display_init(&d, previous);
    assert(aw_display_present(&d, frame, palette, send_rect, p));
    assert(p->calls == 3 && p->bytes == AW_VIDEO_PAGE_BYTES && p->clears == 1); equal(p, frame, palette);
    assert(aw_display_present(&d, frame, palette, send_rect, p) && p->calls == 3);
    frame[47 * AW_VIDEO_STRIDE + 35] ^= 0x10;
    assert(aw_display_present(&d, frame, palette, send_rect, p));
    assert(p->calls == 4 && p->bytes == AW_VIDEO_PAGE_BYTES + 1); equal(p, frame, palette);
    palette[3] ^= 0x1234;
    assert(aw_display_present(&d, frame, palette, send_rect, p));
    assert(p->calls == 7 && p->bytes == 2 * AW_VIDEO_PAGE_BYTES + 1); equal(p, frame, palette);
    frame[50] ^= 1; p->fail = true;
    assert(!aw_display_present(&d, frame, palette, send_rect, p));
    p->fail = false; unsigned calls = p->calls;
    assert(aw_display_present(&d, frame, palette, send_rect, p));
    assert(p->calls == calls + 3 && p->clears == 2); equal(p, frame, palette);
    uint32_t random = 0xA613u;
    for (unsigned iteration = 0; iteration < 1000; ++iteration) {
        unsigned changes = iteration % 11 == 0 ? 1200 : 1 + iteration % 50;
        for (unsigned j = 0; j < changes; ++j)
            frame[random32(&random) % AW_VIDEO_PAGE_BYTES] ^= (uint8_t)(1u << (random32(&random) & 7));
        if (iteration % 127 == 0) palette[iteration % 16] ^= 0x421;
        assert(aw_display_present(&d, frame, palette, send_rect, p));
        equal(p, frame, palette);
    }
    free(p); free(previous); free(frame);
    puts("Another World partial display tests passed"); return 0;
}
