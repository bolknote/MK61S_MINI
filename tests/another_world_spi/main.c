/* Diagnostic entry point for the PicoCalc storm measurements. */
#include "mk61_app.h"
#include "audio.h"
#include "display_compact.h"
#include "display_pages.h"
#include "display_storm.h"
#include "pacing.h"
#include "prepared.h"
#include <string.h>

#define EXTERNAL_BYTES (2u * 1024u * 1024u)
static const char storm_cache[] = "AWSTORM.BIN";
static const mk61_app_services *services;
static mk61_service_buffer external, screen, previous_frame, background_cache, background_tail;
#if defined(AW_CS_PHASE) || defined(AW_PAGE_WRITE)
static aw_assets *phase_assets;
#else
static aw_assets assets;
#endif
static aw_video *video;
static aw_display_compact *compact_display;
static aw_display_pages *pages_display;
static aw_display_storm *storm;
static aw_storm_output storm_lcd;
static aw_vm *vm;
static aw_audio *audio;
static aw_input input;
static uint8_t keys[32], previous[32];
static int16_t *pending;
static unsigned pending_at, pending_count;
static uint32_t next_keys, next_audio, last_frame;
static bool audio_open, pump_failed, compact_ready, pages_ready;
static void pump(void *ctx);

enum { TRACE_START = 2350, TRACE_FIRST = 2387, TRACE_LAST = 2453 };
#if defined(AW_CS_PHASE) || defined(AW_PAGE_WRITE)
static unsigned intro, spi, hz, audio_before, audio_after;
#elif !defined(AW_DMA_FEED)
static unsigned intro, spi, hz, payload, windows, audio_before, audio_after;
#else
static unsigned observing, intro, spi, hz, audio_before, audio_after;
#endif
static bool trace_done, tail_loaded;
static uint32_t cache_base;
static const char *startup_stage;
static uint32_t stage_deadline;
static bool startup_timeout;

static __attribute__((noinline)) void report(const char *format, ...) {
    char line[144];
    va_list args;
    va_start(args, format);
    const int n = services->format(line, sizeof(line), format, args);
    va_end(args);
    if (n > 0 && (unsigned)n < sizeof(line)) services->call(MK61_SERVICE_DEBUG_WRITE, (unsigned)n, 0, 0, line);
}

static uint32_t startup_now(void) {
#ifdef AW_TRACE_HOST
    extern uint32_t aw_host_startup_millis(void);
    return aw_host_startup_millis();
#else
    return mk61_api->millis_ms();
#endif
}

static void begin_stage(const char *stage, unsigned limit_ms) {
    startup_stage = stage;
    stage_deadline = startup_now() + limit_ms;
}
static bool startup_active(void) {
    if (startup_stage && (int32_t)(startup_now() - stage_deadline) >= 0) startup_timeout = pump_failed = true;
    return !startup_timeout && !input.quit;
}
#if defined(AW_CS_PHASE) || defined(AW_PAGE_WRITE)
static bool present_rect(void *, unsigned, unsigned, unsigned, unsigned, const uint8_t *, const uint16_t *, bool);
static bool page_select(void *, unsigned);
#ifdef AW_TRACE_HOST
extern uint32_t aw_phase_mock_us(void);
static uint32_t trace_time(void) { return aw_phase_mock_us(); }
#else
static uint32_t trace_time(void) { return *(volatile uint32_t *)0x40054028u; }
#endif
#ifdef AW_PAGE_WRITE
#include "writeback/meter.h"
#else
#include "phases/meter.h"
#endif
#elif !defined(AW_DMA_FEED)
static inline uint32_t trace_time(void) { return services->call(MK61_SERVICE_MICROS, 0, 0, 0, NULL); }
#include "wire.h"
static WirePoint *trace;
static WireBurst *bursts;
static const unsigned raw_frames[] = {2406, 2415, 2439, 2441};
static void print_burst(unsigned id, const WireBurst *b) {
    report("SCK W %u %u %u %08X %08X %08X %08X\n", id, b->bits, b->n, b->words[0], b->words[1], b->words[2],
           b->words[3]);
    report("SCK V %u %08X %08X %08X %08X\n", id, b->words[4], b->words[5], b->words[6], b->words[7]);
}
static void sample(unsigned frame) {
    if (frame < TRACE_FIRST || frame > TRACE_LAST + 1) return;
    WirePoint *p = trace + frame - TRACE_FIRST;
    wire_point(p);
    p->bytes = payload;
    p->rects = windows;
    for (unsigned k = 0; k < 4; ++k) {
        const unsigned bits = k == 1 ? 4 : 1;
        if (frame == raw_frames[k]) wire_arm(bits);
        if (frame == raw_frames[k] + 1) wire_collect(&bursts[k], bits);
    }
}
#else
#include "feed.h"
#endif
static uint32_t underruns(void) {
    mk61_service_audio status = {0};
    return services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_STATUS, 0, sizeof(status), &status)
               ? status.underruns
               : UINT32_MAX;
}

