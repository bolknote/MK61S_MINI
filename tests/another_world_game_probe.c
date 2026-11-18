/* Headless integration probe for user-supplied DOS resources. */
#include "../examples/portable-apps/ANOTHER/audio.h"
#include "../sdk/coproc/stm3_module.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef AW_DISPLAY_ANALYZE
#include "../examples/portable-apps/ANOTHER/display.h"
#include <assert.h>
#ifdef AW_COMPACT_DISPLAY
#include "../examples/portable-apps/ANOTHER/display_compact.h"
#ifdef AW_TWO_PAGE_ANALYZE
#include "../examples/portable-apps/ANOTHER/display_pages.h"
static aw_display_pages pages;
static uint16_t page_pixels[2][AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT];
static unsigned page_selected=2, page_visible=2, page_shows;
#include "../examples/portable-apps/ANOTHER/display_storm.h"
#ifdef AW_TEST_STORM
static aw_display_storm storm;
static unsigned replayed, intro_frames, anchor_calls, blocking_wire;
static unsigned worker_busy, busy_polls;
static unsigned idle_returns, tail_replayed;
static unsigned deferred_latches, visible_overlaps, draw_lead, last_window_lead, wire_before_last;
static uint32_t lcd_time;
static uint64_t wire_at_flash, wire_at_return;
static bool normal_used, tight_psram, base_prelude_only, return_mismatch, limited_tail, incomplete_black;
static bool overlap;
static unsigned tail_mismatch;
static bool storm_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    FILE *file = ctx;
    return fseek(file, (long)offset, SEEK_SET) == 0 && fread(out, 1, size, file) == size;
}
static bool storm_wait(void *ctx, unsigned lead_ms) {
    (void)ctx;
    if (lead_ms && !draw_lead) draw_lead = lead_ms;
    else if (lead_ms) { last_window_lead = lead_ms; wire_before_last = blocking_wire; }
    return true;
}
#endif
#endif
static aw_display_compact compact;
static uint8_t compact_previous[12800];
#ifndef AW_TWO_PAGE_ANALYZE
static uint64_t fallback_frames[10];
#endif
#else
static aw_display display;
static uint8_t display_previous[AW_VIDEO_PAGE_BYTES];
#endif
#define SCREEN_MARGIN 60u
static uint16_t displayed_pixels[AW_VIDEO_WIDTH * (AW_VIDEO_HEIGHT + 2 * SCREEN_MARGIN)];
static uint64_t display_bytes[10], display_rects[10], display_frames[10];
#ifdef AW_TILE_ANALYZE
static uint64_t two_color_frames[10], two_color_tiles[10], total_tiles[10];
#endif
static unsigned display_part;
static bool display_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                         const uint8_t *pixels, const uint16_t *palette, bool clear) {
    (void)ctx; (void)clear;
    assert(!(x & 1) && !(width & 1) && x + width <= AW_VIDEO_WIDTH && y + height <= AW_VIDEO_HEIGHT);
    display_bytes[display_part] += width * height * 2; ++display_rects[display_part];
    for (unsigned row = 0; row < height; ++row) for (unsigned col = 0; col < width; ++col) {
        const uint8_t b = pixels[row * (width / 2) + col / 2];
        const unsigned at=(y + row) * AW_VIDEO_WIDTH + x + col;
        const uint16_t color=palette[(b >> ((col & 1) ? 0 : 4)) & 15];
#ifdef AW_TWO_PAGE_ANALYZE
        assert(page_selected<2);page_pixels[page_selected][at]=color;
        if(page_visible==page_selected) displayed_pixels[SCREEN_MARGIN*AW_VIDEO_WIDTH+at]=color;
#else
        displayed_pixels[SCREEN_MARGIN*AW_VIDEO_WIDTH+at]=color;
#endif
    }
    return true;
}
#ifdef AW_TWO_PAGE_ANALYZE
static bool display_select_page(void *ctx,unsigned page) { (void)ctx;assert(page<2);page_selected=page;return true; }
static bool display_show_page(void *ctx,unsigned page) {
    (void)ctx;assert(page==page_selected);page_visible=page;++page_shows;
    memcpy(displayed_pixels+SCREEN_MARGIN*AW_VIDEO_WIDTH,page_pixels[page],sizeof(page_pixels[page]));return true;
}
#ifdef AW_TEST_STORM
static bool storm_blocking_select(void *ctx, unsigned page) {
    worker_busy = 0;
    return display_select_page(ctx, page);
}
static bool storm_blocking_show(void *ctx, unsigned page) {
    while (worker_busy) {
        --worker_busy;
        if (!aw_display_pages_write_one(&pages)) return false;
    }
    const unsigned flash = storm.first - AW_STORM_FIRST_PRELOAD_LEAD;
    if (intro_frames == flash + 1) wire_at_flash = display_bytes[display_part];
    if (intro_frames == flash + 2) wire_at_return = display_bytes[display_part];
    return display_show_page(ctx, page);
}
static bool storm_blocking_draw(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                                const uint8_t *pixels, const uint16_t *palette, bool clear) {
    while (worker_busy) {
        --worker_busy;
        if (!aw_display_pages_write_one(&pages)) return false;
    }
    blocking_wire += width * height * 2;
    worker_busy = 2;
    return display_rect(ctx, x, y, width, height, pixels, palette, clear);
}
static unsigned storm_select(void *ctx, unsigned page) {
    if (worker_busy) { --worker_busy; ++busy_polls; return 2; }
    return display_select_page(ctx, page);
}
static unsigned storm_draw(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                           const uint8_t *pixels, const uint16_t *palette, bool clear) {
    if (worker_busy) { --worker_busy; ++busy_polls; return 2; }
    assert(page_selected != page_visible);
    worker_busy = 2;
    return display_rect(ctx, x, y, width, height, pixels, palette, clear);
}
static uint32_t storm_deadline(void *ctx) { (void)ctx; return intro_frames; }
static unsigned storm_latch_at(void *ctx, unsigned page, uint32_t deadline, bool block) {
    if (!block && lcd_time < deadline) return 2;
    if (!block && worker_busy) { --worker_busy; ++busy_polls; return 2; }
    return storm_blocking_show(ctx, page);
}
static const aw_storm_output storm_lcd = {
    storm_blocking_select, storm_blocking_show, storm_blocking_draw, storm_wait, storm_select, storm_draw, 24000000,
    storm_deadline, storm_latch_at
};
static bool storm_normal(void *ctx, const uint8_t *pixels, const uint16_t *palette,
                          const uint32_t *identities, unsigned lead) {
    normal_used = true;
    if (lead) {
        assert(lead == AW_STORM_ANCHOR_LEAD_MS && intro_frames == storm.first + AW_STORM_WARM_FRAMES);
        ++anchor_calls;
    }
    return aw_display_pages_present(&pages, pixels, palette, identities, storm_blocking_select, storm_blocking_show,
                                    storm_blocking_draw, NULL, ctx) &&
        (!lead || storm_blocking_select(ctx, pages.visible));
}
#endif
#endif
#endif

