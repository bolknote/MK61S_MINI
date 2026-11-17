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

bool load_rects(Source &source, aw_assets &assets, uint32_t &at, uint8_t *scratch,
                aw_storm_rect *rects, unsigned count, unsigned max_area, bool full, bool &fits) {
    uint8_t *packed = scratch + AW_STORM_BLOCK;
    unsigned area = 0;
    for (unsigned i = 0; i < count; ++i) {
        uint8_t header[6];
        if (!source.take(header, sizeof(header))) return false;
        const aw_storm_rect r{at, header[0], header[1], header[2], header[3]};
        const unsigned size = unsigned(r.width) * r.height;
        const unsigned encoded = le16(header + 4);
        if (!size || r.x + r.width > int(AW_VIDEO_STRIDE) || r.y + r.height > int(AW_VIDEO_HEIGHT) ||
            size > AW_STORM_BLOCK || !encoded || encoded > size) return false;
        area += size;
        if (area > max_area) return false;
        if (full && (r.x || r.y != i * AW_STORM_STRIP_ROWS ||
                     r.width != AW_VIDEO_STRIDE || r.height != AW_STORM_STRIP_ROWS)) return false;
        if (encoded == size) {
            if (!source.take(scratch, size)) return false;
        } else {
            if (!source.take(packed, encoded)) return false;
            uint8_t *cursor = packed;
            const zx0::Input input{&cursor, [](void *p, u8 &b) {
                b = *(*static_cast<uint8_t **>(p))++; return true;
            }};
            uint32_t written = 0;
            if (!zx0::decode(input, encoded, scratch, size, written) || written != size) return false;
        }
        if (fits) {
            fits = size <= assets.capacity - at && store(assets, at, scratch, size, true);
            if (fits) {
                rects[i] = r;
                at += size;
            }
        }
    }
    return true;
}

// AWS3 appends the idle and two image hashes, the return-frame dirty-band
// mask and window count. Each image has a palette and five full-width strips.
// The final windows restore the frame after the white flash.
bool load_prelude(aw_display_storm &s, Source &source, aw_assets &assets, uint32_t &at,
                  uint8_t *scratch, unsigned rects, bool &fits) {
    uint8_t meta[AW_STORM_PRELUDE_HEADER];
    if (s.first < AW_STORM_IDLE_LEAD || !source.take(meta, sizeof(meta))) return false;
    auto &pre = s.prelude;
    pre.idle_hash = le32(meta);
    pre.lab.hash = le32(meta + 4);
    pre.before_flash.hash = le32(meta + 8);
    pre.dirty_bands = le32(meta + 12);
    const unsigned return_count = meta[16];
    if ((pre.dirty_bands >> AW_VIDEO_BANDS) || !return_count || return_count > AW_STORM_RETURN_RECTS) return false;
    aw_storm_image *images[] = {&pre.lab, &pre.before_flash};
    for (auto *image : images) {
        uint8_t colors[AW_STORM_PALETTE_BYTES];
        if (!source.take(colors, sizeof(colors))) return false;
        for (unsigned i = 0; i < 16; ++i) image->palette[i] = le16(colors + 2 * i);
        image->first = uint8_t(rects);
        image->page = 2;
        if (!load_rects(source, assets, at, scratch, s.rects + rects, AW_STORM_WARM_FRAMES,
                        AW_VIDEO_PAGE_BYTES, true, fits)) return false;
        rects += AW_STORM_WARM_FRAMES;
    }
    pre.return_first = uint8_t(rects);
    pre.return_end = uint8_t(rects + return_count);
    pre.saved_page = 2;
    return load_rects(source, assets, at, scratch, s.rects + rects, return_count,
                      AW_STORM_BLOCK, false, fits);
}

// AWS4 appends the return from the first flash over the earlier idle page.
bool load_idle_return(aw_display_storm &s, Source &source, aw_assets &assets,
                       uint32_t at, uint8_t *scratch, bool &fits) {
    uint8_t header[AW_STORM_IDLE_RETURN_HEADER];
    if (!source.take(header, sizeof(header))) return false;
    auto &ret = s.prelude.idle_return;
    ret.hash = le32(header);
    ret.dirty_bands = le32(header + 4);
    const unsigned count = header[8];
    if (!count || count > AW_STORM_IDLE_RETURN_RECTS || (ret.dirty_bands >> AW_VIDEO_BANDS)) return false;
    for (unsigned i = 0; i < 16; ++i) ret.palette[i] = le16(header + 9 + 2 * i);
    ret.first = s.prelude.return_end;
    ret.end = uint8_t(ret.first + count);
    ret.page = 2;
    return load_rects(source, assets, at, scratch, s.rects + ret.first, count,
                      AW_VIDEO_PAGE_BYTES, false, fits);
}

