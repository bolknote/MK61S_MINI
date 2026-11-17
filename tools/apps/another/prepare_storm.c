/* Prepare the storm's indexed LCD windows using the original local DOS data
 * and the same interpreter and LCD page policy as ANOTHER.APP. */
#include "audio.h"
#include "display_storm.h"
#include "zx0.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { WARM_START = 2416, CLIP_START = WARM_START + AW_STORM_WARM_FRAMES };
enum { IDLE_START = WARM_START - AW_STORM_IDLE_LEAD, LAB_FRAME = WARM_START - AW_STORM_FIRST_PRELOAD_LEAD };
enum { LAB_RETURN = LAB_FRAME + 1 };
enum { PSRAM_BYTES = 2 * 1024 * 1024, LCD_PIXELS = AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT };
enum { WINDOW_COST = 3000 }; /* Approximate SPI bytes per window at 24 MHz. */

typedef struct {
    uint8_t data[AW_STORM_MAX_FILE];
    size_t bytes;
} cache_section;

typedef struct {
    const char *directory;
    aw_assets assets;
    aw_asset_entry entries[AW_ASSET_LIMIT];
    aw_video video;
    aw_vm vm;
    aw_audio audio;
    aw_video_bands bands;
    aw_display_compact first_slot;
    aw_display_pages display;
    uint8_t psram[PSRAM_BYTES], pixels[AW_VIDEO_PAGE_BYTES], spare[AW_VIDEO_PAGE_BYTES];
    uint8_t scratch[2 * AW_STORM_BLOCK];
    cache_section clip, prelude, idle_return;
    uint16_t gram[2][LCD_PIXELS], before[2][LCD_PIXELS];
    uint16_t saved_rgb[LCD_PIXELS], saved_palette[16];
    uint8_t saved_indices[AW_VIDEO_PAGE_BYTES];
    unsigned index, active, front, rectangles;
    bool palette_ready[2];
    bool prelude_ok, idle_return_ok, done;
} builder;

static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t bytes) {
    const builder *b = ctx;
    char path[4096];
    const int n = snprintf(path, sizeof(path), "%s/BANK%02X", b->directory, (unsigned)bank);
    if (n < 0 || (size_t)n >= sizeof(path)) return false;
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    const bool ok = fseek(f, (long)offset, SEEK_SET) == 0 && fread(out, 1, bytes, f) == bytes;
    fclose(f);
    return ok;
}

static bool read_psram(void *ctx, uint32_t offset, void *out, uint32_t bytes) {
    const builder *b = ctx;
    if (offset > sizeof(b->psram) || bytes > sizeof(b->psram) - offset) return false;
    memcpy(out, b->psram + offset, bytes);
    return true;
}

static bool write_psram(void *ctx, uint32_t offset, const void *data, uint32_t bytes) {
    builder *b = ctx;
    if (offset > sizeof(b->psram) || bytes > sizeof(b->psram) - offset) return false;
    memcpy(b->psram + offset, data, bytes);
    return true;
}

static bool select_page(void *ctx, unsigned page) {
    ((builder *)ctx)->active = page;
    return true;
}

static bool show_page(void *ctx, unsigned page) {
    return ((builder *)ctx)->active == page;
}

static bool draw_rect(void *ctx, unsigned x, unsigned y, unsigned w, unsigned h,
                      const uint8_t *pixels, const uint16_t *palette, bool clear) {
    builder *b = ctx;
    (void)clear;
    for (unsigned row = 0; row < h; ++row) {
        uint16_t *out = b->gram[b->active] + (y + row) * AW_VIDEO_WIDTH + x;
        for (unsigned col = 0; col < w; col += 2) {
            const uint8_t pair = *pixels++;
            out[col] = palette[pair >> 4];
            out[col + 1] = palette[pair & 15];
        }
    }
    return true;
}

static void put16(uint8_t *p, unsigned value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}

static void put32(uint8_t *p, uint32_t value) {
    put16(p, value);
    put16(p + 2, value >> 16);
}