static bool acquire_direct(mk61_service_buffer *buffer, unsigned bytes) {
    if (mk61_app_buffer_acquire(services, bytes, MK61_BUFFER_DIRECT, buffer) && buffer->data) return true;
    if (buffer->handle) mk61_app_buffer_release(services, buffer->handle);
    *buffer = mk61_app_buffer_request();
    return false;
}
static bool acquire_frames(bool *paired) {
    if (acquire_direct(&screen, 2 * AW_VIDEO_PAGE_BYTES)) {
        *paired = true;
        previous_frame.data = screen.data + AW_VIDEO_PAGE_BYTES;
        return true;
    }
    if (!acquire_direct(&screen, AW_VIDEO_PAGE_BYTES)) return false;
    if (acquire_direct(&previous_frame, AW_VIDEO_PAGE_BYTES)) return true;
    mk61_app_buffer_release(services, screen.handle);
    screen = mk61_app_buffer_request();
    return false;
}
static void drop_background(void) {
    video->background = video->background_tail = NULL;
    video->background_valid = video->background_attempted = false;
    if (background_tail.handle) mk61_app_buffer_release(services, background_tail.handle);
    if (background_cache.handle) mk61_app_buffer_release(services, background_cache.handle);
    background_tail = background_cache = mk61_app_buffer_request();
}
static bool file_read(const char *path, uint32_t offset, void *out, uint32_t size) {
    mk61_service_file_bytes r = {path, out, offset, size};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(r), &r) != 0;
}
static uint32_t file_size(const char *name) {
    mk61_service_file_info info;
    mk61_service_file_bytes request = {name, &info, 0, sizeof(info)};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(request), &request) &&
                   !info.directory
               ? info.size
               : 0;
}
static bool read_storm(uint32_t at, void *out, uint32_t bytes) { return file_read(storm_cache, at, out, bytes); }
static bool acquire_external(void) {
    static const uint32_t reserve[] = {
        0,
        AW_VIDEO_PAGE_BYTES,
        AW_VIDEO_PAGE_BYTES + AW_STORM_IDLE_RETURN_RESERVE,
        AW_VIDEO_PAGE_BYTES + AW_STORM_IDLE_RETURN_RESERVE + AW_STORM_TAIL_RESERVE,
    };
    char magic[4];
    unsigned tier = 0;
    if (read_storm(0, magic, sizeof(magic)) && !memcmp(magic, "AWS", 3) && magic[3] >= '3' && magic[3] <= '5')
        tier = (unsigned)(magic[3] - '2');
    for (;;) {
        if (mk61_app_buffer_acquire(services, EXTERNAL_BYTES + reserve[tier], MK61_BUFFER_EXTERNAL, &external))
            return true;
        if (!tier) return false;
        --tier;
    }
}
static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    static const char hex[] = "0123456789ABCDEF";
    char path[] = "BANK00";
    path[4] = hex[bank >> 4];
    path[5] = hex[bank & 15];
    if (audio_open) pump(NULL);
    const bool ok = startup_active() && file_read(path, offset, out, size);
    if (audio_open)
        pump(NULL);
    else
        mk61_api->service();
    return ok && startup_active() && !pump_failed;
}
static bool prepared_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    return startup_active() && file_read("AWCACHE.BIN", offset, out, size) && startup_active();
}
static bool store_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    mk61_service_buffer r = mk61_app_buffer_request();
    r.handle = external.handle;
    r.offset = offset;
    r.data = out;
    r.size = size;
    return services->call(MK61_SERVICE_BUFFER, MK61_BUFFER_READ, 0, sizeof(r), &r) != 0;
}
static bool store_write(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    (void)ctx;
    mk61_service_buffer r = mk61_app_buffer_request();
    r.handle = external.handle;
    r.offset = offset;
    r.data = (uint8_t *)in;
    r.size = size;
    const bool ok = services->call(MK61_SERVICE_BUFFER, MK61_BUFFER_WRITE, 0, sizeof(r), &r) != 0;
#ifdef AW_PAGE_WRITE
    if (ok) wb_store(offset, size);
#endif
    return ok;
}
static bool pressed(const uint8_t *map, unsigned key) { return (map[key / 8] & (1u << (key & 7))) != 0; }
static bool letter(const uint8_t *map, unsigned c) { return pressed(map, c) || pressed(map, c - 32); }
static void poll_keys(void) {
    const uint32_t now = mk61_api->millis_ms();
    if ((int32_t)(now - next_keys) < 0) return;
    next_keys = now + 20;
    if (!services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(keys), 0, keys)) {
        pump_failed = true;
        return;
    }
    input.directions = 0;
    if (pressed(keys, 0xB4)) input.directions |= AW_INPUT_LEFT;
    if (pressed(keys, 0xB7)) input.directions |= AW_INPUT_RIGHT;
    if (pressed(keys, 0xB5)) input.directions |= AW_INPUT_UP;
    if (pressed(keys, 0xB6)) input.directions |= AW_INPUT_DOWN;
    input.button = pressed(keys, ' ') || pressed(keys, '\r') || pressed(keys, '\n');
    if ((pressed(keys, 0x1B) || pressed(keys, 0xB1) || pressed(keys, 0x90)) &&
        !(pressed(previous, 0x1B) || pressed(previous, 0xB1) || pressed(previous, 0x90)))
        input.quit = true;
    for (unsigned c = 'a'; c <= 'z'; ++c)
        if (letter(keys, c) && !letter(previous, c)) {
            if (c == 'c' && vm->part != AW_VM_LAST_PART)
                input.code = true;
            else
                input.last_char = (uint8_t)c;
            break;
        }
    if ((pressed(keys, 8) || pressed(keys, 127)) && !(pressed(previous, 8) || pressed(previous, 127)))
        input.last_char = 8;
    memcpy(previous, keys, sizeof(keys));
}
static void audio_pump(void) {
    if (!audio_open || pump_failed) return;
    const uint32_t now = mk61_api->millis_ms();
    if ((int32_t)(now - next_audio) < 0) return;
    next_audio = now + 2;
    mk61_service_audio r = {0};
    if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_STATUS, 0, sizeof(r), &r)) {
        pump_failed = true;
        return;
    }
    for (unsigned blocks = 0; blocks < 9 && r.queued < 1000; ++blocks) {
        if (pending_at == pending_count) {
            if (!aw_audio_render(audio, pending, AW_AUDIO_BLOCK)) {
                pump_failed = true;
                return;
            }
            pending_at = 0;
            pending_count = AW_AUDIO_BLOCK;
        }
        r.samples = pending + pending_at;
        r.count = pending_count - pending_at;
        if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_WRITE, 0, sizeof(r), &r)) {
            pump_failed = true;
            return;
        }
        pending_at += r.count;
        if (pending_at != pending_count) return;
    }
}
static void pump(void *ctx) {
#ifdef AW_DMA_FEED
    feed_poll(observing);
#endif
    (void)ctx;
    mk61_api->service();
    if (!startup_active()) return;
    audio_pump();
    poll_keys();
    if (pages_ready && storm->ready &&
        (storm->pending < AW_STORM_FRAMES || storm->prelude.uploading || storm->prelude.idle_return.active ||
         (storm->tail.active && (storm->tail.visible_pending || storm->tail.latch_pending ||
                                 storm->tail.black_rows < storm->tail.row_limit))) &&
        vm->part == AW_STORM_PART && !input.quit && !pump_failed)
        aw_storm_pump(storm, pages_display, &storm_lcd, NULL);
}
static bool storm_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    const bool ok = read_storm(offset, out, size);
    pump(NULL);
    return ok && !input.quit && !pump_failed;
}
static bool wait_for_frame_lead(void *ctx, unsigned lead_ms) {
    (void)ctx;
#if defined(AW_CS_PHASE) || defined(AW_PAGE_WRITE)
    aw_assets *prefetch_assets = phase_assets;
#else
    aw_assets *prefetch_assets = &assets;
#endif
    const uint32_t deadline = last_frame - lead_ms;
#ifdef AW_CS_PHASE
    PhasePoint begin = {0};
    unsigned loops = 0, saved = ph_wait_begin(lead_ms, deadline, &begin);
#endif
    while ((int32_t)(mk61_api->millis_ms() - deadline) < 0 && !input.quit && !pump_failed) {
#ifdef AW_CS_PHASE
        ++loops;
#endif
        pump(NULL);
        /* Leave room for a storage operation and the audio/input pump. */
        if (!input.quit && !pump_failed && (int32_t)(deadline - mk61_api->millis_ms()) >= 12 &&
            !aw_assets_prefetch_step(prefetch_assets))
            pump_failed = true;
    }
#ifdef AW_CS_PHASE
    ph_wait_end(saved, begin, loops);
#endif
    return !input.quit && !pump_failed;
}
static bool wait_for_frame(void *ctx) { return wait_for_frame_lead(ctx, 0); }
static bool wait_before_storm(void *ctx) { return wait_for_frame_lead(ctx, AW_STORM_ANCHOR_LEAD_MS); }
static bool frame_wait(void *ctx, unsigned slices) {
    (void)ctx;
    // Run the actual VM and mixer on the same inputs before real-time output.
    if (intro < TRACE_START) {
        if (!startup_active()) return false;
        int16_t discarded[AW_AUDIO_BLOCK];
        for (unsigned left = slices * 500; left;) {
            const unsigned n = left < AW_AUDIO_BLOCK ? left : AW_AUDIO_BLOCK;
            if (!aw_audio_render(audio, discarded, n)) return false;
            left -= n;
            mk61_api->service();
        }
        return !input.quit && !pump_failed;
    }
    if (!audio_open) {
        mk61_service_audio request = {0};
        request.rate = AW_AUDIO_RATE;
        request.volume = 100;
        if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_OPEN, 0, sizeof(request), &request)) {
#ifdef AW_CS_PHASE
            report("PH FAIL audio-open %u\n", intro);
#endif
            return false;
        }
        audio_open = true;
        last_frame = next_audio = mk61_api->millis_ms();
    }
    if (intro == TRACE_FIRST) audio_before = underruns();
