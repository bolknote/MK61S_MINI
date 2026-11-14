#include "../examples/portable-apps/ANOTHER/video.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint8_t *bytes; uint32_t size; unsigned presents; uint8_t first; } memory;
static bool bank(void *ctx, uint8_t id, uint32_t offset, void *out, uint32_t size) {
    (void)ctx; (void)id; (void)offset; (void)out; (void)size; return false;
}
static bool read_store(void *ctx, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx;
    if (at > m->size || size > m->size - at) return false;
    memcpy(out, m->bytes + at, size); return true;
}
static bool write_store(void *ctx, uint32_t at, const void *in, uint32_t size) {
    memory *m = ctx;
    if (at > m->size || size > m->size - at) return false;
    memcpy(m->bytes + at, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    memory *m = ctx; ++m->presents; m->first = pixels[0]; (void)palette; return true;
}
static unsigned pixel(const uint8_t *p, unsigned x, unsigned y) {
    const uint8_t b = p[y * AW_VIDEO_STRIDE + x / 2]; return x & 1 ? b & 15 : b >> 4;
}
static void run(bool two_pages) {
    memory m = {calloc(1, 8192 + 4 * AW_VIDEO_PAGE_BYTES), 8192 + 4 * AW_VIDEO_PAGE_BYTES, 0, 0};
    uint8_t *frame = malloc(AW_VIDEO_PAGE_BYTES), *spare = two_pages ? malloc(AW_VIDEO_PAGE_BYTES) : NULL;
    aw_assets a; aw_video v;
    assert(m.bytes && frame && (!two_pages || spare));
    uint8_t list[21] = {0}; list[7] = 1; list[14] = 0x20; list[18] = 0x20; list[20] = 0xFF;
    assert(aw_assets_init(&a, list, sizeof(list), m.size, &m, bank, read_store, write_store));
    assert(aw_video_init(&v, &a, 8192, frame, present, &m));
    if (two_pages) assert(aw_video_use_spare(&v, spare));
    assert(aw_video_fill(&v, 0, 1));
    assert(aw_video_fill(&v, 2, 2));
    assert(aw_video_copy(&v, 0, 2, 0));
    assert(aw_video_select(&v, 2) && pixel(v.pixels, 10, 10) == 1);
    assert(aw_video_fill(&v, 1, 3));
    assert(aw_video_show(&v, 0xFF));
    assert(m.presents == 1 && m.first == 0x33 && v.front_page == 1 && v.back_page == 2);
    assert(aw_video_copy(&v, 1, 3, 0));
    assert(aw_video_select(&v, 3) && pixel(v.pixels, 20, 20) == 3);
    assert(aw_video_fill(&v, 3, 0));
    assert(aw_video_copy(&v, 0x81, 3, 4));
    assert(aw_video_select(&v, 3) && pixel(v.pixels, 20, 3) == 0 && pixel(v.pixels, 20, 4) == 3);
    const uint8_t square[] = {0xC5, 8, 8, 4, 8, 0, 8, 8, 0, 8, 0, 0};
    assert(aw_assets_write(&a, 100, square, sizeof(square)));
    assert(aw_video_fill(&v, 2, 0)); assert(aw_video_select(&v, 2));
    assert(aw_video_polygon(&v, 100, sizeof(square), 0, 64, 160, 100));
    assert(pixel(v.pixels, 156, 96) == 5 && pixel(v.pixels, 164, 103) == 5);
    assert(pixel(v.pixels, 155, 96) == 0 && pixel(v.pixels, 160, 104) == 0);
    const uint8_t dot[] = {0xD0, 0, 1, 4, 0, 0, 0, 0, 0, 0, 0, 0};
    assert(aw_assets_write(&a, 120, dot, sizeof(dot)));
    assert(aw_video_polygon(&v, 120, sizeof(dot), 0, 64, 160, 100));
    assert(pixel(v.pixels, 160, 100) == 13 && pixel(v.pixels, 159, 100) == 5);
    uint8_t pal[32] = {0}; pal[2] = 0x0F; pal[3] = 0xF0;
    assert(aw_assets_write(&a, 200, pal, sizeof(pal)));
    assert(aw_video_palette(&v, 200, 32, 0) && v.palette[1] == 0xFFE0);
    const uint8_t glyph[8] = {0x81,0,0,0,0,0,0,0};
    assert(aw_video_char(&v, 0, 0, 7, glyph));
    assert(pixel(v.pixels, 0, 0) == 7 && pixel(v.pixels, 7, 0) == 7 && pixel(v.pixels, 1, 0) == 0);
    /* Page zero may be dirty in the second slot when a polygon uses it as
     * its source; the copied pixels and a later explicit flush must agree. */
    const uint8_t from_page_zero[] = {0xD1, 8, 8, 4, 8, 0, 8, 8, 0, 8, 0, 0};
    assert(aw_assets_write(&a, 240, from_page_zero, sizeof(from_page_zero)));
    assert(aw_video_fill(&v, 0, 4) && aw_video_fill(&v, 2, 2) && aw_video_select(&v, 2));
    assert(aw_video_polygon(&v, 240, sizeof(from_page_zero), 0, 64, 160, 100));
    assert(pixel(v.pixels, 160, 100) == 4 && pixel(v.pixels, 10, 10) == 2);
    assert(aw_video_flush(&v));
    uint8_t value = 0;
    assert(aw_assets_read(&a, 8192, &value, 1) && value == 0x44);
    assert(aw_assets_read(&a, 8192 + 2 * AW_VIDEO_PAGE_BYTES + 100 * AW_VIDEO_STRIDE + 80, &value, 1));
    assert((value >> 4) == 4);
    assert(!aw_video_polygon(&v, 100, 2, 0, 64, 0, 0) && v.fault);
    free(spare); free(frame); free(m.bytes);
}
int main(void) { run(false); run(true); puts("Another World video tests passed"); return 0; }