bool select_page(aw_display_pages &p, unsigned page, aw_display_page_fn select, void *ctx) {
    if (p.selected == page) return true;
    if (!select(ctx, page)) return false;
    p.selected = page;
    return true;
}

bool read_rect(aw_display_compact &slot, const aw_storm_rect &r) {
    return store(*slot.assets, r.offset, slot.scratch, unsigned(r.width) * r.height, false);
}

bool pump_rect(aw_display_storm &s, aw_display_pages &p, unsigned page, uint8_t &cursor,
               const uint16_t *palette, const aw_storm_output &lcd, void *ctx) {
    if (page == p.visible) return false;
    if (p.selected != page) {
        const unsigned result = lcd.try_select(ctx, page);
        if (result != 1) return result == 2;
        p.selected = page;
    }
    auto &slot = *p.slot[page];
    const auto &r = s.rects[cursor];
    slot.valid = false;
    // Load the next window during DMA and reuse scratch until it is accepted.
    if (!s.staged) {
        if (!read_rect(slot, r)) return false;
        s.staged = true;
    }
    const unsigned result = lcd.try_draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height, slot.scratch, palette, false);
    if (result == 1) {
        ++cursor;
        s.staged = false;
    }
    return result == 1 || result == 2;
}

bool upload_strip(aw_display_storm &s, aw_display_pages &p, aw_storm_image &image,
                  const aw_storm_output &lcd, bool asynchronous, void *ctx) {
    const unsigned page = image.page;
    if (page > 1 || p.visible != (page ^ 1u) || image.strips >= AW_STORM_WARM_FRAMES) return false;
    if (asynchronous) {
        // Poll even if already selected. The previous strip may still own SPI.
        const unsigned result = lcd.try_select(ctx, page);
        if (result != 1) return result == 2;
        p.selected = page;
    } else if (!select_page(p, page, lcd.select, ctx)) {
        return false;
    }
    auto &slot = *p.slot[page];
    const auto &r = s.rects[image.first + image.strips];
    slot.valid = false;
    if (!read_rect(slot, r)) return false;
    const unsigned result = asynchronous
        ? lcd.try_draw(ctx, 0, r.y, AW_VIDEO_WIDTH, r.height, slot.scratch, image.palette, false)
        : lcd.draw(ctx, 0, r.y, AW_VIDEO_WIDTH, r.height, slot.scratch, image.palette, false);
    if (result != 1) return result == 2;
    for (unsigned row = 0; row < r.height; row += AW_VIDEO_BAND_ROWS)
        if (!aw_display_band_store(&slot, (r.y + row) / AW_VIDEO_BAND_ROWS,
                                   slot.scratch + row * AW_VIDEO_STRIDE)) return false;
    if (++image.strips == AW_STORM_WARM_FRAMES)
        return aw_display_pages_finish(&p, image.palette, nullptr, -1, true);
    return true;
}

bool use_image(aw_display_pages &p, const aw_storm_image &image, uint32_t hash,
               const uint16_t *palette, const uint32_t *identities) {
    const unsigned page = image.page;
    if (image.strips != AW_STORM_WARM_FRAMES || !identities || hash != image.hash ||
        page > 1 || p.visible != (page ^ 1u) || !p.slot[page]->valid ||
        memcmp(palette, image.palette, AW_STORM_PALETTE_BYTES) ||
        memcmp(palette, p.slot[page]->palette, AW_STORM_PALETTE_BYTES) ||
        !memcmp(palette, p.slot[p.visible]->palette, AW_STORM_PALETTE_BYTES)) return false;
    memcpy(p.identities[page], identities, sizeof(p.identities[page]));
    return true;
}