#if defined(AW_PAGE_WRITE)
    wb_boundary(intro);
#elif defined(AW_CS_PHASE)
    ph_boundary(intro);
#elif !defined(AW_DMA_FEED)
    sample(intro);
#else
    observing = intro;
    previous_hit = 0;
    if (intro >= FFIRST && intro <= FLAST + 1) {
        const unsigned now = services->call(MK61_SERVICE_MICROS, 0, 0, 0, NULL);
        if (intro > FFIRST) feed_frames[intro - FFIRST - 1].when = now - feed_frames[intro - FFIRST - 1].when;
        if (intro <= FLAST) feed_frames[intro - FFIRST].when = now;
    }
#endif
    last_frame = aw_frame_deadline(last_frame, mk61_api->millis_ms(), slices);
    /* Two-page output can prepare the image before its display deadline. */
    return !input.quit && !pump_failed;
}
static unsigned try_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height, const uint8_t *pixels,
                         const uint16_t *palette, bool clear) {
    (void)ctx;
#ifdef AW_CS_PHASE
    const PhasePoint start = ph->active && ph->detail ? ph_point() : (PhasePoint){0, 0};
#endif
    mk61_service_color_frame frame = {0};
    frame.x = (uint16_t)x;
    frame.y = (uint16_t)(60 + y);
    frame.width = (uint16_t)width;
    frame.height = (uint16_t)height;
    frame.background = 0;
    frame.pixels = pixels;
    frame.pixel_bytes = width * height / 2;
    frame.format = MK61_COLOR_INDEX4 | (clear ? 0 : MK61_COLOR_PRESERVE_OUTSIDE);
    memcpy(frame.palette, palette, sizeof(frame.palette));
    const unsigned result =
        services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PRESENT, 0, sizeof(frame), &frame);
