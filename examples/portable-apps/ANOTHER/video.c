/* Polygon and page semantics follow Raw, Copyright (C) 2004 Gregory Montoir,
 * GPL-2.0-or-later. Pages and shape data use the portable PSRAM asset store. */
#include "video.h"
#include <string.h>

static uint8_t page_id(const aw_video *v, uint8_t page) {
    if (page < 4) return page;
    if (page == 0xFE) return v->front_page;
    if (page == 0xFF) return v->back_page;
    return 0;
}
static uint32_t page_at(const aw_video *v, unsigned page) {
    return v->page_base + page * AW_VIDEO_PAGE_BYTES;
}
static void mark_dirty(aw_video *v) {
    v->dirty = true;
    if (v->resident_page == 0) {
        v->background_valid = false;
        v->background_attempted = false;
    }
    if (v->resident_page == 3) {
        v->page3_packed_valid = false;
        v->page3_packed_attempted = false;
        v->page3_seen_copy = false;
    }
}
static uint8_t *background_at(const aw_video *v, unsigned pos) {
    return pos < v->background_split ? v->background + pos : v->background_tail + pos - v->background_split;
}
static void background_copy_to(const aw_video *v, unsigned pos, const uint8_t *data, unsigned size) {
    if (pos < v->background_split) {
        const unsigned first = size < v->background_split - pos ? size : v->background_split - pos;
        memcpy(v->background + pos, data, first); pos += first; data += first; size -= first;
    }
    if (size) memcpy(v->background_tail + pos - v->background_split, data, size);
}
static void background_copy_from(const aw_video *v, unsigned pos, uint8_t *data, unsigned size) {
    if (pos < v->background_split) {
        const unsigned first = size < v->background_split - pos ? size : v->background_split - pos;
        memcpy(data, v->background + pos, first); pos += first; data += first; size -= first;
    }
    if (size) memcpy(data, v->background_tail + pos - v->background_split, size);
}
/* Each packed row contains literal and run packets. The row index allows
 * polygon spans to read the background without expanding the whole page. */
static void cache_background(aw_video *v, const uint8_t *pixels) {
    if (!v->background || v->background_attempted) return;
    v->background_attempted = true; v->background_valid = false;
    unsigned used = 0;
    for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y) {
        v->background_offsets[y] = (uint16_t)used;
        const uint8_t *row = pixels + y * AW_VIDEO_STRIDE;
        unsigned x = 0;
        while (x < AW_VIDEO_STRIDE) {
            unsigned run = 1;
            while (x + run < AW_VIDEO_STRIDE && run < 128 && row[x + run] == row[x]) ++run;
            if (run >= 3) {
                if (used + 2 > v->background_capacity) return;
                *background_at(v, used++) = (uint8_t)(128u | (run - 1));
                *background_at(v, used++) = row[x]; x += run;
            } else {
                unsigned n = 0;
                while (x + n < AW_VIDEO_STRIDE && n < 128) {
                    unsigned at = x + n, r = 1;
                    while (at + r < AW_VIDEO_STRIDE && r < 3 && row[at + r] == row[at]) ++r;
                    if (r >= 3) break;
                    ++n;
                }
                if (!n || used + 1 + n > v->background_capacity) return;
                *background_at(v, used++) = (uint8_t)(n - 1);
                background_copy_to(v, used, row + x, n); used += n; x += n;
            }
        }
        if ((y & 31u) == 31u) aw_assets_progress(v->assets);
    }
    v->background_offsets[AW_VIDEO_HEIGHT] = (uint16_t)used;
    v->background_size = (uint16_t)used; v->background_valid = true;
}
static bool background_read(aw_video *v, unsigned y, unsigned from, unsigned size, uint8_t *out) {
    if (!v->background_valid || y >= AW_VIDEO_HEIGHT || from > AW_VIDEO_STRIDE || size > AW_VIDEO_STRIDE - from)
        return false;
    unsigned pos = v->background_offsets[y], end = v->background_offsets[y + 1], x = 0;
    const unsigned wanted_end = from + size;
    if (pos > end || end > v->background_size) return false;
    while (pos < end && x < wanted_end) {
        const uint8_t code = *background_at(v, pos++);
        const unsigned count = (code & 127u) + 1u;
        if (count > AW_VIDEO_STRIDE - x) return false;
        const unsigned left = x > from ? x : from, right = x + count < wanted_end ? x + count : wanted_end;
        if (code & 128u) {
            if (pos >= end) return false;
            const uint8_t value = *background_at(v, pos++);
            if (left < right) memset(out + left - from, value, right - left);
        } else {
            if (count > end - pos) return false;
            if (left < right) background_copy_from(v, pos + left - x, out + left - from, right - left);
            pos += count;
        }
        x += count;
    }
    return x >= wanted_end;
}

