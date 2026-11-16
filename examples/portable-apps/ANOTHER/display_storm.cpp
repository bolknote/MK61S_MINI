#include "display_storm.h"
#include "zx0.hpp"
#include <string.h>

namespace {

uint16_t le16(const uint8_t *p) { return p[0] | (uint16_t(p[1]) << 8); }
uint32_t le32(const uint8_t *p) { return le16(p) | (uint32_t(le16(p + 2)) << 16); }

struct Source {
    aw_storm_read_fn read;
    void *ctx;
    uint32_t bytes, at = 0, hash = AW_STORM_HASH_INIT;

    bool take(uint8_t *out, uint32_t size) {
        if (size > bytes - at) return false;
        while (size) {
            const uint32_t n = size > AW_ASSET_MAX_TRANSFER ? AW_ASSET_MAX_TRANSFER : size;
            if (!read(ctx, at, out, n)) return false;
            for (uint32_t i = 0; i < n; ++i)
                if (at + i >= 8) hash = aw_storm_hash_byte(hash, out[i]);
            at += n; out += n; size -= n;
        }
        return true;
    }
};

bool store(aw_assets &assets, uint32_t offset, uint8_t *data, unsigned size, bool write) {
    // The clip has a separate, page-aligned region and never enters the
    // resource LRU. Failure to read this optional data must not fault the VM.
    while (size) {
        const unsigned n = size > AW_ASSET_MAX_TRANSFER ? AW_ASSET_MAX_TRANSFER : size;
        if (!(write ? assets.store_write(assets.ctx, offset, data, n)
                    : assets.store_read(assets.ctx, offset, data, n))) return false;
        offset += n; data += n; size -= n;
    }
    return true;
}

bool select_page(aw_display_pages &p, unsigned page, aw_display_page_fn select, void *ctx) {
    if (p.selected == page) return true;
    if (!select(ctx, page)) return false;
    p.selected = page;
    return true;
}

bool draw_rect(aw_display_pages &p, const aw_storm_rect &r, const uint16_t *palette,
               aw_display_rect_fn draw, void *ctx) {
    auto &slot = *p.slot[p.selected];
    slot.valid = false;
    return store(*slot.assets, r.offset, slot.scratch, unsigned(r.width) * r.height, false) &&
           draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height, slot.scratch, palette, false);
}

} // namespace

bool aw_storm_load(aw_display_storm *s, aw_assets *assets, uint32_t base,
                   uint8_t *scratch, uint32_t bytes, aw_storm_read_fn read, void *ctx) {
    s->ready = false;
    if (bytes < AW_STORM_HEADER || bytes > AW_STORM_MAX_FILE || base > assets->capacity ||
        base > UINT32_MAX - (AW_ASSET_PAGE - 1u)) return false;
    uint32_t at = (base + AW_ASSET_PAGE - 1u) & ~(AW_ASSET_PAGE - 1u);
    if (at > assets->capacity) return false;
    Source source{read, ctx, bytes};
    uint8_t header[AW_STORM_HEADER];
    if (!source.take(header, sizeof(header)) || memcmp(header, "AWS1", 4) ||
        le16(header + 10) != 0) return false;
    const uint32_t hash = le32(header + 4);
    s->first = le16(header + 8);
    if (s->first > UINT16_MAX - AW_STORM_WARM_FRAMES - AW_STORM_FRAMES) return false;
    for (unsigned i = 0; i < AW_STORM_WARM_FRAMES; ++i) s->warm_hash[i] = le32(header + 12 + 4 * i);
    for (unsigned i = 0; i < 16; ++i) s->first_palette[i] = le16(header + 32 + 2 * i);
    uint8_t *packed = scratch + AW_STORM_BLOCK;
    unsigned rects = 0;
    for (unsigned i = 0; i < AW_STORM_FRAMES; ++i) {
        if (!source.take(header, 6) || header[4] > 1 || header[5] > AW_STORM_RECTS - rects) return false;
        auto &f = s->frames[i];
        f = {le32(header), header[4], uint8_t(rects), uint8_t(rects + header[5])};
        if (!i && (f.page != 0 || f.end != AW_STORM_WARM_FRAMES)) return false;
        for (; rects < f.end; ++rects) {
            if (!source.take(header, 6)) return false;
            const aw_storm_rect r{at, header[0], header[1], header[2], header[3]};
            const unsigned size = unsigned(r.width) * r.height;
            const unsigned encoded = le16(header + 4);
            if (!size || r.x + r.width > int(AW_VIDEO_STRIDE) || r.y + r.height > int(AW_VIDEO_HEIGHT) ||
                size > AW_STORM_BLOCK || size > assets->capacity - at || !encoded || encoded > size) return false;
            if (!i && (r.x || r.y != rects * AW_STORM_STRIP_ROWS ||
                       r.width != AW_VIDEO_STRIDE || r.height != AW_STORM_STRIP_ROWS)) return false;
            if (encoded == size) {
                if (!source.take(scratch, size)) return false;
            } else {
                if (!source.take(packed, encoded)) return false;
                uint8_t *cursor = packed;
                const zx0::Input input{&cursor, [](void *p, u8 &b) {
                    b = *(*static_cast<uint8_t **>(p))++; return true;
                }};
                // The decoder bounds all input reads by encoded.
                u32 written = 0;
                if (!zx0::decode(input, encoded, scratch, size, written) || written != size) return false;
            }
            if (!store(*assets, at, scratch, size, true)) return false;
            s->rects[rects] = r;
            at += size;
        }
    }
    s->at = 0;
    s->warmed = 0;
    s->ready = source.at == bytes && source.hash == hash;
    return s->ready;
}