static bool append(cache_section *section, const void *data, size_t bytes) {
    if (bytes > sizeof(section->data) - section->bytes) return false;
    memcpy(section->data + section->bytes, data, bytes);
    section->bytes += bytes;
    return true;
}

typedef struct { unsigned x, y, w, h; } rectangle;
typedef struct { unsigned y, left, right; } dirty_row;

/* A window covers all dirty pairs between two selected rows. Compute the least
 * expensive partition into windows, with separate costs for setup and pixels. */
static unsigned plan_rects(rectangle *rects, const uint16_t *old, const uint16_t *now) {
    dirty_row rows[AW_VIDEO_HEIGHT];
    unsigned count = 0;
    for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y) {
        unsigned first = AW_VIDEO_STRIDE, end = 0;
        for (unsigned x = 0; x < AW_VIDEO_STRIDE; ++x) {
            const unsigned at = y * AW_VIDEO_WIDTH + x * 2;
            if (old[at] == now[at] && old[at + 1] == now[at + 1]) continue;
            if (first == AW_VIDEO_STRIDE) first = x;
            end = x + 1;
        }
        if (end) rows[count++] = (dirty_row){y, first, end};
    }
    unsigned cost[AW_VIDEO_HEIGHT + 1], next[AW_VIDEO_HEIGHT];
    rectangle choices[AW_VIDEO_HEIGHT];
    cost[count] = 0;
    for (unsigned i = count; i--;) {
        unsigned left = AW_VIDEO_STRIDE, right = 0;
        cost[i] = UINT32_MAX;
        for (unsigned j = i; j < count; ++j) {
            if (rows[j].left < left) left = rows[j].left;
            if (rows[j].right > right) right = rows[j].right;
            const unsigned w = right - left, h = rows[j].y + 1 - rows[i].y;
            if (h > 80 || w * h > AW_STORM_BLOCK) break;
            const unsigned total = WINDOW_COST + 4 * w * h + cost[j + 1];
            if (total < cost[i]) {
                cost[i] = total;
                choices[i] = (rectangle){left, rows[i].y, w, h};
                next[i] = j + 1;
            }
        }
    }
    unsigned n = 0;
    for (unsigned i = 0; i < count; i = next[i]) rects[n++] = choices[i];
    return n;
}

static bool emit_rect(cache_section *section, rectangle r, const uint8_t *pixels,
                      const uint16_t *palette, uint16_t *rgb) {
    const unsigned size = r.w * r.h;
    uint8_t raw[AW_STORM_BLOCK];
    for (unsigned i = 0; i < r.h; ++i) {
        const unsigned at = (r.y + i) * AW_VIDEO_STRIDE + r.x;
        memcpy(raw + i * r.w, pixels + at, r.w);
        for (unsigned x = 0; rgb && x < r.w; ++x) {
            const uint8_t pair = pixels[at + x];
            rgb[(at + x) * 2] = palette[pair >> 4];
            rgb[(at + x) * 2 + 1] = palette[pair & 15];
        }
    }
    BLOCK *optimal = optimize(raw, (int)size, 0, 2176);
    int encoded, delta;
    uint8_t *packed = compress(optimal, raw, (int)size, 0, 0, 1, &encoded, &delta);
    if (!packed) return false;
    const bool smaller = encoded > 0 && (unsigned)encoded < size;
    const unsigned count = smaller ? (unsigned)encoded : size;
    uint8_t header[6] = {(uint8_t)r.x, (uint8_t)r.y, (uint8_t)r.w, (uint8_t)r.h};
    put16(header + 4, count);
    const bool ok = append(section, header, sizeof(header)) && append(section, smaller ? packed : raw, count);
    free(packed);
    return ok;
}

static void encode_palette(uint8_t colors[AW_STORM_PALETTE_BYTES], const uint16_t *palette) {
    for (unsigned i = 0; i < 16; ++i) put16(colors + 2 * i, palette[i]);
}

