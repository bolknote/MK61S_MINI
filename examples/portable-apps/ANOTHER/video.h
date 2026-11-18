#ifndef MK61_ANOTHER_VIDEO_H
#define MK61_ANOTHER_VIDEO_H

#include "assets.h"

#define AW_VIDEO_WIDTH 320u
#define AW_VIDEO_HEIGHT 200u
#define AW_VIDEO_STRIDE 160u
#define AW_VIDEO_PAGE_BYTES (AW_VIDEO_STRIDE * AW_VIDEO_HEIGHT)
#define AW_VIDEO_INTERP_SLOTS 32u
#define AW_VIDEO_PAGE3_PACKED_BYTES 8192u
/* The shipping image retains the resource cache within its SRAM
 * budget by omitting this optional codec. Comparison builds can enable it. */
#ifndef AW_VIDEO_PACKED_CACHE
#define AW_VIDEO_PACKED_CACHE 0
#endif
#define AW_VIDEO_BAND_ROWS 8u
#define AW_VIDEO_BANDS (AW_VIDEO_HEIGHT / AW_VIDEO_BAND_ROWS)

/* Nonzero identities describe exact index bytes. Full copies retain the
 * source identities and drawing invalidates the affected bands. */
typedef struct {
    uint32_t page[4][AW_VIDEO_BANDS];
    uint32_t stored[4][AW_VIDEO_BANDS]; /* Last confirmed bytes in each PSRAM band. */
    uint32_t last_identity;
} aw_video_bands;

typedef bool (*aw_video_present_fn)(void *ctx, const uint8_t *pixels, const uint16_t *palette);

typedef struct {
    aw_assets *assets;
    uint8_t *pixels; /* Current SRAM page; may swap with the caller's spare. */
    uint32_t page_base, shape_base, shape_size;
    uint16_t palette[16], interp[AW_VIDEO_INTERP_SLOTS];
    uint8_t draw_page, front_page, back_page, resident_page;
    uint8_t page_scroll[4]; /* Circular row displacement carried by page copies. */
    bool resident_valid, dirty, fault;
    uint8_t *spare;
    uint8_t spare_page;
    bool spare_valid, spare_dirty, last_copy_scrolled_scratch;
    uint8_t *background, *background_tail;
    uint16_t background_split, background_capacity, background_size, background_offsets[AW_VIDEO_HEIGHT + 1];
    bool background_valid, background_attempted;
    uint32_t page3_packed_base;
    uint16_t page3_packed_size, page3_packed_capacity;
    bool page3_packed_valid, page3_packed_attempted, page3_seen_copy;
    aw_video_bands *bands;
    void *present_ctx;
    aw_video_present_fn present;
} aw_video;

bool aw_video_init(aw_video *v, aw_assets *assets, uint32_t page_base, uint8_t *pixels,
                   aw_video_present_fn present, void *ctx);
/* Optionally keep a second coherent 320x200 page in SRAM. */
bool aw_video_use_spare(aw_video *v, uint8_t *pixels);
bool aw_video_use_background(aw_video *v, uint8_t *buffer, uint16_t capacity);
bool aw_video_use_background_split(aw_video *v, uint8_t *first, uint16_t first_size,
                                   uint8_t *second, uint16_t second_size);
bool aw_video_use_packed_page3(aw_video *v, uint32_t base, uint16_t capacity);
void aw_video_track_bands(aw_video *v, aw_video_bands *bands);
const uint32_t *aw_video_band_identities(const aw_video *v);
bool aw_video_flush(aw_video *v);
/* Write at most two dirty bands while the LCD worker or frame clock is busy. */
bool aw_video_write_one(aw_video *v);
bool aw_video_select(aw_video *v, uint8_t page);
/* Select a drawing target without loading bytes that the next operation may
 * replace completely. Use aw_video_select for direct access to its pixels. */
bool aw_video_set_draw_page(aw_video *v, uint8_t page);
bool aw_video_fill(aw_video *v, uint8_t page, uint8_t color);
bool aw_video_copy(aw_video *v, uint8_t src, uint8_t dst, int16_t scroll);
bool aw_video_bitmap(aw_video *v, uint32_t source, uint32_t size);
bool aw_video_palette(aw_video *v, uint32_t source, uint32_t size, uint8_t palette);
bool aw_video_show(aw_video *v, uint8_t page);
bool aw_video_char(aw_video *v, uint16_t x, uint16_t y, uint8_t color, const uint8_t glyph[8]);
bool aw_video_polygon(aw_video *v, uint32_t base, uint32_t size, uint16_t offset,
                      uint16_t zoom, int16_t x, int16_t y);

#endif