#if defined(AW_PAGE_WRITE)
    if (result == 1 && !wb_accept(x, y, width, height)) return 0;
#elif defined(AW_CS_PHASE)
    ph_attempt(result, x, y, width, height, start);
#elif !defined(AW_DMA_FEED)
    if (result == 1) {
        payload += width * height * 2u;
        ++windows;
    }
#else
    if (result == 1) feed_accept(width, height);
    feed_poll(observing);
#endif
    return result;
}
static bool present_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height, const uint8_t *pixels,
                         const uint16_t *palette, bool clear) {
#ifdef AW_CS_PHASE
    const unsigned queue = ph_queue(x, y, width, height);
#endif
    for (;;) {
        const unsigned result = try_rect(ctx, x, y, width, height, pixels, palette, clear);
        if (result == 1) break;
        if (result != 2 || input.quit || pump_failed) return false;
        if (pages_ready && !aw_display_pages_write_one(pages_display)) return false;
        pump(NULL);
    }
#ifdef AW_CS_PHASE
    ph_leave(queue);
#endif
    pump(NULL);
    return !input.quit && !pump_failed;
}
static bool page_control(unsigned operation, unsigned page) {
    const uint32_t value = page;
#ifdef AW_CS_PHASE
    const unsigned fence = ph_enter(PH_FENCE);
#endif
    for (;;) {
        const uint32_t result =
            services->call(MK61_SERVICE_COLOR_DISPLAY, operation, 0, sizeof(value), (void *)&value);
        if (result == 1) {
#ifdef AW_CS_PHASE
            ph_leave(fence);
#endif
            return true;
        }
        if (result != 2 || input.quit || pump_failed) return false;
        if (operation == MK61_COLOR_PAGE_SHOW && !aw_display_pages_write_one(pages_display)) return false;
        pump(NULL);
    }
}
static bool page_select(void *ctx, unsigned page) {
    (void)ctx;
    return page_control(MK61_COLOR_PAGE_SELECT, page);
}
static unsigned try_select(void *ctx, unsigned page) {
    (void)ctx;
    const uint32_t value = page;
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGE_SELECT, 0, sizeof(value), (void *)&value);
}
static bool page_show(void *ctx, unsigned page) {
    (void)ctx;
    const bool ok = page_control(MK61_COLOR_PAGE_SHOW, page);
#ifdef AW_PAGE_PAIR
    if (ok && intro == 2438) {
        ++wb.latches;
        wire_point(&wb.visible_wire[0]);
    } else if (ok && intro == 2442) {
        ++wb.black_latches;
        wire_point(&wb.visible_wire[4]);
    }
#endif
    return ok;
}
static uint32_t display_deadline(void *ctx) {
    (void)ctx;
    return last_frame;
}
static unsigned page_latch_at(void *ctx, unsigned page, uint32_t deadline, bool block) {
    uint32_t value = page;
    do {
        if ((int32_t)(mk61_api->millis_ms() - deadline) >= 0) {
            const unsigned result =
                services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGE_SHOW, 0, sizeof(value), &value);
            if (result != 2) return result;
        }
        if (!block) return 2;
        if (input.quit || pump_failed) return 0;
        pump(ctx);
    } while (true);
}
static bool page_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height, const uint8_t *pixels,
                      const uint16_t *palette, bool clear) {
    (void)clear;
    return present_rect(ctx, x, y, width, height, pixels, palette, false);
}
static bool present_pages(void *ctx, const uint8_t *pixels, const uint16_t *palette, const uint32_t *identities,
                          unsigned lead_ms) {
    const aw_display_wait_fn wait = lead_ms ? wait_before_storm : wait_for_frame;
    if (!aw_display_pages_present(pages_display, pixels, palette, identities, page_select, page_show, page_rect,
                                  wait, ctx))
        return false;
    /* Fence the last visible write before the next scheduled flash. */
    return !lead_ms || page_select(ctx, pages_display->visible);
}
static bool present_live(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    const uint32_t *identities = aw_video_band_identities(video);
    const bool shown = storm->ready ? aw_storm_present_intro(storm, pages_display, pixels, palette, identities,
                                                             &storm_lcd, present_pages, ctx)
                                    : present_pages(ctx, pixels, palette, identities, 0);
    return shown && !input.quit && !pump_failed;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    if (vm->part != AW_STORM_PART) return false;
    if (intro < TRACE_START) {
        ++intro;
        if (storm->ready) ++storm->at;
        return true;
    }
    if (intro == TRACE_LAST + 1) {
        audio_after = underruns();
        trace_done = input.quit = true;
        return false;
    }
#ifdef AW_CS_PHASE
    (void)ph_enter(PH_PRESENT);
#endif
    if (!present_live(ctx, pixels, palette)) {
#ifdef AW_CS_PHASE
        report("PH FAIL present %u %u %u %u %u\n", intro, (unsigned)pump_failed, (unsigned)input.quit,
               pages_display->visible, pages_display->selected);
#endif
        return false;
    }
#ifdef AW_CS_PHASE
    (void)ph_enter(PH_NEXT);
#endif
    if (intro == TRACE_START) {
        if (!page_select(ctx, pages_display->visible) || !startup_active()) return false;
        report("SCK FIRST %u %08X\n", intro, aw_storm_frame_hash(pixels, palette));
        startup_stage = NULL;
    }
#ifdef AW_TRACE_HOST
    if (intro >= TRACE_FIRST && intro <= TRACE_LAST) {
        extern void aw_host_check_pixels(const uint8_t *, const uint16_t *, unsigned);
        aw_host_check_pixels(pixels, palette, intro);
        report("SCK H %u %08X\n", intro, aw_storm_frame_hash(pixels, palette));
    }
#endif
    ++intro;
    return true;
}
#if !defined(AW_DMA_FEED) && !defined(AW_CS_PHASE) && !defined(AW_PAGE_WRITE)
static bool calibrate(unsigned rate, unsigned bits, unsigned ordinal) {
    uint16_t palette[16] = {0, 0xffff};
    WirePoint a = {0}, b = {0};
    WireBurst burst = {0};
    unsigned actual = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_SPI_HZ, 0, sizeof(rate), &rate);
    if (actual != rate || !page_select(NULL, 0)) return false;
    const unsigned width = ordinal == 3 ? 80 : 320, height = 5120 / width;
    wire_arm(bits);
    wire_point(&a);
    if (!present_rect(NULL, 0, 1 + 2 * (ordinal & 1), width, height, screen.data, palette, false) ||
        !page_select(NULL, 0))
        return false;
    wire_point(&b);
    wire_collect(&burst, bits);
    report("SCK C %u %u %u %u %u %u %u\n", ordinal, actual, b.us - a.us, b.edges - a.edges,
           b.selected - a.selected, b.gaps - a.gaps, b.blind - a.blind);
    print_burst(ordinal, &burst);