/* Page 3 is often copied repeatedly without being modified. Keep a second,
 * compressed copy in unused PSRAM and stream it through a small stack buffer
 * instead of rereading a whole 32 KiB page on every full-page restore. */
typedef struct {
    aw_video *video;
    uint32_t written;
    unsigned used;
    uint8_t bytes[1024];
} page3_writer;
static bool page3_flush(page3_writer *w) {
    if (!w->used) return true;
    if (!aw_assets_write(w->video->assets, w->video->page3_packed_base + w->written, w->bytes, w->used))
        return !(w->video->fault = true);
    w->written += w->used; w->used = 0; aw_assets_progress(w->video->assets); return true;
}
static bool page3_append(page3_writer *w, const uint8_t *data, unsigned size) {
    while (size) {
        const unsigned n = size < sizeof(w->bytes) - w->used ? size : sizeof(w->bytes) - w->used;
        memcpy(w->bytes + w->used, data, n); w->used += n; data += n; size -= n;
        if (w->used == sizeof(w->bytes) && !page3_flush(w)) return false;
    }
    return true;
}
static bool cache_page3(aw_video *v, const uint8_t *pixels) {
    if (!v->page3_packed_capacity || v->page3_packed_attempted) return true;
    v->page3_packed_attempted = true; v->page3_packed_valid = false;
    page3_writer w; w.video = v; w.written = 0; w.used = 0; unsigned x = 0;
    while (x < AW_VIDEO_PAGE_BYTES) {
        unsigned run = 1;
        while (x + run < AW_VIDEO_PAGE_BYTES && run < 128 && pixels[x + run] == pixels[x]) ++run;
        if (run >= 3) {
            const uint8_t packet[2] = {(uint8_t)(128u | (run - 1)), pixels[x]};
            if (w.written + w.used + sizeof(packet) > v->page3_packed_capacity) return true;
            if (!page3_append(&w, packet, sizeof(packet))) return false;
            x += run;
        } else {
            unsigned n = 0;
            while (x + n < AW_VIDEO_PAGE_BYTES && n < 128) {
                unsigned at = x + n, r = 1;
                while (at + r < AW_VIDEO_PAGE_BYTES && r < 3 && pixels[at + r] == pixels[at]) ++r;
                if (r >= 3) break;
                ++n;
            }
            if (!n || w.written + w.used + 1 + n > v->page3_packed_capacity) return true;
            const uint8_t header = (uint8_t)(n - 1);
            if (!page3_append(&w, &header, 1) || !page3_append(&w, pixels + x, n)) return false;
            x += n;
        }
    }
    if (!page3_flush(&w)) return false;
    v->page3_packed_size = (uint16_t)w.written; v->page3_packed_valid = true; return true;
}
typedef struct {
    aw_video *video;
    unsigned fetched, at, used, consumed;
    uint8_t bytes[1024];
} page3_reader;
static bool page3_read(page3_reader *r, uint8_t *out, unsigned size) {
    while (size) {
        if (r->at == r->used) {
            const unsigned left = r->video->page3_packed_size - r->fetched;
            if (!left) return false;
            r->used = left < sizeof(r->bytes) ? left : sizeof(r->bytes); r->at = 0;
            if (!aw_assets_read(r->video->assets, r->video->page3_packed_base + r->fetched, r->bytes, r->used))
                return !(r->video->fault = true);
            r->fetched += r->used; aw_assets_progress(r->video->assets);
        }
        const unsigned n = size < r->used - r->at ? size : r->used - r->at;
        memcpy(out, r->bytes + r->at, n); r->at += n; r->consumed += n; out += n; size -= n;
    }
    return true;
}
static bool unpack_page3(aw_video *v, uint8_t *pixels) {
    if (!v->page3_packed_valid) return false;
    page3_reader r; r.video = v; r.fetched = r.at = r.used = r.consumed = 0; unsigned x = 0;
    while (x < AW_VIDEO_PAGE_BYTES) {
        uint8_t code; if (!page3_read(&r, &code, 1)) return false;
        const unsigned count = (code & 127u) + 1u;
        if (count > AW_VIDEO_PAGE_BYTES - x) return false;
        if (code & 128u) {
            uint8_t value; if (!page3_read(&r, &value, 1)) return false;
            memset(pixels + x, value, count);
        } else if (!page3_read(&r, pixels + x, count)) return false;
        x += count;
    }
    return r.consumed == v->page3_packed_size;
}
static bool transfer(aw_video *v, bool write, uint32_t offset, uint8_t *bytes, uint32_t count) {
    while (count) {
        const uint32_t n = count < 4096 ? count : 4096;
        const bool ok = write ? aw_assets_write(v->assets, offset, bytes, n) : aw_assets_read(v->assets, offset, bytes, n);
        if (!ok) return false;
        offset += n; bytes += n; count -= n; aw_assets_progress(v->assets);
    }
    return true;
}
bool aw_video_flush(aw_video *v) {
    if (!v || v->fault) return false;
    bool wrote = false;
    if (v->resident_valid && v->dirty) {
        if (!transfer(v, true, page_at(v, v->resident_page), v->pixels, AW_VIDEO_PAGE_BYTES))
            return !(v->fault = true);
        v->dirty = false; wrote = true;
    }
    if (v->spare_valid && v->spare_dirty) {
        if (!transfer(v, true, page_at(v, v->spare_page), v->spare, AW_VIDEO_PAGE_BYTES))
            return !(v->fault = true);
        v->spare_dirty = false; wrote = true;
    }
    return !wrote || aw_assets_flush(v->assets) || !(v->fault = true);
}
static void swap_resident(aw_video *v) {
    uint8_t *p = v->pixels; v->pixels = v->spare; v->spare = p;
    const uint8_t old_page = v->resident_page; v->resident_page = v->spare_page; v->spare_page = old_page;
    const bool valid = v->resident_valid, dirty = v->dirty;
    v->resident_valid = v->spare_valid; v->dirty = v->spare_dirty;
    v->spare_valid = valid; v->spare_dirty = dirty;
}
static bool resident(aw_video *v, uint8_t page) {
    if (v->fault || page > 3) return false;
    if (v->resident_valid && v->resident_page == page) return true;
    if (v->spare) {
        if (!v->spare_valid || v->spare_page != page) {
            if (v->spare_valid && v->spare_page == 0) cache_background(v, v->spare);
            if (v->spare_valid && v->spare_dirty &&
                (!transfer(v, true, page_at(v, v->spare_page), v->spare, AW_VIDEO_PAGE_BYTES) ||
                 !aw_assets_flush(v->assets))) return !(v->fault = true);
            v->spare_valid = false; v->spare_dirty = false;
            if (!transfer(v, false, page_at(v, page), v->spare, AW_VIDEO_PAGE_BYTES))
                return !(v->fault = true);
            v->spare_page = page; v->spare_valid = true;
        }
        swap_resident(v);
        return true;
    }
    if (!aw_video_flush(v) || !transfer(v, false, page_at(v, page), v->pixels, AW_VIDEO_PAGE_BYTES))
        return !(v->fault = true);
    v->resident_valid = true; v->resident_page = page;
    return true;
}
bool aw_video_init(aw_video *v, aw_assets *a, uint32_t base, uint8_t *pixels,
                   aw_video_present_fn present, void *ctx) {
    if (!v || !a || !pixels || !present || base < a->used || base > a->capacity ||
        4 * AW_VIDEO_PAGE_BYTES > a->capacity - base) return false;
    memset(v, 0, sizeof(*v));
    v->assets = a; v->pixels = pixels; v->page_base = base; v->present = present; v->present_ctx = ctx;
    v->front_page = 2; v->back_page = 1; v->draw_page = 2;
    v->interp[0] = 0x4000;
    for (unsigned i = 1; i < AW_VIDEO_INTERP_SLOTS; ++i) v->interp[i] = (uint16_t)(0x4000 / i);
    memset(pixels, 0, AW_VIDEO_PAGE_BYTES);
    for (unsigned i = 0; i < 4; ++i)
        if (!transfer(v, true, page_at(v, i), pixels, AW_VIDEO_PAGE_BYTES)) return !(v->fault = true);
    if (!aw_assets_flush(a)) return !(v->fault = true);
    v->resident_valid = true; v->resident_page = 2;
    return true;
}
bool aw_video_use_spare(aw_video *v, uint8_t *pixels) {
    if (!v || v->fault || !pixels || pixels == v->pixels || v->spare) return false;
    v->spare = pixels; v->spare_valid = v->spare_dirty = false; return true;
}
bool aw_video_use_background(aw_video *v, uint8_t *buffer, uint16_t capacity) {
    return aw_video_use_background_split(v, buffer, capacity, NULL, 0);
}
bool aw_video_use_background_split(aw_video *v, uint8_t *first, uint16_t first_size,
                                   uint8_t *second, uint16_t second_size) {
    if (!v || v->fault || !first || !first_size || v->background || first == v->pixels || first == v->spare ||
        (!!second != !!second_size) || (second && (second == first || second == v->pixels || second == v->spare)) ||
        (unsigned)first_size + second_size > UINT16_MAX)
        return false;
    v->background = first; v->background_tail = second; v->background_split = first_size;
    v->background_capacity = first_size + second_size; return true;
}
bool aw_video_use_packed_page3(aw_video *v, uint32_t base, uint16_t capacity) {
    if (!v || v->fault || !capacity || v->page3_packed_capacity ||
        base < v->page_base || base - v->page_base < 5 * AW_VIDEO_PAGE_BYTES || base > v->assets->capacity ||
        capacity > v->assets->capacity - base) return false;
    v->page3_packed_base = base; v->page3_packed_capacity = capacity; return true;
}
bool aw_video_select(aw_video *v, uint8_t page) {
    if (!v || v->fault) return false;
    v->draw_page = page_id(v, page);
    return resident(v, v->draw_page);
}
bool aw_video_fill(aw_video *v, uint8_t page, uint8_t color) {
    if (!v || !resident(v, page_id(v, page))) return false;
    color &= 15u;
    memset(v->pixels, (color << 4) | color, AW_VIDEO_PAGE_BYTES);
    mark_dirty(v);
    return true;
}
bool aw_video_copy(aw_video *v, uint8_t src, uint8_t dst, int16_t scroll) {
    if (!v || v->fault) return false;
    if (src == dst) return true;
    bool scrolled = false;
    if (src < 0xFE) { src &= 0xBF; scrolled = (src & 0x80) != 0; if (scrolled) src &= 3; }
    src = page_id(v, src); dst = page_id(v, dst);
    if (scrolled && (scroll < -199 || scroll > 199)) return true;
    uint32_t from = 0, to = 0, size = AW_VIDEO_PAGE_BYTES;
    if (scrolled) {
        if (scroll < 0) { from = (uint32_t)(-scroll) * AW_VIDEO_STRIDE; size -= from; }
        else { to = (uint32_t)scroll * AW_VIDEO_STRIDE; size -= to; }
    }
    /* When copying from the second resident page to an uncached one, keep
     * the source in SRAM instead of evicting and rereading it. */
    if (src != dst && v->spare_valid && v->spare_page == src && v->resident_page != dst)
        swap_resident(v);
    if (!resident(v, dst)) return false;
    if (src == dst) memmove(v->pixels + to, v->pixels + from, size);
    else if (v->spare_valid && v->spare_page == src) memcpy(v->pixels + to, v->spare + from, size);
    else if (src == 0 && v->background_valid) {
        for (unsigned row = 0; row < size / AW_VIDEO_STRIDE; ++row) {
            if (!background_read(v, from / AW_VIDEO_STRIDE + row, 0, AW_VIDEO_STRIDE,
                                 v->pixels + to + row * AW_VIDEO_STRIDE)) return !(v->fault = true);
            if ((row & 31u) == 31u) aw_assets_progress(v->assets);
        }
    } else if (src == 3 && from == 0 && to == 0 && size == AW_VIDEO_PAGE_BYTES && v->page3_packed_valid) {
        if (!unpack_page3(v, v->pixels)) {
            v->page3_packed_valid = false;
            if (v->fault || !transfer(v, false, page_at(v, src), v->pixels, size)) return !(v->fault = true);
        }
    } else if (!transfer(v, false, page_at(v, src) + from, v->pixels + to, size))
        return !(v->fault = true);
    if (src == 3 && dst != 3 && from == 0 && to == 0 && size == AW_VIDEO_PAGE_BYTES) {
        if (v->page3_seen_copy) { if (!cache_page3(v, v->pixels)) return false; }
        else v->page3_seen_copy = true;
    }
    mark_dirty(v);
    return true;
}
bool aw_video_bitmap(aw_video *v, uint32_t source, uint32_t size) {
    if (!v || size < AW_VIDEO_PAGE_BYTES || !resident(v, 0)) return false;
    uint8_t plane[4][40];
    for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y) {
        for (unsigned p = 0; p < 4; ++p)
            if (!aw_assets_read(v->assets, source + (3 - p) * 8000 + y * 40, plane[p], 40))
                return !(v->fault = true);
        for (unsigned x = 0; x < 40; ++x) {
            for (unsigned pair = 0; pair < 4; ++pair) {
                uint8_t pixels = 0;
                for (unsigned pixel = 0; pixel < 2; ++pixel)
                    for (unsigned p = 0; p < 4; ++p) {
                        pixels = (uint8_t)((pixels << 1) | ((plane[p][x] & 0x80) != 0));
                        plane[p][x] <<= 1;
                    }
                v->pixels[y * AW_VIDEO_STRIDE + x * 4 + pair] = pixels;
            }
        }
        if ((y & 7u) == 7u) aw_assets_progress(v->assets);
    }
    mark_dirty(v);
    return true;
}
bool aw_video_palette(aw_video *v, uint32_t source, uint32_t size, uint8_t index) {
    uint8_t bytes[32];
    if (!v || index >= 32 || (uint32_t)index * 32 + 32 > size ||
        !aw_assets_read(v->assets, source + (uint32_t)index * 32, bytes, sizeof(bytes))) return false;
    for (unsigned i = 0; i < 16; ++i) {
        const unsigned r = bytes[2 * i] & 15, g = bytes[2 * i + 1] >> 4, b = bytes[2 * i + 1] & 15;
        v->palette[i] = (uint16_t)((((r << 1) | (r >> 3)) << 11) |
                                  (((g << 2) | (g >> 2)) << 5) | ((b << 1) | (b >> 3)));
    }
    return true;
}
bool aw_video_show(aw_video *v, uint8_t page) {
    if (!v || v->fault) return false;
    if (page == 0xFF) { uint8_t t = v->front_page; v->front_page = v->back_page; v->back_page = t; }
    else if (page != 0xFE) v->front_page = page_id(v, page);
    if (!resident(v, v->front_page) || !v->present(v->present_ctx, v->pixels, v->palette))
        return !(v->fault = true);
    return true;
}
bool aw_video_char(aw_video *v, uint16_t x, uint16_t y, uint8_t color, const uint8_t glyph[8]) {
    if (!v || !glyph || !resident(v, v->draw_page)) return false;
    if (x > 39 || y > 192) return true;
    for (unsigned row = 0; row < 8; ++row) {
        uint8_t bits = glyph[row];
        for (unsigned i = 0; i < 8; ++i, bits <<= 1) if (bits & 0x80) {
            uint8_t *p = v->pixels + (y + row) * AW_VIDEO_STRIDE + x * 4 + i / 2;
            if (i & 1) *p = (uint8_t)((*p & 0xF0) | (color & 15));
            else *p = (uint8_t)((*p & 0x0F) | ((color & 15) << 4));
        }
    }
    mark_dirty(v);
    return true;
}

