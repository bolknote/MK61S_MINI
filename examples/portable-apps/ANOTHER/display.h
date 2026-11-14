#ifndef MK61_ANOTHER_DISPLAY_H
#define MK61_ANOTHER_DISPLAY_H

#include "video.h"

/* The previous 320x200 INDEX4 image also serves as temporary packed rectangle
 * storage after all dirty rectangles have been calculated. PRESENT must copy
 * the rectangle before returning, as required by the PicoCalc color ABI. */
typedef bool (*aw_display_rect_fn)(void *ctx, unsigned x, unsigned y,
                                   unsigned width, unsigned height,
                                   const uint8_t *pixels, const uint16_t *palette,
                                   bool clear_outside);
typedef struct {
    uint8_t *previous;
    uint16_t palette[16];
    bool valid;
} aw_display;

void aw_display_init(aw_display *display, uint8_t *previous);
bool aw_display_present(aw_display *display, const uint8_t *pixels, const uint16_t *palette,
                        aw_display_rect_fn present, void *ctx);

#endif