#ifndef AW_TRACE_HOST
    if (ordinal == 1) {
        report("SCK SPI %08X %08X %08X %08X\n", IO32(0x40040000), IO32(0x40040004), IO32(0x40040010),
               IO32(0x40040024));
        for (unsigned n = 0; n < 12; ++n) {
            const uint32_t base = 0x50000000u + n * 64u;
            const uint32_t ctrl = IO32(base + 12);
            const unsigned dreq = (ctrl >> 15) & 63u;
            if (dreq == 18 || dreq == 19)
                report("SCK DMA %u %08X %08X %08X\n", n, ctrl, IO32(base), IO32(base + 4));
        }
    }
#endif
    return true;
}
#endif
static void sound(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel) {
    (void)ctx;
    aw_audio_sound(audio, id, freq, volume, channel);
}
static void music(void *ctx, unsigned id, unsigned delay, unsigned pos) {
    (void)ctx;
    aw_audio_music(audio, id, delay, pos);
}
static void stop_audio(void *ctx) {
    (void)ctx;
    aw_audio_stop(audio);
}
int main(void) {
    /* The firmware reserves a separate stack. Keeping long-lived state there
     * leaves a larger contiguous heap block for the video-page cache. */
#if defined(AW_CS_PHASE) || defined(AW_PAGE_WRITE)
    // Exchange the table and the asset cache between BSS and the reserved
    // stack. All eight cache pages and both direct video buffers are retained.
    static aw_asset_entry entries[AW_ASSET_LIMIT];
    aw_assets assets;
    phase_assets = &assets;
#ifdef AW_CS_PHASE
    static PhaseMeter meter;
    ph = &meter;
#endif
#else
    aw_asset_entry entries[AW_ASSET_LIMIT];
#endif
#if !defined(AW_CS_PHASE) && !defined(AW_DMA_FEED) && !defined(AW_PAGE_WRITE)
    WirePoint samples[TRACE_LAST - TRACE_FIRST + 2] = {0};
    trace = samples;
    WireBurst waveforms[4] = {0};
    bursts = waveforms;
#elif defined(AW_DMA_FEED)
    FeedFrame results[FLAST - FFIRST + 1] = {0};
    feed_frames = results;
#endif
    aw_video video_state;
    video = &video_state;
    aw_audio audio_state;
    audio = &audio_state;
    aw_vm vm_state = {0};
    vm = &vm_state;
    pages_ready = false;
    aw_display_compact compact_state;
    compact_display = &compact_state;
    aw_display_pages pages_state;
    pages_display = &pages_state;
    aw_display_storm storm_state = {0};
    storm = &storm_state;
    aw_video_bands band_state;
    int16_t pending_samples[AW_AUDIO_BLOCK];
    pending = pending_samples;
    const char *error = "setup";
    bool graphics = false, paired_frames = false;
    bool audio_prepared = false, arena_reserved = false;
    uint32_t compute = 0;
    services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
                                                   MK61_SERVICE_CAP_COLOR_DISPLAY | MK61_SERVICE_CAP_FILE_BYTES |
                                                   MK61_SERVICE_CAP_AUDIO_STREAM | MK61_SERVICE_CAP_DEBUG_IO |
                                                   MK61_SERVICE_CAP_FORMAT);
    if (!services) return 1;
    begin_stage("memory", 5000);
    cache_base = file_size(storm_cache);
    if (!acquire_external()) {
        error = "external-memory";
        goto done;
    }
    /* Reserve required PCM first, then place both video pages and the
     * optional cache in one APP-owned arena if it fits. Older firmware and
     * fragmented heaps retain the existing individual-allocation fallback. */
    mk61_service_audio request = {0};
    request.rate = AW_AUDIO_RATE;
    request.volume = 100;
    audio_prepared =
        services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_PREPARE, 0, sizeof(request), &request) != 0;
    if (audio_prepared) arena_reserved = mk61_app_buffer_reserve(services, 2 * AW_VIDEO_PAGE_BYTES + 6144) != 0;
    if (!acquire_frames(&paired_frames)) {
        /* A premature PCM reservation must not prevent the mandatory page.
         * Retry the original allocation order before reporting failure. */
        if (arena_reserved) {
            (void)mk61_app_buffer_unreserve(services);
            arena_reserved = false;
        }
        if (audio_prepared) {
            (void)services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_CLOSE, 0, 0, NULL);
            audio_prepared = false;
        }
        if (!acquire_frames(&paired_frames)) {
            error = "two-frame-sram";
            goto done;
        }
    }
    if (!startup_active()) goto done;
    begin_stage("sounds", 15000);
    mk61_service_file_info info;
    mk61_service_file_bytes stat = {"MEMLIST.BIN", &info, 0, sizeof(info)};
    if (!services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(stat), &stat) || info.directory ||
        !info.size || info.size > 4096 || !file_read("MEMLIST.BIN", 0, screen.data, info.size)) {
        error = "memlist";
        goto done;
    }
    if (!aw_assets_init(&assets, entries, screen.data, info.size, external.size, NULL, bank_read, store_read,
                        store_write)) {
        error = "resource-list";
        goto done;
    }
    mk61_api->display_clear();
    mk61_api->display_write_m8(0, 0, "Loading sounds...", 17);
    mk61_api->service();
    if (!mk61_api->graphics_begin()) {
        error = "graphics";
        goto done;
    }
    graphics = true;
    assets.progress = pump;
    next_keys = next_audio = mk61_api->millis_ms();
    aw_prepared_cache prepared = {0};
    mk61_service_file_info prepared_info;
    mk61_service_file_bytes prepared_stat = {"AWCACHE.BIN", &prepared_info, 0, sizeof(prepared_info)};
    const bool has_prepared =
        services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(prepared_stat), &prepared_stat) &&
        !prepared_info.directory &&
        aw_prepared_open(&prepared, screen.data, info.size, assets.count, prepared_info.size, screen.data + 4096,
                         AW_VIDEO_PAGE_BYTES - 4096, NULL, prepared_read);
    for (unsigned id = 0; id < assets.count && startup_active() && !pump_failed; ++id) {
        const aw_asset_entry *e = &assets.entries[id];
        if (e->type || !e->bank || !e->size || !e->packed_size) continue;
        if (has_prepared && aw_prepared_load(&prepared, &assets, id)) continue;
        if (!startup_active() || !aw_assets_load(&assets, id)) {
            error = "sound-resource";
            goto done;
        }
    }
    if (input.quit) goto done;
    if (pump_failed) {
        error = "sound-pump";
        goto done;
    }
    begin_stage("display", 15000);
    mk61_api->display_write_m8(0, 0, "Preparing intro...", 18);
    uint32_t spi_hz = 24000000;
    const uint32_t actual_spi_hz =
        services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_SPI_HZ, 0, sizeof(spi_hz), &spi_hz);
    spi = actual_spi_hz;
    if (spi != 24000000) {
        error = "spi-clock";
        goto done;
    }
    storm_lcd = (aw_storm_output){page_select, page_show,     page_rect,        wait_for_frame_lead, try_select,
                                  try_rect,    actual_spi_hz, display_deadline, page_latch_at};
    compute = mk61_app_compute_begin(services);
    if (!aw_video_init(video, &assets, assets.used, screen.data, present, NULL)) {
        error = "video";
        goto done;
    }
    /* The native monochrome framebuffer is borrowed until graphics_end.
     * Store the previous color frame there losslessly, freeing the second
     * direct buffer to cache a game page. Once the old frame is compared,
     * the same borrowed framebuffer is scratch for the color rectangles. */
    mk61_service_framebuffer borrowed = {0};
    if (previous_frame.data && assets.used <= assets.capacity &&
        5 * AW_VIDEO_PAGE_BYTES <= assets.capacity - assets.used &&
        services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_FRAMEBUFFER, sizeof(borrowed), 0, &borrowed) &&
        borrowed.pixels && borrowed.bytes >= 12800 && borrowed.width == 320 && borrowed.height == 320 &&
        aw_display_compact_init(compact_display, &assets, assets.used + 4 * AW_VIDEO_PAGE_BYTES, borrowed.pixels,
                                12800, borrowed.pixels, 12800) &&
        aw_video_use_spare(video, previous_frame.data))
        compact_ready = true;
    if (compact_ready && 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES <= assets.capacity - assets.used)
        (void)aw_video_use_packed_page3(video, assets.used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES);
    aw_vm_host host = {NULL, frame_wait, pump, sound, music, stop_audio};
    if (!aw_vm_init(vm, &assets, video, host, (uint16_t)mk61_api->millis_ms())) {
        error = "vm-init";
        goto done;
    }
    aw_audio_init(audio, &assets, vm);
    vm->vars[0xBC] = 0x10;
    vm->vars[0xC6] = 0x80;
    vm->vars[0xF2] = 4000;
    vm->vars[0xDC] = 33;
    if (!aw_vm_set_part(vm, AW_STORM_PART)) {
        error = "intro-data";
        goto done;
    }
    if (compact_ready) {
        if (acquire_direct(&background_cache, 6144)) {
            if (!aw_video_use_background(video, background_cache.data, 6144)) drop_background();
        } else if (paired_frames && acquire_direct(&background_cache, 4096)) {
            if (!acquire_direct(&background_tail, 2048) ||
                !aw_video_use_background_split(video, background_cache.data, 4096, background_tail.data, 2048))
                drop_background();
        }
    }
    if (compact_ready && 6 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES <= assets.capacity - assets.used) {
        const uint32_t second = assets.used + 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES;
        mk61_service_color_pages config = {60, AW_VIDEO_HEIGHT};
        if (aw_display_pages_init(pages_display, compact_display, second)) {
            for (;;) {
                const uint32_t result = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGES_BEGIN_V2, 0,
                                                       sizeof(config), &config);
                if (result == 1) {
                    aw_video_track_bands(video, &band_state);
                    pages_ready = true;
                    break;
                }
                if (result != 2 || input.quit || pump_failed) break;
                pump(NULL);
            }
        }
        if (pages_ready && cache_base) {
            aw_storm_load(storm, &assets, second + AW_VIDEO_PAGE_BYTES, borrowed.pixels, cache_base, storm_read,
                          NULL);
            tail_loaded = storm->tail.available;
            hz = mk61_app_compute_hz(services);
            storm->tail.overlap = tail_loaded && spi == 24000000u && hz == 200000000u;
        }
    }
    if (!startup_active() || !pages_ready || !tail_loaded) {
        error = "pages-or-aws5";
        goto done;
    }
    {
        uint16_t pal[16] = {0};
        if (!page_select(NULL, 0) || !present_rect(NULL, 0, 0, 320, 16, screen.data, pal, false) ||
            !page_select(NULL, 0)) {
            error = "warm-transfer";
            goto done;
        }
    }
