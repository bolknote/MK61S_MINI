#include "display_pages.h"
#include <string.h>

static bool separate(uint32_t a, uint32_t as, uint32_t b, uint32_t bs) {
    return a <= b ? as <= b - a : bs <= a - b;
}
bool aw_display_pages_init(aw_display_pages *p, aw_display_compact *first,
                           uint32_t second_external, uint32_t swap_base) {
    if (!p || !first || !first->assets || first->valid || first->previous != first->scratch ||
        first->capacity != first->scratch_bytes) return false;
    aw_assets *a = first->assets;
    if (second_external > a->capacity || AW_VIDEO_PAGE_BYTES > a->capacity - second_external ||
        swap_base > a->capacity || first->capacity > a->capacity - swap_base ||
        !separate(first->external_base, AW_VIDEO_PAGE_BYTES, second_external, AW_VIDEO_PAGE_BYTES) ||
        !separate(first->external_base, AW_VIDEO_PAGE_BYTES, swap_base, first->capacity) ||
        !separate(second_external, AW_VIDEO_PAGE_BYTES, swap_base, first->capacity)) return false;
    memset(p, 0, sizeof(*p));
    if (!aw_display_compact_init(&p->second, a, second_external, first->previous,
                                 first->capacity, first->scratch, first->scratch_bytes)) return false;
    p->slot[0] = first; p->slot[1] = &p->second; p->assets = a;
    p->shared = first->previous; p->swap_base = swap_base;
    p->selected = p->visible = 2;
    p->solid[0] = p->solid[1] = -1;
    return true;
}

/* Swap in place, so no second 12.8-KiB SRAM buffer is needed. External
 * fallbacks already live in each page's own 32-KiB PSRAM area. */
static bool switch_cache(aw_display_pages *p, unsigned next) {
    aw_display_compact *old = p->slot[p->loaded], *other = p->slot[next];
    const unsigned old_size = old->valid && !old->external ? old->offsets[AW_VIDEO_HEIGHT] : 0;
    const unsigned next_size = other->valid && !other->external ? other->offsets[AW_VIDEO_HEIGHT] : 0;
    if (old_size > old->capacity || next_size > other->capacity) return false;
    const unsigned limit = old_size > next_size ? old_size : next_size;
    uint8_t temp[AW_ASSET_PAGE];
    for (unsigned offset = 0; offset < limit; offset += sizeof(temp)) {
        unsigned keep = offset < old_size ? old_size - offset : 0;
        unsigned load = offset < next_size ? next_size - offset : 0;
        if (keep > sizeof(temp)) keep = sizeof(temp);
        if (load > sizeof(temp)) load = sizeof(temp);
        if (keep) memcpy(temp, p->shared + offset, keep);
        if (load && !aw_assets_read(p->assets, p->swap_base + offset, p->shared + offset, load)) return false;
        if (keep && !aw_assets_write(p->assets, p->swap_base + offset, temp, keep)) return false;
        aw_assets_progress(p->assets);
    }
    p->loaded = next;
    return true;
}

/* Full black/white game frames often alternate with the same palette. Keep
 * one of each in GRAM so later flashes need no pixel transfer or PSRAM swap. */
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
                              aw_display_page_fn select, aw_display_page_fn show,
                              aw_display_rect_fn present, void *ctx) {
    if (!p || !pixels || !palette || !select || !show || !present) return false;
    const int solid = solid_color(pixels, palette);
    if (solid >= 0) {
        for (unsigned i = 0; i < 2; ++i) if (p->slot[i]->valid && p->solid[i] == solid) {
            /* The cached page already contains the required RGB color. Its
             * saved indices/palette continue to describe that GRAM image. */
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
    unsigned next = p->loaded;
    aw_display_compact *current = p->slot[next], *other = p->slot[next ^ 1u];
    if (solid >= 0) {
        /* Do not alter the currently visible picture while preparing the
         * first instance of a solid frame, even when the palette is shared. */
        next = p->visible < 2 ? p->visible ^ 1u : p->loaded;
        p->slot[next]->valid = false;
    } else if (current->valid && memcmp(current->palette, palette, sizeof(current->palette))) {
        next ^= 1u;
        if (!other->valid || memcmp(other->palette, palette, sizeof(other->palette))) other->valid = false;
    }
    if (p->selected != next) {
        if (!select(ctx, next)) return false;
        p->selected = next;
    }
    if (next != p->loaded && !switch_cache(p, next)) return false;
    if (!aw_display_compact_present(p->slot[next], pixels, palette, present, ctx)) {
        p->solid[next] = -1;
        return false;
    }
    p->solid[next] = (int8_t)solid;
    if (p->visible != next) {
        if (!show(ctx, next)) return false;
        p->visible = next;
    }
    return true;
}