bool show_retained(aw_display_storm &s, aw_display_pages &p, const uint8_t *pixels,
                   const uint16_t *palette, const uint32_t *identities,
                   const aw_storm_output &lcd, void *ctx) {
    const auto &pre = s.prelude;
    const unsigned page = pre.saved_page;
    if (page > 1 || p.visible != (page ^ 1u) || !p.slot[page]->valid ||
        memcmp(p.slot[page]->palette, palette, AW_STORM_PALETTE_BYTES) ||
        aw_storm_frame_hash(pixels, palette) != s.warm_hash[1] ||
        !select_page(p, page, lcd.select, ctx)) return false;
    auto &slot = *p.slot[page];
    const uint32_t base = s.rects[pre.return_first].offset;
    const auto &last = s.rects[pre.return_end - 1];
    const unsigned bytes = last.offset - base + unsigned(last.width) * last.height;
    if (!store(*slot.assets, base, slot.scratch, bytes, false)) return false;
    slot.valid = false;
    p.pending_pixels = pixels;
    p.pending_bands = pre.dirty_bands;
    bool ok = true;
    for (unsigned i = pre.return_first; ok && i < pre.return_end; ++i) {
        const auto &r = s.rects[i];
        ok = lcd.draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height,
                      slot.scratch + (r.offset - base), palette, false);
    }
    ok = ok && lcd.wait(ctx, 0) && lcd.show(ctx, page);
    if (ok) p.visible = page;
    return aw_display_pages_finish(&p, palette, identities, -1, ok);
}

bool show_idle_return(aw_display_storm &s, aw_display_pages &p, const uint8_t *pixels,
                       const uint16_t *palette, const uint32_t *identities,
                       const aw_storm_output &lcd, void *ctx) {
    auto &ret = s.prelude.idle_return;
    ret.active = false;
    bool staged = s.staged;
    s.staged = false;
    const unsigned page = ret.page;
    if (p.visible != (page ^ 1u) || memcmp(palette, ret.palette, AW_STORM_PALETTE_BYTES) ||
        aw_storm_frame_hash(pixels, palette) != ret.hash || !select_page(p, page, lcd.select, ctx)) return false;
    auto &slot = *p.slot[page];
    slot.valid = false;
    p.pending_pixels = pixels;
    p.pending_bands = ret.dirty_bands;
    bool ok = true;
    for (unsigned i = ret.cursor; ok && i < ret.end; ++i) {
        const auto &r = s.rects[i];
        ok = (staged || read_rect(slot, r)) &&
            lcd.draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height, slot.scratch, palette, false);
        staged = false;
    }
    if (!aw_display_pages_finish(&p, palette, identities, -1, ok)) return false;
    if (!lcd.wait(ctx, 0) || !lcd.show(ctx, page)) return slot.valid = false;
    p.visible = page;
    return true;
}

void begin_before_flash(aw_display_storm &s, aw_display_pages &p, const aw_storm_output &lcd, void *ctx) {
    s.prelude.before_flash.page = uint8_t(p.visible ^ 1u);
    s.prelude.uploading = true;
    aw_storm_pump(&s, &p, &lcd, ctx);
}

bool render_normal(aw_display_storm &s, const uint8_t *pixels, const uint16_t *palette,
                   const uint32_t *identities, unsigned lead, aw_storm_normal_fn normal, void *ctx) {
    // The ordinary renderer owns the LCD selection and shared scratch until
    // it returns. Queued rectangles are copied, but staged ones must be reread.
    s.rendering = true;
    s.staged = false;
    const bool ok = normal(ctx, pixels, palette, identities, lead);
    s.rendering = false;
    if (!ok) s.ready = false;
    return ok;
}

// RGB565 on the wire plus the measured budget for PSRAM and window setup.
// Rectangles on the currently visible page start this long before the
// deadline, once their live frame has been validated.
unsigned lead_ms(const aw_display_storm &s, const aw_storm_frame &f, uint32_t spi_hz) {
    if (!s.ahead || spi_hz < 1000 || f.first == f.end) return 0;
    unsigned bytes = 0;
    for (unsigned i = f.first; i < f.end; ++i)
        bytes += unsigned(s.rects[i].width) * s.rects[i].height * 4;
    const uint32_t us = bytes * 8000u / (spi_hz / 1000u) + bytes / 20u + 1000u * (f.end - f.first);
    return (us + 500u) / 1000u;
}

} // namespace