static bool emit_image(cache_section *section, const uint8_t *pixels, const uint16_t *palette) {
    uint8_t colors[AW_STORM_PALETTE_BYTES];
    encode_palette(colors, palette);
    if (!append(section, colors, sizeof(colors))) return false;
    for (unsigned i = 0; i < AW_STORM_WARM_FRAMES; ++i) {
        const rectangle r = {0, i * AW_STORM_STRIP_ROWS, AW_VIDEO_STRIDE, AW_STORM_STRIP_ROWS};
        if (!emit_rect(section, r, pixels, palette, NULL)) return false;
    }
    return true;
}

static uint32_t dirty_bands(const uint8_t *old, const uint8_t *pixels) {
    uint32_t bands = 0;
    const unsigned band_bytes = AW_VIDEO_BAND_ROWS * AW_VIDEO_STRIDE;
    for (unsigned i = 0; i < AW_VIDEO_BANDS; ++i) {
        const unsigned offset = i * band_bytes;
        if (memcmp(old + offset, pixels + offset, band_bytes)) bands |= 1u << i;
    }
    return bands;
}

static bool build_idle_return(builder *b, const uint8_t *pixels, const uint16_t *palette) {
    const uint32_t hash = aw_storm_frame_hash(pixels, palette);
    if (hash != 0x99833f62u) return false;

    /* These windows were measured on PicoCalc. Their horizontal splits keep
     * LCD traffic at 62836 bytes. Derive the pixels from the local DOS files
     * and verify the reconstructed RGB565 frame before saving the cache. */
    static const rectangle windows[] = {
        {71, 11, 29, 13}, {48, 24, 99, 64}, {18, 32, 30, 61}, {48, 88, 79, 65},
        {15, 126, 23, 51}, {130, 130, 16, 30}, {124, 160, 14, 27},
    };
    const unsigned count = sizeof(windows) / sizeof(windows[0]);
    uint8_t header[AW_STORM_IDLE_RETURN_HEADER];
    put32(header, hash);
    put32(header + 4, dirty_bands(b->saved_indices, pixels));
    header[8] = (uint8_t)count;
    encode_palette(header + 9, palette);
    cache_section *section = &b->idle_return;
    if (!append(section, header, sizeof(header))) return false;
    for (unsigned i = 0; i < count; ++i)
        if (!emit_rect(section, windows[i], pixels, palette, b->saved_rgb)) return false;
    return !memcmp(b->saved_rgb, b->gram[b->display.visible], sizeof(b->saved_rgb));
}

static bool build_prelude(builder *b, unsigned n, const uint8_t *pixels, const uint16_t *palette) {
    cache_section *pre = &b->prelude;
    const uint16_t *screen = b->gram[b->display.visible];
    if (n >= IDLE_START && n < LAB_FRAME) {
        const uint32_t hash = aw_storm_frame_hash(pixels, palette);
        if (hash != 0xf11dd654u) return false;
        if (n == IDLE_START) {
            memcpy(b->saved_rgb, screen, sizeof(b->saved_rgb));
            memcpy(b->saved_indices, pixels, sizeof(b->saved_indices));
        }
        put32(pre->data, hash);
    } else if (n == LAB_FRAME) {
        const uint32_t hash = aw_storm_frame_hash(pixels, palette);
        if (hash != 0x4b4da3f6u) return false;
        put32(pre->data + 4, hash);
        return emit_image(pre, pixels, palette);
    } else if (n == LAB_RETURN) {
        b->idle_return_ok = build_idle_return(b, pixels, palette);
    } else if (n == WARM_START - 1) {
        const uint32_t hash = aw_storm_frame_hash(pixels, palette);
        if (hash != 0xa0ed0567u) return false;
        put32(pre->data + 8, hash);
        memcpy(b->saved_rgb, screen, sizeof(b->saved_rgb));
        memcpy(b->saved_indices, pixels, sizeof(b->saved_indices));
        memcpy(b->saved_palette, palette, sizeof(b->saved_palette));
        return emit_image(pre, pixels, palette);
    } else if (n == WARM_START + 1) {
        if (memcmp(b->saved_palette, palette, sizeof(b->saved_palette)) ||
            aw_storm_frame_hash(pixels, palette) != 0xfacddbf4u) return false;
        rectangle rects[AW_VIDEO_HEIGHT];
        const unsigned count = plan_rects(rects, b->saved_rgb, screen);
        if (!count || count > AW_STORM_RETURN_RECTS) return false;
        put32(pre->data + 12, dirty_bands(b->saved_indices, pixels));
        pre->data[16] = (uint8_t)count;
        unsigned area = 0;
        for (unsigned i = 0; i < count; ++i) {
            area += rects[i].w * rects[i].h;
            if (area > AW_STORM_BLOCK || !emit_rect(pre, rects[i], pixels, palette, b->saved_rgb)) return false;
        }
        return !memcmp(b->saved_rgb, screen, sizeof(b->saved_rgb));
    }
    return true;
}

