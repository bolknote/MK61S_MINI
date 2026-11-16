#ifndef ANOTHER_DISPLAY_PAGES_H
#define ANOTHER_DISPLAY_PAGES_H

#include "display_compact.h"

/* Two LCD pages keep their own palette and previous pixel indices. Only the
 * active page's compressed copy occupies the borrowed framebuffer; the other
 * is swapped to the caller-provided PSRAM range when palettes alternate. */
typedef bool (*aw_display_page_fn)(void *ctx, unsigned page);
typedef struct {
    aw_display_compact *slot[2], second;
    aw_assets *assets;
    uint8_t *shared;
    uint32_t swap_base;
    unsigned loaded, selected, visible;
    int8_t solid[2]; /* -1: not solid black/white, 0: black, 1: white. */
} aw_display_pages;

bool aw_display_pages_init(aw_display_pages *p, aw_display_compact *first,
                           uint32_t second_external, uint32_t swap_base);
bool aw_display_pages_present(aw_display_pages *p, const uint8_t *pixels, const uint16_t *palette,
                              aw_display_page_fn select, aw_display_page_fn show,
                              aw_display_rect_fn present, void *ctx);
#endif