bool aw_storm_load(aw_display_storm *s, aw_assets *assets, uint32_t base,
                   uint8_t *scratch, uint32_t bytes, aw_storm_read_fn read, void *ctx) {
    s->ready = false;
    s->prelude = {};
    if (bytes < AW_STORM_HEADER || bytes > AW_STORM_MAX_FILE || base > assets->capacity ||
        base > UINT32_MAX - (AW_ASSET_PAGE - 1u)) return false;
    uint32_t at = (base + AW_ASSET_PAGE - 1u) & ~(AW_ASSET_PAGE - 1u);
    if (at > assets->capacity) return false;
    Source source{read, ctx, bytes};
    uint8_t header[AW_STORM_HEADER];
    if (!source.take(header, sizeof(header)) ||
        memcmp(header, "AWS", 3) || header[3] < '1' || header[3] > '4' || le16(header + 10)) return false;
    const uint32_t hash = le32(header + 4);
    const bool has_prelude = header[3] >= '3', has_idle_return = header[3] == '4';
    s->ahead = header[3] >= '2';
    s->first = le16(header + 8);
    if (s->first > UINT16_MAX - AW_STORM_WARM_FRAMES - AW_STORM_FRAMES) return false;
    for (unsigned i = 0; i < AW_STORM_WARM_FRAMES; ++i) s->warm_hash[i] = le32(header + 12 + 4 * i);
    for (unsigned i = 0; i < 16; ++i) s->palette[0][i] = le16(header + 32 + 2 * i);
    if (s->ahead) {
        if (!source.take(header, AW_STORM_PALETTE_BYTES)) return false;
        for (unsigned i = 0; i < 16; ++i) s->palette[1][i] = le16(header + 2 * i);
    }
    bool fits = true;
    unsigned rects = 0;
    for (unsigned i = 0; i < AW_STORM_FRAMES; ++i) {
        if (!source.take(header, 6) || header[4] > 1 || header[5] > AW_STORM_RECTS - rects) return false;
        auto &f = s->frames[i];
        f = {le32(header), header[4], uint8_t(rects), uint8_t(rects + header[5])};
        if (!i && (f.page != 0 || f.end != AW_STORM_WARM_FRAMES)) return false;
        // The lead calculation assumes at most one screen of RGB565 per frame.
        const unsigned max_area = s->ahead ? AW_VIDEO_PAGE_BYTES : AW_STORM_RECTS * AW_STORM_BLOCK;
        if (!load_rects(source, *assets, at, scratch, s->rects + rects, f.end - rects,
                        max_area, !i, fits) || !fits) return false;
        rects = f.end;
    }
    if (has_prelude && !load_prelude(*s, source, *assets, at, scratch, rects, fits)) return false;
    bool return_fits = fits;
    if (has_idle_return && !load_idle_return(*s, source, *assets, at, scratch, return_fits)) return false;
    s->at = 0;
    s->warmed = 0;
    s->pending = AW_STORM_FRAMES;
    s->staged = false;
    s->rendering = false;
    s->ready = source.at == bytes && source.hash == hash;
    s->prelude.available = s->ready && has_prelude && fits;
    s->prelude.idle_return.available = s->ready && has_idle_return && return_fits;
    return s->ready;
}

bool aw_storm_warm(aw_display_storm *s, aw_display_pages *p, unsigned index,
                   const uint8_t *pixels, const uint16_t *palette,
                   aw_display_page_fn select, aw_display_rect_fn draw, void *ctx) {
    if (!s->ready) return false;
    if (!index) s->front = uint8_t(p->visible);
    if (index != s->warmed || index >= AW_STORM_WARM_FRAMES || p->visible > 1 || p->visible != s->front ||
        aw_storm_frame_hash(pixels, palette) != s->warm_hash[index] ||
        !select_page(*p, s->front ^ 1u, select, ctx)) return s->ready = false;
    auto &slot = *p->slot[p->selected];
    const auto &r = s->rects[index];
    slot.valid = false;
    if (!read_rect(slot, r) ||
        !draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height, slot.scratch, s->palette[0], false))
        return s->ready = false;
    ++s->warmed;
    return true;
}

