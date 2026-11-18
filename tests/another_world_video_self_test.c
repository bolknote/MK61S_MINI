#include "../examples/portable-apps/ANOTHER/video.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint8_t *bytes; uint32_t size; unsigned presents; uint8_t first; uint32_t read_bytes, write_bytes; } memory;
static bool bank(void *ctx, uint8_t id, uint32_t offset, void *out, uint32_t size) {
    (void)ctx; (void)id; (void)offset; (void)out; (void)size; return false;
}
static bool read_store(void *ctx, uint32_t at, void *out, uint32_t size) {
    memory *m = ctx;
    if (at > m->size || size > m->size - at) return false;
    m->read_bytes += size;
    memcpy(out, m->bytes + at, size); return true;
}
static bool write_store(void *ctx, uint32_t at, const void *in, uint32_t size) {
    memory *m = ctx;
    if (at > m->size || size > m->size - at) return false;
    m->write_bytes += size;
    memcpy(m->bytes + at, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    memory *m = ctx; ++m->presents; m->first = pixels[0]; (void)palette; return true;
}
static unsigned pixel(const uint8_t *p, unsigned x, unsigned y) {
    const uint8_t b = p[y * AW_VIDEO_STRIDE + x / 2]; return x & 1 ? b & 15 : b >> 4;
}
static void run(bool two_pages) {
    aw_asset_entry entries[AW_ASSET_LIMIT];
    memory m = {.bytes = calloc(1, 8192 + 4 * AW_VIDEO_PAGE_BYTES), .size = 8192 + 4 * AW_VIDEO_PAGE_BYTES};
    uint8_t *frame = malloc(AW_VIDEO_PAGE_BYTES), *spare = two_pages ? malloc(AW_VIDEO_PAGE_BYTES) : NULL;
    aw_assets a; aw_video v;
    aw_video_bands bands;
    assert(m.bytes && frame && (!two_pages || spare));
    uint8_t list[21] = {0}; list[7] = 1; list[14] = 0x20; list[18] = 0x20; list[20] = 0xFF;
    assert(aw_assets_init(&a, entries, list, sizeof(list), m.size, &m, bank, read_store, write_store));
    assert(aw_video_init(&v, &a, 8192, frame, present, &m));
    aw_video_track_bands(&v, &bands);
    if (two_pages) assert(aw_video_use_spare(&v, spare));
    const uint32_t before_fill = m.read_bytes;
    assert(aw_video_fill(&v, 0, 1));
    assert(aw_video_fill(&v, 2, 2));
    assert(m.read_bytes == before_fill);
    const unsigned resident_page = v.resident_page;
    assert(aw_video_set_draw_page(&v, 3) && v.draw_page == 3 && v.resident_page == resident_page);
    assert(m.read_bytes == before_fill);
    assert(aw_video_copy(&v, 2, 1, 0));
    assert(m.read_bytes - before_fill == (two_pages ? 0 : AW_VIDEO_PAGE_BYTES));
    assert(aw_video_copy(&v, 0, 2, 0));
    assert(!memcmp(bands.page[0], bands.page[2], sizeof(bands.page[0])));
    assert(aw_video_select(&v, 2) && pixel(v.pixels, 10, 10) == 1);
    assert(aw_video_fill(&v, 1, 3));
    assert(aw_video_show(&v, 0xFF));
    assert(m.presents == 1 && m.first == 0x33 && v.front_page == 1 && v.back_page == 2);
    assert(aw_video_copy(&v, 1, 3, 0));
    assert(aw_video_select(&v, 3) && pixel(v.pixels, 20, 20) == 3);
    assert(aw_video_fill(&v, 3, 0));
    assert(aw_video_copy(&v, 0x81, 3, 4));
    assert(v.page_scroll[3] == 4 && v.page_scroll[1] == 0);
    for (unsigned i = 0; i < AW_VIDEO_BANDS; ++i) assert(!bands.page[3][i]);
    assert(aw_video_select(&v, 3) && pixel(v.pixels, 20, 3) == 0 && pixel(v.pixels, 20, 4) == 3);
    assert(aw_video_copy(&v, 0x83, 3, -7) && v.page_scroll[3] == 197);
    assert(aw_video_copy(&v, 3, 1, 0) && v.page_scroll[1] == 197);
    assert(aw_video_fill(&v, 1, 3) && v.page_scroll[1] == 0);
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
    assert(!bands.page[2][0] && bands.page[2][1] == 1);
    assert(aw_video_char(&v, 1, 7, 7, glyph));
    assert(!bands.page[2][0] && !bands.page[2][1] && bands.page[2][2] == 1);
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
    if (two_pages) {
        /* A sub-byte edit to an evicted background must preserve its other
         * nibble, both SRAM pages and their exact band identities. */
        assert(aw_video_fill(&v, 0, 5) && aw_video_fill(&v, 3, 3) && aw_video_fill(&v, 1, 1));
        assert(aw_video_copy(&v, 0x83, 1, 0));
        assert(aw_video_flush(&v));
        const uint8_t page = v.resident_page, spare_page = v.spare_page;
        const uint32_t reads = m.read_bytes;
        assert(aw_video_set_draw_page(&v, 0));
        assert(aw_video_polygon(&v, 120, sizeof(dot), 0, 64, 161, 100));
        assert(v.resident_page == page && v.spare_page == spare_page);
        assert(m.read_bytes - reads < AW_VIDEO_PAGE_BYTES);
        assert(bands.page[0][12] == 0 && bands.page[0][11] == 6 && bands.page[1][12] == 4 && bands.page[3][12] == 4);
        assert(aw_video_flush(&v));
        assert(m.bytes[8192 + 100 * AW_VIDEO_STRIDE + 80] == 0x5D);
        assert(aw_video_copy(&v, 0, 2, 0));
        assert(v.spare_page == 3 && pixel(v.pixels, 161, 100) == 13);
        assert(aw_video_select(&v, 0) && pixel(v.pixels, 160, 100) == 5);

        /* Once the shake ends, holding page 3 here would write a whole
         * display page to PSRAM on every ordinary background copy. */
        assert(aw_video_fill(&v, 3, 3) && aw_video_fill(&v, 1, 1));
        assert(aw_video_flush(&v));
        const uint32_t writes = m.write_bytes;
        for (unsigned i = 0; i < 10; ++i) {
            const uint8_t dst = (i & 1u) ? 1 : 2;
            assert(aw_video_copy(&v, 0, dst, 0) && aw_video_show(&v, dst));
            assert(pixel(v.pixels, 161, 100) == 13);
        }
        assert(m.write_bytes == writes);
    }
    if (two_pages) {
        /* A whole-page change can drain over many LCD polls. If the game
         * redraws an already written band, the next flush must repair it. */
        assert(aw_video_fill(&v, 1, 7) && aw_video_fill(&v, 2, 8));
        const uint32_t before = m.write_bytes;
        assert(aw_video_write_one(&v));
        assert(m.write_bytes > before && m.write_bytes - before <= 2 * AW_VIDEO_BAND_ROWS * AW_VIDEO_STRIDE);
        assert(aw_video_fill(&v, 1, 9));
        assert(aw_video_flush(&v));
        for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) {
            assert(m.bytes[8192 + AW_VIDEO_PAGE_BYTES + i] == 0x99);
            assert(m.bytes[8192 + 2 * AW_VIDEO_PAGE_BYTES + i] == 0x88);
        }
        for (unsigned page = 0; page < 4; ++page) assert(aw_video_fill(&v, page, (uint8_t)(page + 1)));
        assert(aw_video_flush(&v));
        /* The evicted page matches first the overwritten page's backing,
         * then the other SRAM page's backing. Neither eviction needs I/O. */
        assert(aw_video_fill(&v, 0, 2) && aw_video_fill(&v, 3, 7));
        uint32_t written = m.write_bytes;
        assert(aw_video_fill(&v, 1, 9) && m.write_bytes == written);
        assert(aw_video_flush(&v));
        assert(aw_video_fill(&v, 0, 9) && aw_video_fill(&v, 1, 11));
        written = m.write_bytes;
        assert(aw_video_fill(&v, 2, 12) && m.write_bytes == written);
        assert(aw_video_flush(&v));
        const uint8_t expected[] = {0x99, 0xbb, 0xcc, 0x77};
        for (unsigned page = 0; page < 4; ++page)
            for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i)
                assert(m.bytes[v.page_base + page * AW_VIDEO_PAGE_BYTES + i] == expected[page]);
    }
    /* Saving the displayed page during LCD DMA must respect the batch limit.
     * A subsequent draw can change bands that have already reached PSRAM. */
    assert(aw_video_fill(&v, 1, 12) && aw_video_fill(&v, 2, 14));
    const uint32_t before_writeback = m.write_bytes;
    const unsigned early_bytes = two_pages ? 4 * AW_VIDEO_BAND_ROWS * AW_VIDEO_STRIDE : 0;
    assert(aw_video_write_displayed(&v, 0) && m.write_bytes == before_writeback);
    assert(aw_video_write_displayed(&v, 2) && m.write_bytes - before_writeback == early_bytes);
    const uint32_t backing = v.page_base + v.store_slot[2] * AW_VIDEO_PAGE_BYTES;
    assert(!memcmp(m.bytes + backing, v.pixels, early_bytes));
    assert(aw_video_fill(&v, 2, 3) && aw_video_flush(&v));
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i)
        assert(m.bytes[v.page_base + 2 * AW_VIDEO_PAGE_BYTES + i] == 0x33);
    bands.last_identity = UINT32_MAX - AW_VIDEO_BANDS + 1;
    assert(aw_video_show(&v, 2) && !aw_video_band_identities(&v));
    assert(!aw_video_polygon(&v, 100, 2, 0, 64, 0, 0) && v.fault);
    free(spare); free(frame); free(m.bytes);
}
int main(void) { run(false); run(true); puts("Another World video tests passed"); return 0; }
