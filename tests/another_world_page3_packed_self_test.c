#include "../examples/portable-apps/ANOTHER/video.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { BASE = 8192, PACKED = BASE + 5 * AW_VIDEO_PAGE_BYTES,
       CAPACITY = PACKED + AW_VIDEO_PAGE3_PACKED_BYTES };
typedef struct { uint8_t *bytes; unsigned page_reads, packed_reads; bool fail_packed_read; } memory;
static bool bank(void *ctx, uint8_t id, uint32_t at, void *out, uint32_t size) {
    (void)ctx; (void)id; (void)at; (void)out; (void)size; return false;
}
static bool rd(void *ctx, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx; if (at > CAPACITY || size > CAPACITY - at) return false;
    if (at >= BASE + 3 * AW_VIDEO_PAGE_BYTES && at < BASE + 4 * AW_VIDEO_PAGE_BYTES) m->page_reads += size;
    if (at < CAPACITY && at + size > PACKED) {
        if (m->fail_packed_read) return false;
        m->packed_reads += size;
    }
    memcpy(out, m->bytes + at, size); return true;
}
static bool wr(void *ctx, uint32_t at, const void *in, uint32_t size) {
    memory *m = ctx; if (at > CAPACITY || size > CAPACITY - at) return false;
    memcpy(m->bytes + at, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    (void)ctx; (void)pixels; (void)palette; return true;
}
static uint32_t random32(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s; }
static void evict3(aw_video *v) {
    assert(aw_video_fill(v, 0, 0)); assert(aw_video_fill(v, 1, 1)); assert(aw_video_fill(v, 2, 2));
    assert(v->resident_page != 3 && (!v->spare_valid || v->spare_page != 3));
}
static void reuse3(aw_video *v) {
    assert(aw_video_copy(v, 3, 1, 0));
    assert(v->page3_seen_copy && !v->page3_packed_attempted);
    assert(aw_video_copy(v, 3, 2, 0));
    assert(v->page3_packed_attempted);
}
int main(void) {
    memory m = {calloc(1, CAPACITY), 0, 0, false};
    uint8_t *frame = malloc(AW_VIDEO_PAGE_BYTES), *spare = malloc(AW_VIDEO_PAGE_BYTES);
    uint8_t *snapshot = malloc(AW_VIDEO_PAGE_BYTES); aw_assets a; aw_video v;
    assert(m.bytes && frame && spare && snapshot);
    uint8_t list[21] = {0}; list[7] = 1; list[14] = 0x20; list[18] = 0x20; list[20] = 0xFF;
    assert(aw_assets_init(&a, list, sizeof(list), CAPACITY, &m, bank, rd, wr));
    assert(aw_video_init(&v, &a, BASE, frame, present, &m));
    assert(aw_video_use_spare(&v, spare));
    assert(!aw_video_use_packed_page3(&v, BASE + 4 * AW_VIDEO_PAGE_BYTES, 8192));
    assert(!aw_video_use_packed_page3(&v, PACKED, 8193));
    assert(aw_video_use_packed_page3(&v, PACKED, 8192));
    assert(!aw_video_use_packed_page3(&v, PACKED, 8192));

    /* Mixed runs and literal packets cross both 1 KiB buffer boundaries. */
    assert(aw_video_fill(&v, 3, 0) && aw_video_select(&v, 3));
    uint32_t seed = 0xd150e002;
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i)
        v.pixels[i] = (i % 37 < 5) ? (uint8_t)(random32(&seed) >> 24) : 0x44;
    memcpy(snapshot, v.pixels, AW_VIDEO_PAGE_BYTES); reuse3(&v); evict3(&v);
    assert(v.page3_packed_valid && v.page3_packed_size > 2048 && v.page3_packed_size < 8192);
    unsigned old_page = m.page_reads, old_packed = m.packed_reads;
    assert(aw_video_copy(&v, 3, 1, 0) && aw_video_select(&v, 1));
    assert(!memcmp(v.pixels, snapshot, AW_VIDEO_PAGE_BYTES));
    assert(m.page_reads == old_page && m.packed_reads > old_packed);

    /* Changing page 3 invalidates the compressed copy and creates a new one. */
    assert(aw_video_fill(&v, 3, 6) && !v.page3_packed_valid && !v.page3_packed_attempted);
    reuse3(&v); evict3(&v); assert(v.page3_packed_valid);
    assert(aw_video_copy(&v, 3, 1, 0) && aw_video_select(&v, 1));
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) assert(v.pixels[i] == 0x66);

    /* Scrolled copies retain the original source/destination semantics. */
    evict3(&v); assert(aw_video_fill(&v, 1, 5));
    assert(aw_video_copy(&v, 0x83, 1, 4) && aw_video_select(&v, 1));
    for (unsigned i = 0; i < 4 * AW_VIDEO_STRIDE; ++i) assert(v.pixels[i] == 0x55);
    for (unsigned i = 4 * AW_VIDEO_STRIDE; i < AW_VIDEO_PAGE_BYTES; ++i) assert(v.pixels[i] == 0x66);

    /* A truncated compressed stream falls back to the intact raw PSRAM page. */
    evict3(&v); assert(v.page3_packed_valid); v.page3_packed_size = 1; old_page = m.page_reads;
    assert(aw_video_copy(&v, 3, 1, 0) && aw_video_select(&v, 1));
    assert(!v.page3_packed_valid && m.page_reads > old_page);
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) assert(v.pixels[i] == 0x66);

    /* A page too large for the compressed area must also use the raw copy. */
    assert(aw_video_fill(&v, 3, 0) && aw_video_select(&v, 3));
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) v.pixels[i] = (uint8_t)(random32(&seed) >> 24);
    memcpy(snapshot, v.pixels, AW_VIDEO_PAGE_BYTES); reuse3(&v); evict3(&v);
    assert(v.page3_packed_attempted && !v.page3_packed_valid); old_page = m.page_reads;
    assert(aw_video_copy(&v, 3, 1, 0) && aw_video_select(&v, 1));
    assert(!memcmp(v.pixels, snapshot, AW_VIDEO_PAGE_BYTES) && m.page_reads > old_page);

    /* Exercise repeated invalidation and both sides of the 8 KiB limit with
     * mixed run lengths and literal bytes. */
    bool saw_packed = false, saw_fallback = false;
    for (unsigned iteration = 0; iteration < 32; ++iteration) {
        assert(aw_video_fill(&v, 3, 0) && aw_video_select(&v, 3));
        for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i)
            v.pixels[i] = i % 37 < iteration ? (uint8_t)(random32(&seed) >> 24) : (uint8_t)iteration;
        memcpy(snapshot, v.pixels, AW_VIDEO_PAGE_BYTES); reuse3(&v); evict3(&v);
        const bool packed = v.page3_packed_valid;
        saw_packed |= packed; saw_fallback |= !packed; old_page = m.page_reads;
        assert(aw_video_copy(&v, 3, 1, 0) && aw_video_select(&v, 1));
        assert(!memcmp(v.pixels, snapshot, AW_VIDEO_PAGE_BYTES));
        if (packed) assert(m.page_reads == old_page); else assert(m.page_reads > old_page);
    }
    assert(saw_packed && saw_fallback);

    /* A real PSRAM error is propagated instead of being silently ignored. */
    assert(aw_video_fill(&v, 3, 4)); reuse3(&v); evict3(&v); assert(v.page3_packed_valid);
    assert(aw_assets_flush(&a));
    for (unsigned i = 0; i < AW_ASSET_CACHE_SLOTS; ++i) a.cache[i].valid = false;
    a.recent = NULL; m.fail_packed_read = true;
    assert(!aw_video_copy(&v, 3, 1, 0) && v.fault && a.fault);

    free(snapshot); free(spare); free(frame); free(m.bytes);
    puts("Page 3 compressed PSRAM cache and fallback passed"); return 0;
}