#if defined(AW_PAGE_WRITE)
#ifdef AW_PAGE_PAIR
    const unsigned marker = file_size("AWPGCTL.TAG");
    wb.mode = 2;
    switch (marker) {
        case 4: wb.mode = 0; break;
        case 5: wb.mode = 1; break;
        case 6: wb.mode = 3; break;
        case 7: wb.mode = 4; break;
        case 8: wb.mode = 5; break;
        case 9: wb.mode = 6; break;
    }
    aw_storm_configure_timing(&storm->tail, hz, spi);
    static const aw_storm_writeback policies[] = {{0, 0}, {5000, 0}, {2000, 0}, {1500, 1000}, {1000, 1400}};
    storm->tail.writeback[0] = policies[wb.mode > 4 ? 4 : wb.mode];
    // Keep the same 200 rows and vary when eight hidden rows cross the bus.
    static const uint8_t black_limits[][3] = {{32, 64, 96}, {40, 64, 96}, {32, 56, 88}};
    memcpy(storm->tail.black_before_rows, black_limits[wb.mode > 4 ? wb.mode - 4 : 0], sizeof(black_limits[0]));
#else
    wb.mode = file_size("AWPGCTL.TAG") != 4;
#endif
    if (!wb_calibrate()) {
        error = "writeback-calibration";
        goto done;
    }
    report("WB MODE %u %u %u %u %u %u %u %u\n", wb.mode, hz, spi, (unsigned)storm->tail.overlap,
           (unsigned)audio_prepared, (unsigned)paired_frames, background_cache.size, background_tail.size);
    begin_stage("intro", 65000);