typedef struct {
    const char *path;
    uint8_t *store;
    uint32_t capacity, frames, checksum, music_events, sound_events, nonzero_samples, sample_count, peak_packet;
    uint64_t source_bytes, packet_bytes;
#ifdef AW_DISPLAY_ANALYZE
    uint64_t store_reads, store_read_bytes, store_writes, store_write_bytes;
#endif
#if defined(AW_TWO_PAGE_ANALYZE) && !defined(AW_TEST_STORM)
    uint32_t backdrop_store, backdrop_read_bytes;
#endif
    aw_audio *audio, *remote;
} host;
uint32_t module_entry(uint32_t, const stm3_api *, stm3_job *);
static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    host *h = ctx; char path[1024];
    if (snprintf(path, sizeof(path), "%s/BANK%02X", h->path, bank) >= (int)sizeof(path)) return false;
    FILE *f = fopen(path, "rb"); if (!f) return false;
    const bool ok = fseek(f, offset, SEEK_SET) == 0 && fread(out, 1, size, f) == size;
    fclose(f); return ok;
}
static bool store_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    host *h = ctx;
    if (offset > h->capacity || size > h->capacity - offset) return false;
#ifdef AW_DISPLAY_ANALYZE
    ++h->store_reads; h->store_read_bytes += size;
#endif
#if defined(AW_TWO_PAGE_ANALYZE) && !defined(AW_TEST_STORM)
    if (h->backdrop_store && offset >= h->backdrop_store && offset - h->backdrop_store < AW_VIDEO_PAGE_BYTES)
        h->backdrop_read_bytes += size;