bool aw_storm_warm(aw_display_storm *s, aw_display_pages *p, unsigned index,
                   const uint8_t *pixels, const uint16_t *palette,
                   aw_display_page_fn select, aw_display_rect_fn draw, void *ctx) {
    if (!s->ready) return false;
    if (!index) s->front = uint8_t(p->visible);
    if (index != s->warmed || index >= AW_STORM_WARM_FRAMES || p->visible > 1 || p->visible != s->front ||
        aw_storm_frame_hash(pixels, palette) != s->warm_hash[index] ||
        !select_page(*p, s->front ^ 1u, select, ctx) ||
        !draw_rect(*p, s->rects[index], s->first_palette, draw, ctx)) return s->ready = false;
    ++s->warmed;
    return true;
}

bool aw_storm_present(aw_display_storm *s, aw_display_pages *p, unsigned index,
                      const uint8_t *pixels, const uint16_t *palette,
                      aw_display_page_fn select, aw_display_page_fn show,
                      aw_display_rect_fn draw, aw_display_wait_fn wait, void *ctx) {
    if (!s->ready) return false;
    if (index >= AW_STORM_FRAMES || s->warmed != AW_STORM_WARM_FRAMES ||
        (!index && p->visible != s->front)) return s->ready = false;
    const auto &frame = s->frames[index];
    if (aw_storm_frame_hash(pixels, palette) != frame.hash ||
        (!index && memcmp(palette, s->first_palette, sizeof(s->first_palette)))) return s->ready = false;
    const unsigned page = frame.page ^ s->front ^ 1u;
    const bool hidden = page != p->visible;
    if (!select_page(*p, page, select, ctx) || (!hidden && !wait(ctx))) return s->ready = false;
    // Frame zero is already fully uploaded by the five warm steps.
    if (index)
        for (unsigned i = frame.first; i < frame.end; ++i)
            if (!draw_rect(*p, s->rects[i], palette, draw, ctx)) return s->ready = false;
    if (hidden && (!wait(ctx) || !show(ctx, page))) return s->ready = false;
    p->visible = page;
    // Retain palette choice for normal page selection after the clip. The
    // first normal draw into each modified page rebuilds its band snapshot.
    p->slot[page]->valid = false;
    memcpy(p->slot[page]->palette, palette, sizeof(s->first_palette));
    if (index + 1 == AW_STORM_FRAMES) s->ready = false;
    return true;
}
