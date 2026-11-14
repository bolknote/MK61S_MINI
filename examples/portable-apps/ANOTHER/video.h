#ifndef MK61_ANOTHER_VIDEO_H
#define MK61_ANOTHER_VIDEO_H

#include "assets.h"

#define AW_VIDEO_WIDTH 320u
#define AW_VIDEO_HEIGHT 200u
#define AW_VIDEO_STRIDE 160u
#define AW_VIDEO_PAGE_BYTES (AW_VIDEO_STRIDE * AW_VIDEO_HEIGHT)
#define AW_VIDEO_INTERP_SLOTS 32u
#define AW_VIDEO_PAGE3_PACKED_BYTES 8192u

typedef bool (*aw_video_present_fn)(void *ctx, const uint8_t *pixels, const uint16_t *palette);

typedef struct {
    aw_assets *assets;
    uint8_t *pixels; /* Current SRAM page; may swap with the caller's spare. */
    uint32_t page_base, shape_base, shape_size;
    uint16_t palette[16], interp[AW_VIDEO_INTERP_SLOTS];
    uint8_t draw_page, front_page, back_page, resident_page;
    bool resident_valid, dirty, fault;
    uint8_t *spare;
    uint8_t spare_page;
    bool spare_valid, spare_dirty;
    uint8_t *background, *background_tail;
    uint16_t background_split, background_capacity, background_size, background_offsets[AW_VIDEO_HEIGHT + 1];
    bool background_valid, background_attempted;
    uint32_t page3_packed_base;
    uint16_t page3_packed_size, page3_packed_capacity;
    bool page3_packed_valid, page3_packed_attempted, page3_seen_copy;
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
bool aw_video_flush(aw_video *v);
bool aw_video_select(aw_video *v, uint8_t page);
bool aw_video_fill(aw_video *v, uint8_t page, uint8_t color);
bool aw_video_copy(aw_video *v, uint8_t src, uint8_t dst, int16_t scroll);
bool aw_video_bitmap(aw_video *v, uint32_t source, uint32_t size);
bool aw_video_palette(aw_video *v, uint32_t source, uint32_t size, uint8_t palette);
bool aw_video_show(aw_video *v, uint8_t page);
bool aw_video_char(aw_video *v, uint16_t x, uint16_t y, uint8_t color, const uint8_t glyph[8]);
bool aw_video_polygon(aw_video *v, uint32_t base, uint32_t size, uint16_t offset,
                      uint16_t zoom, int16_t x, int16_t y);

#endif
