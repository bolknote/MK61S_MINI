#include "display_pages.h"
#include <string.h>

bool aw_display_pages_init(aw_display_pages *p, aw_display_compact *first, uint32_t second_external) {
    if (!p || !first || !first->assets || first->valid || first->previous != first->scratch ||
        first->capacity != first->scratch_bytes) return false;
    aw_assets *a = first->assets;
    const uint32_t left = first->external_base < second_external ? first->external_base : second_external;
    const uint32_t right = first->external_base < second_external ? second_external : first->external_base;
    if (right - left < AW_VIDEO_PAGE_BYTES) return false;
    memset(p, 0, sizeof(*p));
    if (!aw_display_compact_init(&p->second, a, second_external, first->previous,
                                 first->capacity, first->scratch, first->scratch_bytes)) return false;
    p->slot[0] = first; p->slot[1] = &p->second;
    p->selected = p->visible = 2;
    p->solid[0] = p->solid[1] = -1;
    return true;
}

bool aw_display_pages_write_one(aw_display_pages *p) {
    return !p->pending_bands ||
           aw_display_bands_write_one(p->slot[p->selected], p->pending_pixels, &p->pending_bands);
}

/* Full black/white game frames often alternate with the same palette. Keep
 * one of each in GRAM so later flashes need only switch pages. */
static int solid_color(const uint8_t *pixels, const uint16_t *palette) {
    const uint8_t pair = pixels[0];
    if ((pair >> 4) != (pair & 15)) return -1;
    const uint16_t color = palette[pair & 15];
    if (color != 0 && color != 0xffff) return -1;
    for (unsigned i = 1; i <= 32; ++i)
        if (pixels[(i * 997u) % AW_VIDEO_PAGE_BYTES] != pair) return -1;
    for (unsigned i = 1; i < AW_VIDEO_PAGE_BYTES; ++i)
        if (pixels[i] != pair) return -1;
    return color != 0;
}

bool aw_display_pages_present(aw_display_pages *p, const uint8_t *pixels, const uint16_t *palette,
                              const uint32_t *identities,
                              aw_display_page_fn select, aw_display_page_fn show,
                              aw_display_rect_fn present, aw_display_wait_fn wait, void *ctx) {
    if (!p || !pixels || !palette || !select || !show || !present) return false;
    const int solid = solid_color(pixels, palette);
    if (solid >= 0) {
        for (unsigned i = 0; i < 2; ++i) if (p->slot[i]->valid && p->solid[i] == solid) {
            /* The cached page already contains the required RGB color. Its
             * saved indices/palette continue to describe that GRAM image. */
            if (wait && !wait(ctx)) return false;
            if (p->visible != i) {
                if (p->selected != i) {
                    if (!select(ctx, i)) return false;
                    p->selected = i;
                }
                if (!show(ctx, i)) return false;
                p->visible = i;
            }
            return true;
        }
    }
    unsigned next = p->visible < 2 ? p->visible : 0;
    const aw_display_compact *current = p->slot[next];
    if (p->visible < 2 && (solid >= 0 || memcmp(current->palette, palette, sizeof(current->palette))))
        next ^= 1u;
    if (p->selected != next) {
        if (!select(ctx, next)) return false;
        p->selected = next;
    }
    aw_display_compact *target = p->slot[next];
    const bool hidden = p->visible != next;
    uint32_t known = 0;
    if (identities && target->valid)
        for (unsigned band = 0; band < AW_VIDEO_BANDS; ++band)
            if (identities[band] && identities[band] == p->identities[next][band])
                known |= 1u << band;
    p->pending_pixels = pixels;
    bool ok = aw_display_bands_prepare(target, pixels, palette, present, hidden ? NULL : wait, ctx,
                                       known, &p->pending_bands);
    if (ok && hidden) {
        ok = (!wait || wait(ctx)) && show(ctx, next);
        if (ok) p->visible = next;
    }
    while (ok && p->pending_bands) {
        ok = aw_display_pages_write_one(p);
        if (ok) aw_assets_progress(target->assets);
    }
    p->pending_pixels = NULL;
    p->pending_bands = 0;
    if (!ok) {
        /* Either GRAM or the snapshot may be partially updated. */
        target->valid = false;
        return false;
    }
    memcpy(target->palette, palette, sizeof(target->palette));
    target->valid = true;
    if (identities) memcpy(p->identities[next], identities, sizeof(p->identities[next]));
    else memset(p->identities[next], 0, sizeof(p->identities[next]));
    p->solid[next] = (int8_t)solid;
    return true;
}