typedef struct { int16_t x, y; } point;
typedef struct {
    aw_video *v;
    uint32_t cursor;
    point vertices[50];
    uint16_t width, height;
    uint8_t count;
} shape;
static uint8_t fetch(shape *s) {
    uint8_t value = 0;
    if (s->cursor >= s->v->shape_size ||
        !aw_assets_read(s->v->assets, s->v->shape_base + s->cursor, &value, 1)) {
        s->v->fault = true; return 0;
    }
    ++s->cursor;
    return value;
}
static uint16_t fetch16(shape *s) {
    const uint16_t hi = fetch(s);
    return (uint16_t)((hi << 8) | fetch(s));
}
static void edge(uint8_t *p, uint8_t mask, uint8_t color, uint8_t source) {
    if (color == 0x10) *p |= (uint8_t)(mask & 0x88);
    else {
        const uint8_t c = color > 0x10 ? source : (uint8_t)((color << 4) | color);
        *p = (uint8_t)((*p & ~mask) | (c & mask));
    }
}
static bool line(aw_video *v, int x1, int x2, int y, uint8_t color) {
    if (y < 0 || y >= 200 || x2 < 0 || x1 >= 320) return true;
    if (x1 > x2) { int t = x1; x1 = x2; x2 = t; }
    if (x1 < 0) x1 = 0;
    if (x2 > 319) x2 = 319;
    const unsigned from = (unsigned)x1 / 2, to = (unsigned)x2 / 2;
    uint8_t source[AW_VIDEO_STRIDE];
    if (color > 0x10) {
        if (v->resident_page == 0) return true;
        if (v->spare_valid && v->spare_page == 0)
            memcpy(source, v->spare + (unsigned)y * AW_VIDEO_STRIDE + from, to - from + 1);
        else if (v->background_valid) {
            if (!background_read(v, (unsigned)y, from, to - from + 1, source)) return !(v->fault = true);
        } else if (!aw_assets_read(v->assets, page_at(v, 0) + (unsigned)y * AW_VIDEO_STRIDE + from,
                                 source, to - from + 1)) return !(v->fault = true);
    }
    uint8_t *row = v->pixels + (unsigned)y * AW_VIDEO_STRIDE;
    if (from == to) {
        const uint8_t mask = (uint8_t)((x1 & 1 ? 0x0F : 0xFF) & (x2 & 1 ? 0xFF : 0xF0));
        edge(row + from, mask, color, color > 0x10 ? source[0] : 0);
    } else {
        unsigned begin = from, end = to + 1;
        if (x1 & 1) { edge(row + begin, 0x0F, color, color > 0x10 ? source[0] : 0); ++begin; }
        if (!(x2 & 1)) { --end; edge(row + end, 0xF0, color, color > 0x10 ? source[end - from] : 0); }
        if (begin < end) {
            if (color < 0x10) memset(row + begin, (color << 4) | color, end - begin);
            else if (color == 0x10) for (unsigned i = begin; i < end; ++i) row[i] |= 0x88;
            else memcpy(row + begin, source + begin - from, end - begin);
        }
    }
    mark_dirty(v);
    return true;
}
static bool fill_polygon(shape *s, uint8_t color, point center) {
    aw_video *v = s->v;
    if (!s->width && s->height == 1 && s->count == 4) return line(v, center.x, center.x, center.y, color);
    int x1 = center.x - s->width / 2, x2 = center.x + s->width / 2;
    int y = center.y - s->height / 2, y2 = center.y + s->height / 2;
    if (x1 > 319 || x2 < 0 || y > 199 || y2 < 0) return true;
    unsigned i = 0, j = s->count - 1;
    x2 = s->vertices[i++].x + x1; x1 = s->vertices[j--].x + x1;
    uint32_t c1 = (uint32_t)(int32_t)x1 * 65536u, c2 = (uint32_t)(int32_t)x2 * 65536u;
    unsigned remaining = s->count;
    while ((remaining -= 2) != 0) {
        const int dy1 = s->vertices[j].y - s->vertices[j + 1].y;
        const int dy2 = s->vertices[i].y - s->vertices[i - 1].y;
        if (dy1 < 0 || dy1 >= 1024 || dy2 < 0 || dy2 >= 1024) return !(v->fault = true);
        const unsigned factor1 = (unsigned)dy1 < AW_VIDEO_INTERP_SLOTS ? v->interp[dy1] : 0x4000u / (unsigned)dy1;
        const unsigned factor2 = (unsigned)dy2 < AW_VIDEO_INTERP_SLOTS ? v->interp[dy2] : 0x4000u / (unsigned)dy2;
        const int32_t step1 = (s->vertices[j].x - s->vertices[j + 1].x) * (int32_t)factor1 * 4;
        const int32_t step2 = (s->vertices[i].x - s->vertices[i - 1].x) * (int32_t)factor2 * 4;
        ++i; --j;
        c1 = (c1 & 0xFFFF0000u) | 0x7FFFu; c2 = (c2 & 0xFFFF0000u) | 0x8000u;
        if (!dy2) { c1 += (uint32_t)step1; c2 += (uint32_t)step2; }
        else for (int h = dy2; h; --h) {
            if (y >= 0 && !line(v, (int16_t)(c1 >> 16), (int16_t)(c2 >> 16), y, color)) return false;
            c1 += (uint32_t)step1; c2 += (uint32_t)step2;
            if (++y > 199) return true;
            if (!(y & 31)) aw_assets_progress(v->assets);
        }
    }
    return true;
}
static bool draw_shape(shape *s, uint8_t color, uint16_t zoom, point at, unsigned depth) {
    if (depth > 32 || s->v->fault) return !(s->v->fault = true);
    const uint8_t kind = fetch(s);
    if (kind >= 0xC0) {
        if (color & 0x80) color = kind & 0x3F;
        s->width = (uint16_t)(fetch(s) * (uint32_t)zoom / 64);
        s->height = (uint16_t)(fetch(s) * (uint32_t)zoom / 64);
        s->count = fetch(s);
        if (s->count < 2 || s->count >= 50 || (s->count & 1)) return !(s->v->fault = true);
        for (unsigned i = 0; i < s->count; ++i) {
            s->vertices[i].x = (int16_t)(fetch(s) * (uint32_t)zoom / 64);
            s->vertices[i].y = (int16_t)(fetch(s) * (uint32_t)zoom / 64);
        }
        return !s->v->fault && fill_polygon(s, color, at);
    }
    if ((kind & 0x3F) != 2) return !(s->v->fault = true);
    at.x -= (int16_t)(fetch(s) * (uint32_t)zoom / 64);
    at.y -= (int16_t)(fetch(s) * (uint32_t)zoom / 64);
    unsigned children = fetch(s) + 1u;
    while (children-- && !s->v->fault) {
        uint16_t offset = fetch16(s);
        const int dx = (int)(fetch(s) * (uint32_t)zoom / 64);
        const int dy = (int)(fetch(s) * (uint32_t)zoom / 64);
        point child = { (int16_t)(at.x + dx), (int16_t)(at.y + dy) };
        uint8_t child_color = 0xFF;
        if (offset & 0x8000) { child_color = fetch(s) & 0x7F; (void)fetch(s); }
        const uint32_t saved = s->cursor;
        s->cursor = (uint32_t)(offset & 0x7FFF) * 2;
        if (!draw_shape(s, child_color, zoom, child, depth + 1)) return false;
        s->cursor = saved;
    }
    return !s->v->fault;
}
bool aw_video_polygon(aw_video *v, uint32_t base, uint32_t size, uint16_t offset,
                      uint16_t zoom, int16_t x, int16_t y) {
    if (!v || base > v->assets->capacity || size > v->assets->capacity - base || offset >= size ||
        !resident(v, v->draw_page)) return false;
    v->shape_base = base; v->shape_size = size;
    shape s = {0}; s.v = v; s.cursor = offset;
    const point at = {x, y};
    return draw_shape(&s, 0xFF, zoom, at, 0);
}