#endif
    memcpy(out, h->store + offset, size); return true;
}
static bool store_write(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    host *h = ctx;
    if (offset > h->capacity || size > h->capacity - offset) return false;
#ifdef AW_DISPLAY_ANALYZE
    ++h->store_writes; h->store_write_bytes += size;
#endif
    memcpy(h->store + offset, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    host *h = ctx; uint32_t checksum = 2166136261u;
#ifdef AW_DISPLAY_ANALYZE
    if (!h->frames) {
#ifdef AW_COMPACT_DISPLAY
        assert(aw_display_compact_init(&compact, h->audio->assets,
               h->audio->assets->used + 4 * AW_VIDEO_PAGE_BYTES,
               compact_previous, sizeof(compact_previous), compact_previous, sizeof(compact_previous)));
#ifdef AW_TWO_PAGE_ANALYZE
        const uint32_t second=h->audio->assets->used + 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES;
        assert(aw_display_pages_init(&pages,&compact,second));
#ifdef AW_TEST_STORM
        FILE *file = fopen(getenv("AW_STORM_CACHE"), "rb");
        char magic[4];
        assert(file && fread(magic, 1, sizeof(magic), file) == sizeof(magic) && fseek(file, 0, SEEK_END) == 0);
        const long size = ftell(file);
        assert(size > 0 && size <= AW_STORM_MAX_FILE &&
               aw_storm_load(&storm, h->audio->assets, second + AW_VIDEO_PAGE_BYTES,
                             compact.scratch, (uint32_t)size, storm_read, file));
        assert(storm.prelude.available == (!tight_psram && magic[3] >= '3'));
        assert(storm.prelude.idle_return.available == (magic[3] >= '4' && !tight_psram && !base_prelude_only));
        assert(storm.tail.available == (magic[3] == '5' && !tight_psram && !base_prelude_only && !limited_tail));
        storm.tail.overlap = overlap && storm.tail.available;
        if (return_mismatch) storm.prelude.idle_return.hash ^= 1u;
        if (tail_mismatch == 1) storm.tail.frames[1].hash ^= 1u;
        if (tail_mismatch == 2) storm.tail.black_hash ^= 1u;
        fclose(file);
#endif
#endif
#else
        aw_display_init(&display, display_previous);
#endif
    }
    display_part = h->audio->vm->part - AW_VM_FIRST_PART;
    assert(display_part < 10);
#if defined(AW_TWO_PAGE_ANALYZE) || defined(AW_FRAME_METRICS)
    const uint64_t before_rgb = display_bytes[display_part];
    const uint64_t before_reads = h->store_read_bytes, before_writes = h->store_write_bytes;
#endif
#ifdef AW_TWO_PAGE_ANALYZE
    const unsigned before_shows = page_shows;
#endif
#ifdef AW_TILE_ANALYZE
    unsigned eligible = 0;
    for (unsigned y = 0; y < AW_VIDEO_HEIGHT; y += 8)
        for (unsigned x = 0; x < AW_VIDEO_STRIDE; x += 4) {
            uint32_t colors = 0;
            for (unsigned row = 0; row < 8; ++row)
                for (unsigned col = 0; col < 4; ++col) {
                    const uint8_t pair = pixels[(y + row) * AW_VIDEO_STRIDE + x + col];
                    colors |= (1u << (pair >> 4)) | (1u << (pair & 15));
                }
            if (__builtin_popcount(colors) <= 2) ++eligible;
        }
    const unsigned tiles = (AW_VIDEO_WIDTH / 8) * (AW_VIDEO_HEIGHT / 8);
    two_color_frames[display_part] += eligible == tiles;
    two_color_tiles[display_part] += eligible;
    total_tiles[display_part] += tiles;
#endif
#ifdef AW_COMPACT_DISPLAY
#ifdef AW_TWO_PAGE_ANALYZE
    const uint32_t *identities = aw_video_band_identities(h->audio->vm->video);
#ifdef AW_TEST_STORM
    const unsigned intro_frame = h->audio->vm->part == AW_STORM_PART ? intro_frames++ : UINT32_MAX;
    const unsigned clip_start = storm.first + AW_STORM_WARM_FRAMES;
    const unsigned tail_start = clip_start + AW_STORM_FRAMES;
    const unsigned before_page = pages.visible;
    lcd_time = intro_frame;
    blocking_wire = draw_lead = last_window_lead = wire_before_last = 0;
    normal_used = false;
    if (intro_frame != UINT32_MAX && storm.ready) {
        assert(aw_storm_present_intro(&storm, &pages, pixels, palette, identities, &storm_lcd, storm_normal, NULL));
        if (intro_frame >= clip_start && intro_frame < tail_start && !normal_used) ++replayed;
        if (storm.prelude.available) {
            if (intro_frame == storm.first - AW_STORM_FIRST_PRELOAD_LEAD || intro_frame == storm.first - 1u)
                assert(normal_used && blocking_wire == 0 && page_shows == before_shows + 1);
            if (intro_frame == storm.first + 1u)
                assert(!normal_used && blocking_wire == 5984 && storm.pending == 0);
            if (intro_frame == storm.first - AW_STORM_FIRST_PRELOAD_LEAD + 1u) {
                if (storm.prelude.idle_return.available && !return_mismatch) {
                    assert(!normal_used && page_shows == before_shows + 1);
                    assert(wire_at_return - wire_at_flash == 62836);
                    ++idle_returns;
                } else {
                    assert(normal_used);
                }
            }
        }
    } else {
        assert(storm_normal(NULL, pixels, palette, identities, 0));
    }
    if (storm.tail.latch_pending) {
        assert(overlap && intro_frame + 1 == tail_start && pages.visible == before_page && page_shows == before_shows);
        assert(storm.tail.latch_deadline == intro_frames && lcd_time < storm.tail.latch_deadline);
        aw_storm_pump(&storm, &pages, &storm_lcd, NULL);
        assert(storm.tail.latch_pending && page_shows == before_shows);
        lcd_time = storm.tail.latch_deadline;
        for (unsigned i = 0; i < 3 && storm.tail.latch_pending; ++i)
            aw_storm_pump(&storm, &pages, &storm_lcd, NULL);
        assert(!storm.tail.latch_pending && pages.visible == storm.tail.visible && page_shows == before_shows + 1);
        ++deferred_latches;
    }
    if (storm.tail.visible_pending) {
        const uint64_t visible_end = display_bytes[display_part];
        assert(overlap && worker_busy && pages.selected == pages.visible);
        aw_storm_pump(&storm, &pages, &storm_lcd, NULL);
        assert(storm.tail.visible_pending && display_bytes[display_part] == visible_end && pages.selected == pages.visible);
        ++visible_overlaps;
    }
    if (intro_frame >= tail_start && intro_frame <= tail_start + AW_STORM_TAIL_FRAMES) {
        static const unsigned wire[] = {45856, 57440, 48908, 0};
        const unsigned index = intro_frame - tail_start;
        const bool expected = storm.tail.available && (tail_mismatch != 1 || index == 0) &&
                              (tail_mismatch != 2 || index < AW_STORM_TAIL_FRAMES);
        assert(normal_used != expected);
        if (expected) {
            if (index == AW_STORM_TAIL_FRAMES) {
                assert(page_shows == before_shows + 1);
                if (incomplete_black)
                    assert(storm.tail.black_rows < AW_VIDEO_HEIGHT &&
                           blocking_wire == (AW_VIDEO_HEIGHT - storm.tail.black_rows) * AW_VIDEO_WIDTH * 2u);
                else
                    assert(storm.tail.black_rows == AW_VIDEO_HEIGHT && blocking_wire == 0);
            } else {
                assert(blocking_wire == wire[index]);
                if (overlap) {
                    static const unsigned expected_lead[] = {28, 31, 25};
                    static const unsigned final_lead[] = {7, 6, 8};
                    static const unsigned final_bytes[] = {15008, 12800, 20224};
                    assert(draw_lead == expected_lead[index]);
                    assert(last_window_lead == final_lead[index] && wire_before_last == wire[index] - final_bytes[index]);
                }
            }
            ++tail_replayed;
        }
    }
#else
    assert(aw_display_pages_present(&pages, pixels, palette, identities, display_select_page,
                                    display_show_page, display_rect, NULL, NULL));
#endif
#else
    assert(aw_display_compact_present(&compact, pixels, palette, display_rect, NULL));
#endif
#ifndef AW_TWO_PAGE_ANALYZE
    fallback_frames[display_part] += compact.external;
#endif
#else
    assert(aw_display_present(&display, pixels, palette, display_rect, NULL));
#endif
    ++display_frames[display_part];
    for (unsigned i = 0; i < AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT; ++i) {
        const uint8_t b = pixels[i / 2];
        assert(displayed_pixels[SCREEN_MARGIN*AW_VIDEO_WIDTH+i] == palette[(b >> ((i & 1) ? 0 : 4)) & 15]);
    }
    for (unsigned i = 0; i < SCREEN_MARGIN * AW_VIDEO_WIDTH; ++i) {
        assert(displayed_pixels[i] == 0);
        assert(displayed_pixels[(SCREEN_MARGIN + AW_VIDEO_HEIGHT)*AW_VIDEO_WIDTH+i] == 0);
    }
#ifdef AW_TWO_PAGE_ANALYZE
    /* Once the first white and black frames exist, the actual intro reuses
     * those two RGB pages. Border pixels must remain black on every flash. */
#ifdef AW_TEST_STORM
    const unsigned frame = intro_frame;
#else
    const unsigned frame = h->frames;
#endif
    if (h->audio->vm->part == 0x3e81 && frame >= 2443 && frame <= 2450) {
        assert(display_bytes[display_part] == before_rgb);
        assert(h->store_read_bytes == before_reads && h->store_write_bytes == before_writes);
        assert(page_shows == before_shows + 1);
    }
#endif
#ifdef AW_FRAME_METRICS
    if (h->audio->vm->part == 0x3e81 && h->frames >= 2418 && h->frames <= 2454)
        printf("FRAME %u RGB=%llu PSRAM_R=%llu PSRAM_W=%llu\n", h->frames,
               (unsigned long long)(display_bytes[display_part]-before_rgb),
               (unsigned long long)(h->store_read_bytes-before_reads),
               (unsigned long long)(h->store_write_bytes-before_writes));
#endif
#endif
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) checksum = (checksum ^ pixels[i]) * 16777619u;
    for (unsigned i = 0; i < 16; ++i) checksum = (checksum ^ palette[i]) * 16777619u;
    h->checksum = checksum; ++h->frames; return true;
}
static bool frame_wait(void *ctx, unsigned slices) {
    host *h = ctx; int16_t samples[64]; uint8_t packet[512], output[72];
    unsigned remaining = slices * 500;
    while (remaining) {
#ifdef AW_TEST_STORM
        if (h->audio->vm->part == AW_STORM_PART &&
            !(incomplete_black && storm.tail.active && storm.tail.row_limit == AW_VIDEO_HEIGHT))
            aw_storm_pump(&storm, &pages, &storm_lcd, NULL);
#endif
        unsigned n = remaining < 64 ? remaining : 64, frames, bytes;
        if (!aw_audio_prepare_m3(h->remote, packet, sizeof(packet), n, 1000, 0, &frames, &bytes) ||
            !aw_audio_render(h->audio, samples, frames)) return false;
        stm3_job job = {packet, bytes, output, sizeof(output), 0, 0};
        uint32_t result = module_entry(STM3_INIT, NULL, &job);
        while (result == STM3_MORE) result = module_entry(STM3_STEP, NULL, &job);
        if (result != STM3_DONE || job.output_bytes != frames + 8) return false;
        for (unsigned i = 0; i < frames; ++i) {
            if (samples[i]) ++h->nonzero_samples;
            if (output[8+i] != 128 + samples[i] / 512) return false;
        }
        for (unsigned ch = 0; ch < 4; ++ch)
            if (h->audio->channels[ch].active != h->remote->channels[ch].active ||
                h->audio->channels[ch].position != h->remote->channels[ch].position) return false;
        h->source_bytes += bytes - 44; h->packet_bytes += bytes + frames + 62;
        h->sample_count += frames; if (bytes > h->peak_packet) h->peak_packet = bytes;
        remaining -= frames;
    }
    return true;
}
static void sound(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel) {
    host *h = ctx; ++h->sound_events; aw_audio_sound(h->audio, id, freq, volume, channel);
    aw_audio_sound(h->remote, id, freq, volume, channel);
}
static void music(void *ctx, unsigned id, unsigned delay, unsigned pos) {
    host *h = ctx; ++h->music_events; aw_audio_music(h->audio, id, delay, pos);
    aw_audio_music(h->remote, id, delay, pos);
}
static void stop_audio(void *ctx) { host *h = ctx; aw_audio_stop(h->audio); aw_audio_stop(h->remote); }
#if defined(AW_TWO_PAGE_ANALYZE) && !defined(AW_TEST_STORM)
/* Replay the DOS route from the pool, modelling the bounded background
 * writes between displays independently of the host wall clock. */