void aw_storm_pump(aw_display_storm *s, aw_display_pages *p, const aw_storm_output *lcd, void *ctx) {
    if (!s->ready || s->rendering || p->pending_bands) return;
    auto &ret = s->prelude.idle_return;
    if (ret.active) {
        if (ret.cursor < ret.end && !pump_rect(*s, *p, ret.page, ret.cursor, ret.palette, *lcd, ctx)) {
            ret.active = false;
            s->staged = false;
        }
        return;
    }
    if (s->prelude.uploading) {
        auto &image = s->prelude.before_flash;
        if (!upload_strip(*s, *p, image, *lcd, true, ctx)) image.page = 2;
        s->prelude.uploading = image.page < 2 && image.strips < AW_STORM_WARM_FRAMES;
        return;
    }
    if (s->pending >= AW_STORM_FRAMES) return;
    const auto &f = s->frames[s->pending];
    if (s->cursor == f.end) return;
    const unsigned page = f.page ^ s->front ^ 1u;
    if (!pump_rect(*s, *p, page, s->cursor, s->palette[f.page], *lcd, ctx)) s->ready = false;
}

bool aw_storm_present(aw_display_storm *s, aw_display_pages *p, unsigned index,
                      const uint8_t *pixels, const uint16_t *palette,
                      const aw_storm_output *lcd, void *ctx) {
    if (!s->ready) return false;
    const bool prepared = s->pending == index;
    if (index >= AW_STORM_FRAMES ||
        (s->warmed != AW_STORM_WARM_FRAMES && (index || !prepared)) ||
        (!index && p->visible != s->front)) return s->ready = false;
    const auto &frame = s->frames[index];
    if (aw_storm_frame_hash(pixels, palette) != frame.hash ||
        ((s->ahead || !index) && memcmp(palette, s->palette[frame.page], AW_STORM_PALETTE_BYTES)))
        return s->ready = false;
    const unsigned page = frame.page ^ s->front ^ 1u;
    const bool hidden = page != p->visible;
    const unsigned start = prepared ? s->cursor : index ? frame.first : frame.end;
    bool staged = prepared && s->staged;
    s->pending = AW_STORM_FRAMES;
    s->staged = false;
    if (!select_page(*p, page, lcd->select, ctx) ||
        (!hidden && !lcd->wait(ctx, lead_ms(*s, frame, lcd->spi_hz)))) return s->ready = false;
    auto &slot = *p->slot[page];
    slot.valid = false;
    for (unsigned i = start; i < frame.end; ++i) {
        const auto &r = s->rects[i];
        if ((!staged && !read_rect(slot, r)) ||
            !lcd->draw(ctx, r.x * 2u, r.y, r.width * 2u, r.height, slot.scratch, palette, false))
            return s->ready = false;
        staged = false;
    }
    if (hidden && (!lcd->wait(ctx, 0) || !lcd->show(ctx, page))) return s->ready = false;
    if (!hidden && s->ahead && start < frame.end && !lcd->select(ctx, page)) return s->ready = false;
    p->visible = page;
    s->warmed = AW_STORM_WARM_FRAMES;
    // Retain palette choice for normal page selection after the clip. The
    // first normal draw into each modified page rebuilds its band snapshot.
    memcpy(slot.palette, palette, AW_STORM_PALETTE_BYTES);
    const unsigned following = index + 1;
    if (following == AW_STORM_FRAMES) s->ready = false;
    else if (s->ahead && lcd->try_select && lcd->try_draw && s->frames[following].page != frame.page) {
        s->pending = uint8_t(following);
        s->cursor = s->frames[following].first;
        aw_storm_pump(s, p, lcd, ctx);
    }
    if (!hidden && s->ahead && !lcd->wait(ctx, 0)) return s->ready = false;
    return true;
}