#elif defined(AW_CS_PHASE)
    ph->detail = file_size("AWPHCTL.TAG") != 4;
    if (!ph_calibrate()) {
        error = "PIO-calibration";
        goto done;
    }
    report("PH CLOCK %u %u %u\n", hz, spi, (unsigned)storm->tail.overlap);
    report("PH START pcm=%u arena=%u paired=%u bg=%u tail=%u\n", (unsigned)audio_prepared, (unsigned)arena_reserved,
           (unsigned)paired_frames, background_cache.size, background_tail.size);
    begin_stage("intro", 65000);
#elif !defined(AW_DMA_FEED)
    if (!wire_begin()) {
        error = "PIO0-in-use";
        goto done;
    }
    report("SCK CLOCK %u %u %u\n", hz, spi, (unsigned)storm->tail.overlap);
    if (!calibrate(12000000, 1, 0) || !calibrate(24000000, 1, 1) || !calibrate(24000000, 4, 2) ||
        !calibrate(24000000, 1, 3)) {
        error = "calibration";
        goto done;
    }
    begin_stage("intro", 65000);
#else
    if (!feed_init()) {
        error = "DMA-channels";
        goto done;
    }
    report("FEED CLOCK %u %u\n", hz, spi);
    begin_stage("intro", 95000);