static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    builder *b = ctx;
    if (b->done) return true;
    const unsigned n = b->vm.part == AW_STORM_PART ? b->index++ : 0;
    if (n >= CLIP_START) memcpy(b->before, b->gram, sizeof(b->gram));
    if (!aw_display_pages_present(&b->display, pixels, palette, aw_video_band_identities(&b->video),
                                  select_page, show_page, draw_rect, NULL, b)) return false;
    if (b->prelude_ok && n >= IDLE_START && n <= WARM_START + 1)
        b->prelude_ok = build_prelude(b, n, pixels, palette);
    if (n < WARM_START) return true;
    const unsigned page = b->display.visible;
    const uint32_t hash = aw_storm_frame_hash(pixels, palette);
    if (n < CLIP_START) {
        if (n == WARM_START) {
            if (hash != 0xb918221du) return false; /* First flash in the supported DOS intro. */
            b->front = page;
        }
        if (page != b->front) return false;
        put32(b->clip.data + 12 + 4 * (n - WARM_START), hash);
        return true;
    }
    rectangle rects[AW_VIDEO_HEIGHT];
    unsigned count;
    if (n == CLIP_START) {
        if (page == b->front || hash != 0x2dde0697u) return false;
        count = AW_STORM_WARM_FRAMES;
        for (unsigned i = 0; i < count; ++i)
            rects[i] = (rectangle){0, i * AW_STORM_STRIP_ROWS, AW_VIDEO_STRIDE, AW_STORM_STRIP_ROWS};
    } else {
        count = plan_rects(rects, b->before[page], b->gram[page]);
    }
    if (count > AW_STORM_RECTS - b->rectangles) return false;
    b->rectangles += count;
    uint8_t frame[6];
    put32(frame, hash);
    frame[4] = page == b->front;
    frame[5] = (uint8_t)count;
    // Each physical page serves one of the two lightning palettes throughout
    // this sequence. Store both for uploads made before the VM reaches a frame.
    uint8_t *saved_palette = b->clip.data + 32 + frame[4] * AW_STORM_PALETTE_BYTES;
    uint8_t colors[AW_STORM_PALETTE_BYTES];
    encode_palette(colors, palette);
    if (!b->palette_ready[frame[4]]) {
        memcpy(saved_palette, colors, sizeof(colors));
        b->palette_ready[frame[4]] = true;
    } else if (memcmp(saved_palette, colors, sizeof(colors))) {
        return false;
    }
    if (!append(&b->clip, frame, sizeof(frame))) return false;
    for (unsigned i = 0; i < count; ++i)
        if (!emit_rect(&b->clip, rects[i], pixels, palette, b->before[page])) return false;
    if (memcmp(b->before[page], b->gram[page], sizeof(b->gram[page]))) return false;
    b->done = n == CLIP_START + AW_STORM_FRAMES - 1;
    return true;
}

