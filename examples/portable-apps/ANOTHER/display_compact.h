#ifndef ANOTHER_DISPLAY_COMPACT_H
#define ANOTHER_DISPLAY_COMPACT_H
#include "display.h"
/* The previous frame lives losslessly in the borrowed framebuffer when it
 * fits, or in the reserved PSRAM range otherwise. Scratch is only used after
 * comparing the previous frame, so it may be the same borrowed framebuffer.
 * Rectangle submissions copy their pixels synchronously. All buffers are
 * owned by the caller. */
typedef struct {
    uint8_t *previous, *scratch;
    uint32_t capacity, scratch_bytes, external_base;
    union {
        uint16_t offsets[AW_VIDEO_HEIGHT + 1]; /* Legacy row RLE in SRAM. */
        uint16_t band_sizes[AW_VIDEO_BANDS];   /* Two-page snapshots in PSRAM. */
    };
    uint16_t palette[16];
    aw_assets *assets;
    bool valid, external;
} aw_display_compact;
typedef bool (*aw_display_wait_fn)(void *ctx);
#ifdef __cplusplus
extern "C" {
#endif
bool aw_display_compact_init(aw_display_compact *d, aw_assets *a, uint32_t external_base,
                             uint8_t *previous, uint32_t capacity, uint8_t *scratch, uint32_t scratch_bytes);
bool aw_display_compact_present(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                                aw_display_rect_fn present, void *ctx);
/* Two-page output keeps independent bands in PSRAM. Prepare fills the dirty
 * mask before submitting rectangles. A wait callback gates writes to the
 * visible page. The caller can save one dirty band per busy LCD poll. */
bool aw_display_bands_prepare(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                              aw_display_rect_fn present, aw_display_wait_fn wait, void *ctx,
                              uint32_t known, uint32_t *dirty);
bool aw_display_bands_write_one(aw_display_compact *d, const uint8_t *pixels, uint32_t *dirty);
/* Store one packed-index band, without changing the slot's validity. */
bool aw_display_band_store(aw_display_compact *d, unsigned band, const uint8_t *source);
#ifdef __cplusplus
}
#endif
#endif