typedef struct {
    host io;
    aw_video video;
    aw_vm vm;
    unsigned slices, previous_scroll, checked;
    unsigned strips_to_prepare;
    uint64_t previous_reads, previous_writes, pool_start_io;
    uint64_t route_hash;
} cut_probe;

static bool cut_wait(void *ctx, unsigned slices) {
    ((cut_probe *)ctx)->slices = slices;
    return true;
}
static bool cut_present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    cut_probe *p = ctx;
    const unsigned scroll = p->video.page_scroll[p->video.front_page];
    const unsigned shift = (p->previous_scroll + AW_VIDEO_HEIGHT - scroll) % AW_VIDEO_HEIGHT;
    p->previous_scroll = scroll;
    page_selected = page_visible = 0;
    if (shift) {
        for (unsigned y = 0; y < AW_VIDEO_HEIGHT; ++y)
            memcpy(page_pixels[1] + y * AW_VIDEO_WIDTH,
                   page_pixels[0] + (y + shift) % AW_VIDEO_HEIGHT * AW_VIDEO_WIDTH, AW_VIDEO_WIDTH * sizeof(uint16_t));
        memcpy(page_pixels[0], page_pixels[1], sizeof(page_pixels[0]));
    }
    const uint64_t wire_before = display_bytes[display_part];
    assert(aw_display_compact_present_tracked(&compact, pixels, palette, shift,
                                               aw_video_band_identities(&p->video), display_rect, NULL));
    for (unsigned i = 0; i < AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT; ++i)
        assert(page_pixels[0][i] == palette[(pixels[i / 2] >> ((i & 1) ? 0 : 4)) & 15]);
    const uint32_t frame_hash = aw_storm_frame_hash(pixels, palette);
    p->route_hash = (p->route_hash ^ frame_hash) * UINT64_C(1099511628211);
    if (p->io.frames >= 6 && p->io.frames <= 68) assert(p->slices == 4);
    /* Evicting the background between alternating display pages costs
     * over 5,000 PSRAM transactions during these twenty pool frames. */
    if (p->io.frames == 5) p->pool_start_io = p->io.store_reads + p->io.store_writes;
    if (p->io.frames == 25) assert(p->io.store_reads + p->io.store_writes - p->pool_start_io <= 800);
    if (p->io.frames >= 5 && p->io.frames <= 7) {
        static const uint32_t hashes[] = {0x8F7FC229u, 0xD3E992A3u, 0xA3437B92u};
        static const unsigned payloads[] = {0, 128000, 45968};
        const unsigned i = p->io.frames - 5;
        assert(p->slices == 4 && frame_hash == hashes[i]);
        assert(display_bytes[display_part] - wire_before == payloads[i]);
    }
    /* Foreground PSRAM budgets under the eight idle polls below. Physical
     * frame deadlines are measured independently on the device. */
    static const struct { unsigned frame, slices; uint32_t hash, reads, writes; } cuts[] = {
        {168, 3, 0x8D80D9F8u, 60 * 1024,  4 * 1024},
        {169, 3, 0x222F7F27u,  4 * 1024, 16 * 1024},
        {170, 3, 0x1A322527u,  2 * 1024,  2 * 1024},
        {222, 4, 0xBA6ADCE8u, 18 * 1024, AW_VIDEO_PAGE_BYTES},
        {223, 4, 0x4D86D570u, 18 * 1024, 28 * 1024}
    };
    if (p->io.frames == 64) {
        assert(frame_hash == 0xF627725Bu && display_bytes[display_part] - wire_before == 128000);
        assert(p->vm.backdrop_rows == p->strips_to_prepare * AW_BACKDROP_ROWS);
        assert(p->io.backdrop_read_bytes == (p->vm.backdrop_rows == AW_VIDEO_HEIGHT ? AW_VIDEO_PAGE_BYTES : 0));
        if (p->vm.backdrop_rows == AW_VIDEO_HEIGHT)
            assert(p->io.store_write_bytes - p->previous_writes <= AW_VIDEO_PAGE_BYTES);
    }
    if (p->checked < sizeof(cuts) / sizeof(cuts[0]) && p->io.frames == cuts[p->checked].frame) {
        assert(p->slices == cuts[p->checked].slices);
        assert(frame_hash == cuts[p->checked].hash);
        const uint64_t reads = p->io.store_read_bytes - p->previous_reads;
        const uint64_t writes = p->io.store_write_bytes - p->previous_writes;
        assert(reads <= cuts[p->checked].reads && writes <= cuts[p->checked].writes);
        ++p->checked;
    }
    /* Model one idle window per strip. A second run only finishes half
     * the backdrop before the cut and must still show the same pixels. */
    if (p->io.frames >= 26 && p->io.frames - 26 < p->strips_to_prepare) {
        uint8_t scratch[AW_BACKDROP_ROWS * AW_VIDEO_STRIDE + 2];
        scratch[0] = scratch[sizeof(scratch) - 1] = 0xa5;
        const unsigned top = p->vm.backdrop_rows;
        const uint64_t before = p->io.store_write_bytes;
        aw_vm_prepare_backdrop(&p->vm, p->io.backdrop_store, scratch + 1);
        assert(p->vm.backdrop_rows == top + AW_BACKDROP_ROWS);
        assert(p->io.store_write_bytes - before == AW_BACKDROP_ROWS * AW_VIDEO_STRIDE);
        assert(scratch[0] == 0xa5 && scratch[sizeof(scratch) - 1] == 0xa5);
    }
    for (unsigned poll = 0; poll < 8; ++poll) {
        const uint64_t before = p->io.store_write_bytes;
        assert(aw_video_write_one(&p->video));
        assert(p->io.store_write_bytes - before <= 2 * AW_VIDEO_BAND_ROWS * AW_VIDEO_STRIDE);
    }
    p->previous_reads = p->io.store_read_bytes;
    p->previous_writes = p->io.store_write_bytes;
    ++p->io.frames;
    return true;
}
static void camera_cut(const char *path, unsigned strips_to_prepare) {
    cut_probe p = {
        .io = {.path = path, .capacity = 2 * 1024 * 1024},
        .route_hash = UINT64_C(14695981039346656037),
        .strips_to_prepare = strips_to_prepare
    };
    p.io.store = calloc(1, p.io.capacity);
    uint8_t pixels[AW_VIDEO_PAGE_BYTES], spare[AW_VIDEO_PAGE_BYTES], list[4096];
    char name[1024];
    assert(snprintf(name, sizeof(name), "%s/MEMLIST.BIN", path) < (int)sizeof(name));
    FILE *file = fopen(name, "rb");
    assert(file);
    const size_t bytes = fread(list, 1, sizeof(list), file);
    assert(bytes && !ferror(file));
    fclose(file);
    aw_assets a;
    aw_asset_entry entries[AW_ASSET_LIMIT];
    assert(p.io.store && aw_assets_init(&a, entries, list, bytes, p.io.capacity, &p.io, bank_read, store_read, store_write));
    assert(aw_video_init(&p.video, &a, a.used, pixels, cut_present, &p));
    p.io.backdrop_store = a.used + 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES;
    assert(aw_video_use_spare(&p.video, spare));
    aw_video_bands bands;
    aw_video_track_bands(&p.video, &bands);
    assert(aw_display_compact_init(&compact, &a, a.used + 4 * AW_VIDEO_PAGE_BYTES,
                                   compact_previous, sizeof(compact_previous), compact_previous, sizeof(compact_previous)));
    assert(aw_vm_init(&p.vm, &a, &p.video, (aw_vm_host){.ctx = &p, .frame_wait = cut_wait}, 1));
    p.vm.vars[0xBC] = 0x10; p.vm.vars[0xC6] = 0x80; p.vm.vars[0xF2] = 4000; p.vm.vars[0xDC] = 33;
    assert(aw_vm_set_part(&p.vm, AW_VM_FIRST_PART + 2));
    for (unsigned step = 0; step < 1800; ++step) {
        aw_input input = {.directions = step < 90 ? AW_INPUT_UP : AW_INPUT_RIGHT, .button = step >= 90};
        if (step >= 120 && step % 55 < 18) input.directions |= AW_INPUT_UP;
        assert(aw_vm_frame(&p.vm, &input));
    }
    /* Fingerprint of the independently recorded 1802 indexed frames and palettes. */
    assert(p.io.frames == 1802 && p.route_hash == UINT64_C(0xDEBE2AC625BAA207) && p.checked == 5);
    free(p.io.store);
}
#endif

