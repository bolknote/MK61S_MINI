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
    uint16_t offsets[AW_VIDEO_HEIGHT + 1], palette[16];
    aw_assets *assets;
    bool valid, external;
} aw_display_compact;
bool aw_display_compact_init(aw_display_compact *d, aw_assets *a, uint32_t external_base,
                             uint8_t *previous, uint32_t capacity, uint8_t *scratch, uint32_t scratch_bytes);
bool aw_display_compact_present(aw_display_compact *d, const uint8_t *pixels, const uint16_t *palette,
                                aw_display_rect_fn present, void *ctx);
#endif
