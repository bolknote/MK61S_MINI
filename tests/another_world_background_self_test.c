#include "../examples/portable-apps/ANOTHER/video.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint8_t *bytes; uint32_t size, page0_reads; } memory;
static bool bank(void *ctx, uint8_t id, uint32_t at, void *out, uint32_t size) {
    (void)ctx; (void)id; (void)at; (void)out; (void)size; return false;
}
static bool rd(void *ctx, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx; if (at > m->size || size > m->size - at) return false;
    if (at >= 8192 && at < 8192 + AW_VIDEO_PAGE_BYTES) m->page0_reads += size;
    memcpy(out, m->bytes + at, size); return true;
}
static bool wr(void *ctx, uint32_t at, const void *in, uint32_t size) {
    memory *m = ctx; if (at > m->size || size > m->size - at) return false;
    memcpy(m->bytes + at, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    (void)ctx; (void)pixels; (void)palette; return true;
}
static void evict_zero(aw_video *v) {
    assert(aw_video_fill(v, 1, 1)); assert(aw_video_fill(v, 2, 2)); assert(aw_video_fill(v, 3, 3));
}
static uint32_t random32(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s; }

static void test(unsigned capacity, unsigned split) {
    memory m = {calloc(1, 8192 + 4 * AW_VIDEO_PAGE_BYTES), 8192 + 4 * AW_VIDEO_PAGE_BYTES, 0};
    uint8_t *frame = malloc(AW_VIDEO_PAGE_BYTES), *spare = malloc(AW_VIDEO_PAGE_BYTES);
    uint8_t *cache = malloc(split ? split : capacity), *tail = split ? malloc(capacity - split) : NULL;
    uint8_t *snapshot = malloc(AW_VIDEO_PAGE_BYTES);
    aw_assets a; aw_video v;
    assert(m.bytes && frame && spare && cache && snapshot && (!split || tail));
    uint8_t list[21] = {0}; list[7] = 1; list[14] = 0x20; list[18] = 0x20; list[20] = 0xFF;
    assert(aw_assets_init(&a, list, sizeof(list), m.size, &m, bank, rd, wr));
    assert(aw_video_init(&v, &a, 8192, frame, present, &m));
    assert(aw_video_use_spare(&v, spare));
    if (split) assert(aw_video_use_background_split(&v, cache, split, tail, capacity - split));
    else assert(aw_video_use_background(&v, cache, capacity));

    assert(aw_video_fill(&v, 0, 4)); evict_zero(&v);
    assert(v.background_attempted && v.background_valid == (capacity >= 800));
    unsigned reads = m.page0_reads;
    assert(aw_video_copy(&v, 0, 2, 0) && aw_video_select(&v, 2));
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) assert(v.pixels[i] == 0x44);
    if (capacity >= 800) assert(m.page0_reads == reads); else assert(m.page0_reads > reads);

    assert(aw_video_fill(&v, 0, 5)); assert(!v.background_valid && !v.background_attempted);
    evict_zero(&v); assert(v.background_valid == (capacity >= 800));
    const uint8_t polygon[] = {0xD1, 8, 8, 4, 8, 0, 8, 8, 0, 8, 0, 0};
    assert(aw_assets_write(&a, 240, polygon, sizeof(polygon)));
    assert(aw_video_fill(&v, 2, 2) && aw_video_select(&v, 2)); reads = m.page0_reads;
    assert(aw_video_polygon(&v, 240, sizeof(polygon), 0, 64, 160, 100));
    assert((v.pixels[100 * AW_VIDEO_STRIDE + 80] >> 4) == 5);
    if (capacity >= 800) assert(m.page0_reads == reads);

    /* Mixed runs and literals; both vertical scroll directions must reproduce
     * the full source rows when the compact cache serves a page copy. */
    assert(aw_video_fill(&v, 0, 0) && aw_video_select(&v, 0));
    const uint8_t pattern[8] = {0x81, 0x18, 0xAA, 0x11, 0x42, 0x24, 0x80, 0xFF};
    for (unsigned y = 0; y <= 192; y += 16) for (unsigned x = 0; x < 40; x += 10)
        assert(aw_video_char(&v, x, y, (uint8_t)(1 + (x + y) % 15), pattern));
    memcpy(snapshot, v.pixels, AW_VIDEO_PAGE_BYTES); evict_zero(&v);
    if (capacity >= 6144) assert(v.background_valid);
    assert(aw_video_fill(&v, 2, 10) && aw_video_copy(&v, 0x80, 2, 4) && aw_video_select(&v, 2));
    for (unsigned i = 0; i < 4 * AW_VIDEO_STRIDE; ++i) assert(v.pixels[i] == 0xAA);
    assert(!memcmp(v.pixels + 4 * AW_VIDEO_STRIDE, snapshot, AW_VIDEO_PAGE_BYTES - 4 * AW_VIDEO_STRIDE));
    assert(aw_video_fill(&v, 2, 10) && aw_video_copy(&v, 0x80, 2, -3) && aw_video_select(&v, 2));
    assert(!memcmp(v.pixels, snapshot + 3 * AW_VIDEO_STRIDE, AW_VIDEO_PAGE_BYTES - 3 * AW_VIDEO_STRIDE));
    for (unsigned i = AW_VIDEO_PAGE_BYTES - 3 * AW_VIDEO_STRIDE; i < AW_VIDEO_PAGE_BYTES; ++i) assert(v.pixels[i] == 0xAA);

    assert(aw_video_fill(&v, 0, 0) && aw_video_select(&v, 0));
    uint32_t seed = 0x7f6a39c2;
    for (unsigned y = 0; y <= 192; y += 8) for (unsigned x = 0; x < 40; ++x) {
        uint8_t glyph[8]; for (unsigned i = 0; i < 8; ++i) glyph[i] = (uint8_t)(random32(&seed) >> 24);
        assert(aw_video_char(&v, x, y, (uint8_t)(1 + (x + y) % 15), glyph));
    }
    memcpy(snapshot, v.pixels, AW_VIDEO_PAGE_BYTES); evict_zero(&v);
    assert(v.background_attempted && !v.background_valid);
    reads = m.page0_reads; assert(aw_video_copy(&v, 0, 2, 0) && aw_video_select(&v, 2));
    assert(!memcmp(v.pixels, snapshot, AW_VIDEO_PAGE_BYTES) && m.page0_reads > reads);
    assert(aw_video_flush(&v));
    free(snapshot); free(tail); free(cache); free(spare); free(frame); free(m.bytes);
}
int main(void) {
    const unsigned splits[] = {1, 2, 3, 15, 64, 127, 128, 129, 511, 1023, 4095, 4096, 4097, 6143};
    test(6144, 0); test(100, 0);
    for (unsigned i = 0; i < sizeof(splits) / sizeof(splits[0]); ++i) test(6144, splits[i]);
    puts("Compressed background, split boundaries and PSRAM fallback passed"); return 0;
}
