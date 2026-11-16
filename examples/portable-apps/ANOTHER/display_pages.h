#ifndef ANOTHER_DISPLAY_PAGES_H
#define ANOTHER_DISPLAY_PAGES_H

#include "display_compact.h"

/* Each LCD page keeps its palette and exact band snapshots in PSRAM. The
 * borrowed framebuffer supplies separate scratch space for LCD and packing. */
typedef bool (*aw_display_page_fn)(void *ctx, unsigned page);
typedef struct {
    aw_display_compact *slot[2], second;
    unsigned selected, visible;
    int8_t solid[2]; /* -1: not solid black/white, 0: black, 1: white. */
    uint32_t identities[2][AW_VIDEO_BANDS];
    const uint8_t *pending_pixels;
    uint32_t pending_bands;
} aw_display_pages;

bool aw_display_pages_init(aw_display_pages *p, aw_display_compact *first, uint32_t second_external);
/* wait is called once before modifying a visible page or showing a new one. */
bool aw_display_pages_present(aw_display_pages *p, const uint8_t *pixels, const uint16_t *palette,
                              const uint32_t *identities,
                              aw_display_page_fn select, aw_display_page_fn show,
                              aw_display_rect_fn present, aw_display_wait_fn wait, void *ctx);
/* Save at most one pending band while the LCD worker owns its copied pixels. */
bool aw_display_pages_write_one(aw_display_pages *p);
#endif