int main(int argc, char **argv) {
#if defined(AW_TWO_PAGE_ANALYZE) && !defined(AW_TEST_STORM)
    if (argc == 3 && !strcmp(argv[2], "camera-cut")) {
        const unsigned strips = AW_VIDEO_HEIGHT / AW_BACKDROP_ROWS;
        camera_cut(argv[1], strips);
        camera_cut(argv[1], strips / 2);
        puts("DOS pool route and camera cuts verified across 1802 frames with complete and partial scenery");
        return 0;
    }
#endif
    aw_asset_entry entries[AW_ASSET_LIMIT];
    if (argc < 2 || argc > 3) { fprintf(stderr, "usage: %s DATA_DIR [WALK_STEPS]\n", argv[0]); return 2; }
    const unsigned limit = argc == 3 ? (unsigned)strtoul(argv[2], NULL, 10) : 5000;
    if (!limit || limit > 100000) return 2;
    char path[1024]; snprintf(path, sizeof(path), "%s/MEMLIST.BIN", argv[1]);
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); return 1; }
    uint8_t list[4096]; size_t len = fread(list, 1, sizeof(list), f); fclose(f);
    host h = {0}; h.path = argv[1]; h.capacity = 2u * 1024u * 1024u;
#ifdef AW_TEST_STORM
    tight_psram = getenv("AW_STORM_TIGHT_PSRAM") != NULL;
    base_prelude_only = getenv("AW_STORM_BASE_PRELUDE") != NULL;
    return_mismatch = getenv("AW_STORM_RETURN_MISMATCH") != NULL;
    limited_tail = getenv("AW_STORM_LIMITED_TAIL") != NULL;
    incomplete_black = getenv("AW_STORM_INCOMPLETE_BLACK") != NULL;
    overlap = getenv("AW_STORM_OVERLAP") != NULL;
    const char *mismatch = getenv("AW_STORM_TAIL_MISMATCH");
    if (mismatch) {
        assert(!strcmp(mismatch, "visible") || !strcmp(mismatch, "black"));
        tail_mismatch = !strcmp(mismatch, "visible") ? 1 : 2;
    }
    if (!tight_psram) {
        h.capacity += AW_VIDEO_PAGE_BYTES;
        if (!base_prelude_only) {
            h.capacity += AW_STORM_IDLE_RETURN_RESERVE;
            if (!limited_tail) h.capacity += AW_STORM_TAIL_RESERVE;
        }
    }