static bool frame_wait(void *ctx, unsigned slices) {
    builder *b = ctx;
    if (slices > 500) return false;
    int16_t samples[AW_AUDIO_BLOCK];
    for (unsigned left = slices * 500; left;) {
        const unsigned n = left < AW_AUDIO_BLOCK ? left : AW_AUDIO_BLOCK;
        if (!aw_audio_render(&b->audio, samples, n)) return false;
        left -= n;
    }
    return true;
}

static void sound(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel) {
    aw_audio_sound(&((builder *)ctx)->audio, id, freq, volume, channel);
}

static void music(void *ctx, unsigned id, unsigned delay, unsigned pos) {
    aw_audio_music(&((builder *)ctx)->audio, id, delay, pos);
}

static void stop_audio(void *ctx) { aw_audio_stop(&((builder *)ctx)->audio); }

static bool build(builder *b) {
    char path[4096];
    const int n = snprintf(path, sizeof(path), "%s/MEMLIST.BIN", b->directory);
    if (n < 0 || (size_t)n >= sizeof(path)) return false;
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    uint8_t list[4097];
    const size_t bytes = fread(list, 1, sizeof(list), f);
    const bool read_ok = !ferror(f) && bytes < sizeof(list);
    fclose(f);
    if (!read_ok || !aw_assets_init(&b->assets, b->entries, list, bytes, sizeof(b->psram), b,
                                   bank_read, read_psram, write_psram)) return false;
    const uint32_t base = b->assets.used;
    const aw_vm_host host = {b, frame_wait, NULL, sound, music, stop_audio};
    if (!aw_video_init(&b->video, &b->assets, base, b->pixels, present, b) ||
        !aw_video_use_spare(&b->video, b->spare) ||
        !aw_display_compact_init(&b->first_slot, &b->assets, base + 4 * AW_VIDEO_PAGE_BYTES,
                                 b->scratch, sizeof(b->scratch), b->scratch, sizeof(b->scratch)) ||
        !aw_display_pages_init(&b->display, &b->first_slot,
                              base + 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES) ||
        !aw_vm_init(&b->vm, &b->assets, &b->video, host, 1)) return false;
    aw_video_track_bands(&b->video, &b->bands);
    aw_audio_init(&b->audio, &b->assets, &b->vm);
    if (!aw_vm_set_part(&b->vm, AW_VM_FIRST_PART)) return false;
    aw_input input = {0};
    b->clip.bytes = AW_STORM_HEADER + AW_STORM_PALETTE_BYTES;
    b->prelude.bytes = AW_STORM_PRELUDE_HEADER;
    b->prelude_ok = true;
    memcpy(b->clip.data, "AWS2", 4);
    put16(b->clip.data + 8, WARM_START);
    for (unsigned i = 0; i < 4800 && !b->done && b->vm.part <= AW_STORM_PART; ++i)
        if (!aw_vm_frame(&b->vm, &input)) return false;
    if (b->prelude_ok && append(&b->clip, b->prelude.data, b->prelude.bytes)) {
        b->clip.data[3] = '3';
        if (b->idle_return_ok && append(&b->clip, b->idle_return.data, b->idle_return.bytes))
            b->clip.data[3] = '4';
    }
    uint32_t hash = AW_STORM_HASH_INIT;
    for (size_t i = 8; i < b->clip.bytes; ++i) hash = aw_storm_hash_byte(hash, b->clip.data[i]);
    put32(b->clip.data + 4, hash);
    return b->done;
}

int main(int argc, char **argv) {
    if (argc != 3) return 1;
    builder *b = calloc(1, sizeof(*b));
    if (!b) return 1;
    b->directory = argv[1];
    if (!build(b)) {
        fprintf(stderr, "The DOS files did not produce the supported storm sequence.\n");
        free(b);
        return 2;
    }
    FILE *f = fopen(argv[2], "wb");
    if (!f) { free(b); return 1; }
    const bool wrote = fwrite(b->clip.data, 1, b->clip.bytes, f) == b->clip.bytes;
    const bool closed = fclose(f) == 0;
    free(b);
    return wrote && closed ? 0 : 1;
}