bool aw_storm_present_intro(aw_display_storm *s, aw_display_pages *p, const uint8_t *pixels,
                            const uint16_t *palette, const uint32_t *identities,
                            const aw_storm_output *lcd, aw_storm_normal_fn normal, void *ctx) {
    const unsigned n = s->at++;
    auto &pre = s->prelude;
    if (n < s->first) {
        if (!pre.available)
            return render_normal(*s, pixels, palette, identities, 0, normal, ctx);
        const unsigned lead = s->first - n;
        auto &image = pre.before_flash;
        auto &ret = pre.idle_return;
        const bool return_due = lead == AW_STORM_FIRST_PRELOAD_LEAD - 1 && ret.available && ret.page < 2;
        if (return_due && ret.active && show_idle_return(*s, *p, pixels, palette, identities, *lcd, ctx)) {
            begin_before_flash(*s, *p, *lcd, ctx);
            return true;
        }
        bool lab_ready = false, before_flash = false;
        if (lead == AW_STORM_FIRST_PRELOAD_LEAD) {
            lab_ready = use_image(*p, pre.lab, aw_storm_frame_hash(pixels, palette), palette, identities);
        } else if (lead == 1) {
            pre.uploading = false;
            const uint32_t hash = aw_storm_frame_hash(pixels, palette);
            image.used = use_image(*p, image, hash, palette, identities);
            before_flash = hash == image.hash;
        }
        if (!render_normal(*s, pixels, palette, identities, 0, normal, ctx)) return false;
        if (lead <= AW_STORM_IDLE_LEAD && lead > AW_STORM_FIRST_PRELOAD_LEAD) {
            if (lead == AW_STORM_IDLE_LEAD && p->visible < 2) pre.lab.page = uint8_t(p->visible ^ 1u);
            if (pre.lab.page < 2 &&
                (p->visible != (pre.lab.page ^ 1u) || aw_storm_frame_hash(pixels, palette) != pre.idle_hash ||
                 (pre.lab.strips < AW_STORM_WARM_FRAMES && !upload_strip(*s, *p, pre.lab, *lcd, false, ctx))))
                pre.lab.page = 2;
        } else if (lab_ready && p->visible == pre.lab.page && lcd->try_select && lcd->try_draw) {
            const unsigned idle_page = p->visible ^ 1u;
            if (ret.available && p->slot[idle_page]->valid) {
                // Start updating the old page immediately after frame 2405
                // is shown. Reserve the newly freed page for 2415 afterwards.
                ret.page = uint8_t(idle_page);
                ret.cursor = ret.first;
                ret.active = true;
                s->staged = false;
                aw_storm_pump(s, p, lcd, ctx);
            } else {
                begin_before_flash(*s, *p, *lcd, ctx);
            }
        } else if (return_due && p->visible < 2) {
            begin_before_flash(*s, *p, *lcd, ctx);
        } else if (lead == 1) {
            image.used = image.used && p->visible == image.page;
            if (before_flash && p->visible < 2 && p->slot[p->visible]->valid)
                pre.saved_page = uint8_t(p->visible);
        } else if (lead < AW_STORM_FIRST_PRELOAD_LEAD && p->visible == image.page) {
            image.page = 2;
            pre.uploading = false;
        }
        return true;
    }

    const unsigned offset = n - s->first;
    if (offset >= AW_STORM_WARM_FRAMES) {
        if (aw_storm_present(s, p, offset - AW_STORM_WARM_FRAMES, pixels, palette, lcd, ctx)) return true;
        return render_normal(*s, pixels, palette, identities, 0, normal, ctx);
    }

    if (offset == 1 && pre.returning) {
        pre.returning = false;
        if (show_retained(*s, *p, pixels, palette, identities, *lcd, ctx)) {
            s->front = uint8_t(p->visible);
            s->pending = 0;
            s->cursor = s->frames[0].first;
            aw_storm_pump(s, p, lcd, ctx);
            return true;
        }
        s->ready = false;
        return render_normal(*s, pixels, palette, identities, 0, normal, ctx);
    }

    const bool queued = s->pending == 0;
    const unsigned lead = offset == AW_STORM_WARM_FRAMES - 1 && queued && pre.before_flash.used &&
        p->visible == s->front && !memcmp(p->slot[s->front]->palette, palette, AW_STORM_PALETTE_BYTES) &&
        aw_storm_frame_hash(pixels, palette) == s->warm_hash[offset] ? AW_STORM_ANCHOR_LEAD_MS : 0;
    if (!render_normal(*s, pixels, palette, identities, lead, normal, ctx)) return false;
    if (!offset && pre.available && pre.saved_page < 2 && p->visible == (pre.saved_page ^ 1u) &&
        p->slot[pre.saved_page]->valid && aw_storm_frame_hash(pixels, palette) == s->warm_hash[0]) {
        // Keep frame 2415 behind the white frame. The first lightning frame
        // can start uploading as soon as the return to the lab is visible.
        pre.returning = true;
    } else if (queued) {
        if (p->visible != s->front || aw_storm_frame_hash(pixels, palette) != s->warm_hash[offset])
            s->ready = false;
    } else {
        aw_storm_warm(s, p, offset, pixels, palette, lcd->select, lcd->draw, ctx);
    }
    return true;
}