#endif
    h.store = calloc(1, h.capacity);
    uint8_t *pixels = malloc(AW_VIDEO_PAGE_BYTES), *spare = NULL, *background = NULL; aw_assets *a = calloc(1, sizeof(*a));
#ifdef AW_COMPACT_DISPLAY
    spare = malloc(AW_VIDEO_PAGE_BYTES);
    if (!spare) return 1;
#endif
#ifdef AW_VIDEO_BACKGROUND
    background = malloc(6144);
    if (!background) return 1;
#endif
    aw_video *video = calloc(1, sizeof(*video)); aw_vm *vm = calloc(1, sizeof(*vm));
    h.audio = calloc(1, sizeof(*h.audio)); h.remote = calloc(1, sizeof(*h.remote));
    aw_vm_host callbacks = {&h, frame_wait, NULL, sound, music, stop_audio};
    if (!h.store || !pixels || !a || !video || !vm || !h.audio || !h.remote ||
        !aw_assets_init(a, entries, list, len, h.capacity, &h, bank_read, store_read, store_write) ||
        !aw_video_init(video, a, a->used, pixels, present, &h) ||
        (spare && !aw_video_use_spare(video, spare)) ||
        (background && !aw_video_use_background(video, background, 6144)) ||
#ifdef AW_VIDEO_PACKED3
        !aw_video_use_packed_page3(video, a->used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES) ||
#endif
        !aw_vm_init(vm, a, video, callbacks, 1)) {
        fprintf(stderr, "initialization failed\n"); return 1;
    }
