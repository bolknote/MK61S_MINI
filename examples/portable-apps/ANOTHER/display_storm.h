#ifndef MK61_ANOTHER_DISPLAY_STORM_H
#define MK61_ANOTHER_DISPLAY_STORM_H

#include "display_pages.h"

/* AWS1 through AWS4 are local caches of one DOS intro sequence. Frame indices are
 * relative to the intro part, independent of the copy-protection screen. */
#define AW_STORM_PART 0x3E81u
#define AW_STORM_WARM_FRAMES 5u
#define AW_STORM_STRIP_ROWS (AW_VIDEO_HEIGHT / AW_STORM_WARM_FRAMES)
#define AW_STORM_FRAMES 18u
#define AW_STORM_RECTS 48u
#define AW_STORM_RETURN_RECTS 8u
#define AW_STORM_IDLE_RETURN_RECTS 12u
#define AW_STORM_PRELUDE_RECTS (2u * AW_STORM_WARM_FRAMES + AW_STORM_RETURN_RECTS + AW_STORM_IDLE_RETURN_RECTS)
#define AW_STORM_IDLE_LEAD 26u
#define AW_STORM_FIRST_PRELOAD_LEAD 11u
#define AW_STORM_ANCHOR_LEAD_MS 8u
#define AW_STORM_BLOCK (AW_VIDEO_STRIDE * AW_STORM_STRIP_ROWS)
#define AW_STORM_HEADER 64u
#define AW_STORM_PRELUDE_HEADER 17u
#define AW_STORM_PALETTE_BYTES 32u
#define AW_STORM_IDLE_RETURN_HEADER (9u + AW_STORM_PALETTE_BYTES)
#define AW_STORM_IDLE_RETURN_RESERVE 8192u
#define AW_STORM_MAX_FILE 65536u
#define AW_STORM_HASH_INIT 2166136261u

typedef struct {
    uint32_t offset;
    uint8_t x, y, width, height; /* Horizontal coordinates are in packed pairs. */
} aw_storm_rect;

typedef struct {
    uint32_t hash;
    uint8_t page, first, end;
} aw_storm_frame;

typedef struct {
    uint32_t hash;
    uint16_t palette[16];
    uint8_t first, page, strips;
    bool used;
} aw_storm_image;

typedef struct {
    uint32_t hash, dirty_bands;
    uint16_t palette[16];
    uint8_t first, end, cursor, page;
    bool available, active;
} aw_storm_idle_return;

typedef struct {
    aw_storm_image lab, before_flash;
    aw_storm_idle_return idle_return;
    uint32_t idle_hash, dirty_bands;
    uint8_t return_first, return_end, saved_page;
    bool available, uploading, returning;
} aw_storm_prelude;

typedef struct {
    aw_storm_frame frames[AW_STORM_FRAMES];
    aw_storm_rect rects[AW_STORM_RECTS + AW_STORM_PRELUDE_RECTS];
    aw_storm_prelude prelude;
    uint32_t warm_hash[AW_STORM_WARM_FRAMES];
    uint16_t palette[2][16], first, at;
    uint8_t warmed, front;
    uint8_t pending, cursor;
    bool ready, ahead, staged, rendering;
} aw_display_storm;

typedef bool (*aw_storm_read_fn)(void *ctx, uint32_t offset, void *out, uint32_t size);

/* The nonblocking callbacks return 1 on acceptance, 2 while the LCD worker
 * is busy and 0 on failure. A successful draw has copied the input pixels. */
typedef struct {
    aw_display_page_fn select, show;
    aw_display_rect_fn draw;
    bool (*wait)(void *ctx, unsigned lead_ms);
    unsigned (*try_select)(void *ctx, unsigned page);
    unsigned (*try_draw)(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                         const uint8_t *pixels, const uint16_t *palette, bool clear);
    uint32_t spi_hz;
} aw_storm_output;

typedef bool (*aw_storm_normal_fn)(void *ctx, const uint8_t *pixels, const uint16_t *palette,
                                   const uint32_t *identities, unsigned lead_ms);

static inline uint32_t aw_storm_hash_byte(uint32_t hash, uint8_t byte) {
    return (hash ^ byte) * 16777619u;
}

/* Fingerprint the whole indexed image before reusing cached rectangles. The
 * app's video buffers are word-aligned, but host callers need not align them. */
static inline uint32_t aw_storm_frame_hash(const uint8_t *pixels, const uint16_t *palette) {
    uint32_t hash = AW_STORM_HASH_INIT;
#if defined(__GNUC__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if (!((uintptr_t)pixels & 3u)) {
        const uint8_t *aligned = (const uint8_t *)__builtin_assume_aligned(pixels, 4);
        for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; i += 4) {
            uint32_t word;
            __builtin_memcpy(&word, aligned + i, sizeof(word));
            hash = (hash ^ word) * 16777619u;
        }
    } else
#endif
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; i += 4) {
        const uint32_t word = pixels[i] | ((uint32_t)pixels[i + 1] << 8) |
            ((uint32_t)pixels[i + 2] << 16) | ((uint32_t)pixels[i + 3] << 24);
        hash = (hash ^ word) * 16777619u;
    }
    for (unsigned i = 0; i < 16; ++i) hash = (hash ^ palette[i]) * 16777619u;
    return hash;
}

#ifdef __cplusplus
extern "C" {
#endif
/* scratch has room for two AW_STORM_BLOCK buffers. base is the first free
 * offset after the two LCD snapshots in the app's PSRAM reservation. */
bool aw_storm_load(aw_display_storm *s, aw_assets *assets, uint32_t base,
                   uint8_t *scratch, uint32_t bytes, aw_storm_read_fn read, void *ctx);
/* Warm only the hidden page. False leaves the ordinary renderer available.
 * Any destination written by the cache has its old snapshot invalidated. */
bool aw_storm_warm(aw_display_storm *s, aw_display_pages *p, unsigned index,
                   const uint8_t *pixels, const uint16_t *palette,
                   aw_display_page_fn select, aw_display_rect_fn draw, void *ctx);
/* At most one rectangle per service call, on the hidden page only. */
void aw_storm_pump(aw_display_storm *s, aw_display_pages *p, const aw_storm_output *lcd, void *ctx);
bool aw_storm_present(aw_display_storm *s, aw_display_pages *p, unsigned index,
                      const uint8_t *pixels, const uint16_t *palette,
                      const aw_storm_output *lcd, void *ctx);
/* Present one intro frame through the cache or the ordinary two-page renderer. */
bool aw_storm_present_intro(aw_display_storm *s, aw_display_pages *p, const uint8_t *pixels,
                            const uint16_t *palette, const uint32_t *identities,
                            const aw_storm_output *lcd, aw_storm_normal_fn normal, void *ctx);
#ifdef __cplusplus
}
#endif
#endif