#endif
    last_frame = mk61_api->millis_ms();
    next_keys = next_audio = last_frame;
    (void)services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(previous), 0, previous);
    while (!input.quit && !pump_failed) {
        pump(NULL);
        if (pump_failed || input.quit) break;
        if (!aw_vm_frame(vm, &input)) {
            error = "vm-step";
            break;
        }
    }
    if (pump_failed && !input.quit) error = "runtime-pump";
done:
#ifndef AW_DMA_FEED
    wire_end();
#endif
    if (trace_done) {
#if defined(AW_PAGE_WRITE)
        wb_print();
#elif defined(AW_CS_PHASE)
        ph_print();
#elif !defined(AW_DMA_FEED)
        for (unsigned k = 0; k < 4; ++k)
            print_burst(raw_frames[k], &bursts[k]);
        for (unsigned k = 0; k <= TRACE_LAST - TRACE_FIRST; ++k) {
            const WirePoint *a = trace + k, *b = a + 1;
            report("SCK F %u %u %u %u %u %u %u %u\n", TRACE_FIRST + k, b->us - a->us, b->edges - a->edges,
                   b->selected - a->selected, b->gaps - a->gaps, b->blind - a->blind, b->bytes - a->bytes,
                   b->rects - a->rects);
        }
#else
        for (unsigned f = FFIRST; f <= FLAST; ++f) {
            FeedFrame *r = feed_frames + f - FFIRST;
            report("FEED F %u %u %u %u %u %u %u %u %u %u %u %u\n", f, r->when, r->polls, r->selected, r->running,
                   r->hits, r->positions, r->stripe, r->source_zero, r->confirmed_us, r->first, r->last);
        }
#endif
        report("SCK END %u %u\n", audio_before, audio_after);
    } else {
        report("SCK FAIL %s %s %u\n", startup_stage ? startup_stage : "capture",
               startup_timeout ? "timeout" : error, intro);
    }
    if (audio_open || audio_prepared) services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_CLOSE, 0, 0, NULL);
    if (compute) (void)mk61_app_compute_end(services, compute);
    if (graphics) {
        services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_END, 0, 0, NULL);
        // Discard the progress text before ending graphics restores the console.
        mk61_api->display_clear();
        mk61_api->graphics_end();
    }
    drop_background();
    if (previous_frame.handle) mk61_app_buffer_release(services, previous_frame.handle);
    if (screen.handle) mk61_app_buffer_release(services, screen.handle);
    if (arena_reserved) (void)mk61_app_buffer_unreserve(services);
    if (external.handle) mk61_app_buffer_release(services, external.handle);
    return 0;
}