#ifdef AW_TWO_PAGE_ANALYZE
    aw_video_bands identities;
    aw_video_track_bands(video, &identities);
#endif
    aw_audio_init(h.audio, a, vm); aw_audio_init(h.remote, a, vm);
    /* The probe starts after the protection part; seed the same variables
     * that Raw's BYPASS_PROTECTION test build initializes. */
#ifndef AW_TEST_STORM
    vm->vars[0xBC] = 0x10; vm->vars[0xC6] = 0x80; vm->vars[0xF2] = 4000; vm->vars[0xDC] = 33;
#endif
#ifdef AW_PROBE_FIRST_PART
    if (!aw_vm_set_part(vm, AW_VM_FIRST_PART)) { fprintf(stderr, "part load failed\n"); return 1; }
#else
    if (!aw_vm_set_part(vm, 0x3E81)) { fprintf(stderr, "part load failed\n"); return 1; }
#endif
    aw_input input = {0};
    unsigned iteration;
    for (iteration = 0; iteration < limit && (argc == 3 || vm->part == 0x3E81); ++iteration) {
        if (argc == 3 && vm->part >= 0x3E82) {
            const unsigned phase = iteration % 600;
            input.directions = phase < 260 ? AW_INPUT_RIGHT : phase < 400 ? AW_INPUT_LEFT : AW_INPUT_UP;
            input.button = phase % 90 < 15;
        }
        const unsigned previous_frames = h.frames;
        if (!aw_vm_frame(vm, &input)) {
            fprintf(stderr, "failed after %u iterations, display frames=%u, part=%04X cursor=%u video=%d assets=%d vm=%d\n",
                    iteration, h.frames, vm->part, vm->cursor, video->fault, a->fault, vm->fault);
            return 1;
        }
        if (argc == 3 && h.frames == previous_frames && !frame_wait(&h, 1)) return 1;
    }
    printf("iterations=%u frames=%u part=%04X last=%08X music=%u sounds=%u nonzero=%u source_Bps=%u transport_estimate_Bps=%u peak_packet=%u\n", iteration,
           h.frames, vm->part, h.checksum, h.music_events, h.sound_events, h.nonzero_samples,
           (unsigned)(h.source_bytes * 25000 / h.sample_count), (unsigned)(h.packet_bytes * 25000 / h.sample_count), h.peak_packet);
    if (argc == 3) {
        printf("vars: 00=%d 01=%d 02=%d E4=%d F4=%d F7=%d FF=%d next=%04X audio=%u\n",
               vm->vars[0], vm->vars[1], vm->vars[2], vm->vars[0xE4], vm->vars[0xF4],
               vm->vars[0xF7], vm->vars[0xFF], vm->next_part, h.audio->music_active);
        for (unsigned i = 0; i < AW_VM_THREADS; ++i) if (vm->pc[i] != 0xFFFF)
            printf("thread %u pc=%04X paused=%u requested=%04X\n", i, vm->pc[i], vm->paused[i], vm->requested_pc[i]);
    }
    const bool passed = h.frames > 10 && h.music_events && h.nonzero_samples &&
        (argc != 3 || limit < 3000 || (h.frames >= limit * 4 / 5 && vm->part >= 0x3E82));
#ifdef AW_DISPLAY_ANALYZE
    printf("storage reads=%llu bytes=%llu writes=%llu bytes=%llu\n",
           (unsigned long long)h.store_reads, (unsigned long long)h.store_read_bytes,
           (unsigned long long)h.store_writes, (unsigned long long)h.store_write_bytes);
    for (unsigned i = 0; i < 10; ++i) if (display_frames[i])
        printf("display part=%04X frames=%llu rectangles=%llu rgb_bytes=%llu full_bytes=%llu\n",
               AW_VM_FIRST_PART + i, (unsigned long long)display_frames[i],
               (unsigned long long)display_rects[i], (unsigned long long)display_bytes[i],
               (unsigned long long)(display_frames[i] * AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT * 2u));
#ifdef AW_TILE_ANALYZE
    for (unsigned i = 0; i < 10; ++i) if (display_frames[i])
        printf("two-color part=%04X complete_frames=%llu/%llu tiles=%llu/%llu\n", AW_VM_FIRST_PART + i,
               (unsigned long long)two_color_frames[i], (unsigned long long)display_frames[i],
               (unsigned long long)two_color_tiles[i], (unsigned long long)total_tiles[i]);
#endif
#ifdef AW_COMPACT_DISPLAY
#ifdef AW_TWO_PAGE_ANALYZE
    printf("page switches=%u\n",page_shows);
#ifdef AW_TEST_STORM
    assert(replayed == AW_STORM_FRAMES && storm.warmed == AW_STORM_WARM_FRAMES && !storm.ready);
    assert(anchor_calls == (unsigned)storm.prelude.available && busy_polls);
    assert(idle_returns == (unsigned)(storm.prelude.idle_return.available && !return_mismatch));
    assert(tail_replayed == (storm.tail.available
        ? (tail_mismatch == 1 ? 1u : tail_mismatch == 2 ? AW_STORM_TAIL_FRAMES : AW_STORM_TAIL_FRAMES + 1u)
        : 0u));
    if (overlap) {
        assert(deferred_latches == 1 && visible_overlaps == AW_STORM_TAIL_FRAMES);
        puts("DOS intro: deferred latch honored its deadline and DMA preceded hidden uploads");
    }
    if (tail_replayed == AW_STORM_TAIL_FRAMES + 1u && !incomplete_black)
        puts("DOS intro: frames 2439–2441 used 45856/57440/48908 LCD bytes; frame 2442 latched a preloaded page");
    if (idle_returns)
        puts("DOS intro: frame 2406 reused the hidden page with 62836 LCD bytes");
    if (storm.prelude.available)
        puts("DOS intro: both preloaded frames latched, restored the saved page with 5984 LCD bytes");
    puts("DOS intro: all warm steps and cached frames used, RGB565 matches each live frame");
#endif
#else
    for (unsigned i = 0; i < 10; ++i) if (display_frames[i])
        printf("compact part=%04X external_fallback_frames=%llu\n", AW_VM_FIRST_PART + i,
               (unsigned long long)fallback_frames[i]);
#endif
#endif
#endif
    free(h.remote); free(h.audio); free(vm); free(video); free(a); free(pixels); free(spare); free(background); free(h.store);
    return passed ? 0 : 1;
}
