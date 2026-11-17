#include "mk61_app.h"
#include "audio.h"
#include "display.h"
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
static aw_assets assets;
static aw_video *video;
static aw_display display;
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
static bool audio_open, first_strip, pump_failed, compact_ready, pages_ready;
static void pump(void *ctx);

static bool acquire_direct(mk61_service_buffer *buffer, unsigned bytes) {
    if (mk61_app_buffer_acquire(services, bytes, MK61_BUFFER_DIRECT, buffer) && buffer->data) return true;
    if (buffer->handle) mk61_app_buffer_release(services, buffer->handle);
    *buffer = mk61_app_buffer_request();
    return false;
}
static bool acquire_frames(bool *paired) {
    if (acquire_direct(&screen, 2 * AW_VIDEO_PAGE_BYTES)) {
        *paired = true; previous_frame.data = screen.data + AW_VIDEO_PAGE_BYTES; return true;
    }
    if (!acquire_direct(&screen, AW_VIDEO_PAGE_BYTES)) return false;
    (void)acquire_direct(&previous_frame, AW_VIDEO_PAGE_BYTES);
    return true;
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
static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    (void)ctx; static const char hex[] = "0123456789ABCDEF";
    char path[] = "BANK00"; path[4] = hex[bank >> 4]; path[5] = hex[bank & 15];
    if (audio_open) pump(NULL);
    const bool ok = file_read(path, offset, out, size);
    if (audio_open) pump(NULL); else mk61_api->service();
    return ok && !pump_failed;
}
static bool prepared_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    return file_read("AWCACHE.BIN", offset, out, size);
}
static bool store_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    mk61_service_buffer r = mk61_app_buffer_request();
    r.handle = external.handle; r.offset = offset; r.data = out; r.size = size;
    return services->call(MK61_SERVICE_BUFFER, MK61_BUFFER_READ, 0, sizeof(r), &r) != 0;
}
static bool store_write(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    (void)ctx;
    mk61_service_buffer r = mk61_app_buffer_request();
    r.handle = external.handle; r.offset = offset; r.data = (uint8_t *)in; r.size = size;
    return services->call(MK61_SERVICE_BUFFER, MK61_BUFFER_WRITE, 0, sizeof(r), &r) != 0;
}
static bool pressed(const uint8_t *map, unsigned key) { return (map[key / 8] & (1u << (key & 7))) != 0; }
static bool letter(const uint8_t *map, unsigned c) { return pressed(map, c) || pressed(map, c - 32); }
static void poll_keys(void) {
    const uint32_t now = mk61_api->millis_ms();
    if ((int32_t)(now - next_keys) < 0) return;
    next_keys = now + 20;
    if (!services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(keys), 0, keys)) {
        pump_failed = true; return;
    }
    input.directions = 0;
    if (pressed(keys, 0xB4)) input.directions |= AW_INPUT_LEFT;
    if (pressed(keys, 0xB7)) input.directions |= AW_INPUT_RIGHT;
    if (pressed(keys, 0xB5)) input.directions |= AW_INPUT_UP;
    if (pressed(keys, 0xB6)) input.directions |= AW_INPUT_DOWN;
    input.button = pressed(keys, ' ') || pressed(keys, '\r') || pressed(keys, '\n');
    if ((pressed(keys, 0x1B) || pressed(keys, 0xB1) || pressed(keys, 0x90)) &&
        !(pressed(previous, 0x1B) || pressed(previous, 0xB1) || pressed(previous, 0x90))) input.quit = true;
    for (unsigned c = 'a'; c <= 'z'; ++c) if (letter(keys, c) && !letter(previous, c)) {
        if (c == 'c' && vm->part != AW_VM_LAST_PART) input.code = true;
        else input.last_char = (uint8_t)c;
        break;
    }
    if ((pressed(keys, 8) || pressed(keys, 127)) && !(pressed(previous, 8) || pressed(previous, 127))) input.last_char = 8;
    memcpy(previous, keys, sizeof(keys));
}
static void audio_pump(void) {
    if (!audio_open || pump_failed) return;
    const uint32_t now = mk61_api->millis_ms();
    if ((int32_t)(now - next_audio) < 0) return;
    next_audio = now + 2;
    mk61_service_audio r = {0};
    if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_STATUS, 0, sizeof(r), &r)) { pump_failed = true; return; }
    for (unsigned blocks = 0; blocks < 9 && r.queued < 1000; ++blocks) {
        if (pending_at == pending_count) {
            if (!aw_audio_render(audio, pending, AW_AUDIO_BLOCK)) { pump_failed = true; return; }
            pending_at = 0; pending_count = AW_AUDIO_BLOCK;
        }
        r.samples = pending + pending_at; r.count = pending_count - pending_at;
        if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_WRITE, 0, sizeof(r), &r)) { pump_failed = true; return; }
        pending_at += r.count;
        if (pending_at != pending_count) return;
    }
}
static void pump(void *ctx) {
    (void)ctx; mk61_api->service(); audio_pump(); poll_keys();
    if (pages_ready && storm->ready && (storm->pending < AW_STORM_FRAMES || storm->prelude.uploading) &&
        vm->part == AW_STORM_PART && !input.quit && !pump_failed)
        aw_storm_pump(storm, pages_display, &storm_lcd, NULL);
}
static bool storm_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    (void)ctx;
    const bool ok = file_read(storm_cache, offset, out, size);
    pump(NULL);
    return ok && !input.quit && !pump_failed;
}
static bool wait_for_frame_lead(void *ctx, unsigned lead_ms) {
    (void)ctx;
    const uint32_t deadline = last_frame - lead_ms;
    while ((int32_t)(mk61_api->millis_ms() - deadline) < 0 && !input.quit && !pump_failed) {
        pump(NULL);
        /* Leave room for a storage operation and the audio/input pump. */
        if (!input.quit && !pump_failed && (int32_t)(deadline - mk61_api->millis_ms()) >= 12 &&
            !aw_assets_prefetch_step(&assets)) pump_failed = true;
    }
    return !input.quit && !pump_failed;
}
static bool wait_for_frame(void *ctx) { return wait_for_frame_lead(ctx, 0); }
static bool wait_before_storm(void *ctx) { return wait_for_frame_lead(ctx, AW_STORM_ANCHOR_LEAD_MS); }
static bool frame_wait(void *ctx, unsigned slices) {
    last_frame = aw_frame_deadline(last_frame, mk61_api->millis_ms(), slices);
    /* Two-page output can prepare the image before its display deadline. */
    return pages_ready ? !input.quit && !pump_failed : wait_for_frame(ctx);
}
static unsigned try_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                         const uint8_t *pixels, const uint16_t *palette, bool clear) {
    (void)ctx;
    mk61_service_color_frame frame = {0};
    frame.x = (uint16_t)x; frame.y = (uint16_t)(60 + y);
    frame.width = (uint16_t)width; frame.height = (uint16_t)height; frame.background = 0;
    frame.pixels = pixels; frame.pixel_bytes = width * height / 2;
    frame.format = MK61_COLOR_INDEX4 | (clear ? 0 : MK61_COLOR_PRESERVE_OUTSIDE);
    memcpy(frame.palette, palette, sizeof(frame.palette));
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PRESENT, 0, sizeof(frame), &frame);
}
static bool present_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                         const uint8_t *pixels, const uint16_t *palette, bool clear) {
    for (;;) {
        const unsigned result = try_rect(ctx, x, y, width, height, pixels, palette, clear);
        if (result == 1) break;
        if (result != 2 || input.quit || pump_failed) return false;
        if (pages_ready && !aw_display_pages_write_one(pages_display)) return false;
        pump(NULL);
    }
    pump(NULL);
    return !input.quit && !pump_failed;
}
static bool page_control(unsigned operation, unsigned page) {
    const uint32_t value = page;
    for (;;) {
        const uint32_t result = services->call(MK61_SERVICE_COLOR_DISPLAY, operation, 0, sizeof(value), (void *)&value);
        if (result == 1) return true;
        if (result != 2 || input.quit || pump_failed) return false;
        if (operation == MK61_COLOR_PAGE_SHOW && !aw_display_pages_write_one(pages_display)) return false;
        pump(NULL);
    }
}
static bool page_select(void *ctx, unsigned page) { (void)ctx; return page_control(MK61_COLOR_PAGE_SELECT, page); }
static unsigned try_select(void *ctx, unsigned page) {
    (void)ctx;
    const uint32_t value = page;
    return services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGE_SELECT, 0, sizeof(value), (void *)&value);
}
static bool page_show(void *ctx, unsigned page) { (void)ctx; return page_control(MK61_COLOR_PAGE_SHOW, page); }
static bool page_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                      const uint8_t *pixels, const uint16_t *palette, bool clear) {
    (void)clear;
    return present_rect(ctx, x, y, width, height, pixels, palette, false);
}
static bool end_pages(void) {
    for (;;) {
        const uint32_t result = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGES_END, 0, 0, NULL);
        if (result == 1) return true;
        if (result != 2 || input.quit || pump_failed) return false;
        pump(NULL);
    }
}
static bool present_pages(void *ctx, const uint8_t *pixels, const uint16_t *palette,
                          const uint32_t *identities, unsigned lead_ms) {
    const aw_display_wait_fn wait = lead_ms ? wait_before_storm : wait_for_frame;
    if (!aw_display_pages_present(pages_display, pixels, palette, identities,
                                  page_select, page_show, page_rect, wait, ctx)) return false;
    /* Fence the last visible write before the next scheduled flash. */
    return !lead_ms || page_select(ctx, pages_display->visible);
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    if (pages_ready) {
        const bool intro = vm->part == AW_STORM_PART;
        /* Other parts can overwrite either LCD page while the intro is paused. */
        if (!intro && storm->at) storm->ready = false;
        const uint32_t *identities = aw_video_band_identities(video);
        const bool shown = storm->ready && intro
            ? aw_storm_present_intro(storm, pages_display, pixels, palette, identities,
                                    &storm_lcd, present_pages, ctx)
            : present_pages(ctx, pixels, palette, identities, 0);
        if (shown) return !input.quit && !pump_failed;
        if (assets.fault || !wait_for_frame(ctx) || !end_pages()) return false;
        /* An optional display transaction failed: restore a complete ordinary
         * frame, with no assumptions about either partially written page. */
        pages_ready = false; compact_display->valid = false;
        aw_video_track_bands(video, NULL);
    }
    if (input.quit || pump_failed) return false;
    if (compact_ready) {
        return aw_display_compact_present(compact_display, pixels, palette, present_rect, NULL) &&
            !input.quit && !pump_failed;
    }
    if (previous_frame.data) {
        return aw_display_present(&display, pixels, palette, present_rect, NULL) &&
            !input.quit && !pump_failed;
    }
    for (unsigned y = 0; y < 200;) {
        const unsigned rows = 200 - y < 80 ? 200 - y : 80;
        if (!present_rect(NULL, 0, y, 320, rows, pixels + y * 160, palette, first_strip)) return false;
        first_strip = false; y += rows;
    }
    return true;
}
static void sound(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel) {
    (void)ctx; aw_audio_sound(audio, id, freq, volume, channel);
}
static void music(void *ctx, unsigned id, unsigned delay, unsigned pos) {
    (void)ctx; aw_audio_music(audio, id, delay, pos);
}
static void stop_audio(void *ctx) { (void)ctx; aw_audio_stop(audio); }
static void message(const char *line1, const char *line2) {
    mk61_api->display_clear();
    mk61_api->display_write_m8(0, 0, line1, (uint32_t)strlen(line1));
    if (line2) mk61_api->display_write_m8(0, 1, line2, (uint32_t)strlen(line2));
    (void)mk61_api->key_wait();
}

int main(void) {
    /* The firmware reserves a separate stack. Keeping long-lived state there
     * leaves a larger contiguous heap block for the video-page cache. */
    aw_asset_entry entries[AW_ASSET_LIMIT];
    aw_video video_state; video = &video_state;
    aw_audio audio_state; audio = &audio_state;
    aw_vm vm_state = {0}; vm = &vm_state; pages_ready = false;
    aw_display_compact compact_state; compact_display = &compact_state;
    aw_display_pages pages_state; pages_display = &pages_state;
    aw_display_storm storm_state = {0}; storm = &storm_state;
    aw_video_bands band_state;
    int16_t pending_samples[AW_AUDIO_BLOCK]; pending = pending_samples;
    const char *error = NULL; bool graphics = false, paired_frames = false;
    bool audio_prepared = false, arena_reserved = false; uint32_t compute = 0;
    services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
        MK61_SERVICE_CAP_COLOR_DISPLAY | MK61_SERVICE_CAP_TEXT_COLORS | MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_AUDIO_STREAM);
    if (!services) { message("Update PicoCalc", "firmware / PSRAM"); return 0; }
    char storm_magic[4];
    const bool extended_storm = file_read(storm_cache, 0, storm_magic, sizeof(storm_magic)) &&
        !memcmp(storm_magic, "AWS3", sizeof(storm_magic));
    if (!(extended_storm && mk61_app_buffer_acquire(services, EXTERNAL_BYTES + AW_VIDEO_PAGE_BYTES,
                                                    MK61_BUFFER_EXTERNAL, &external)) &&
        !mk61_app_buffer_acquire(services, EXTERNAL_BYTES, MK61_BUFFER_EXTERNAL, &external)) {
        error = "Not enough memory"; goto done;
    }
    /* Reserve required PCM first, then place both video pages and the
     * optional cache in one APP-owned arena if it fits. Older firmware and
     * fragmented heaps retain the existing individual-allocation fallback. */
    mk61_service_audio request = {0}; request.rate = AW_AUDIO_RATE; request.volume = 100;
    audio_prepared = services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_PREPARE, 0, sizeof(request), &request) != 0;
    if (audio_prepared)
        arena_reserved = mk61_app_buffer_reserve(services, 2 * AW_VIDEO_PAGE_BYTES + 6144) != 0;
    if (!acquire_frames(&paired_frames)) {
        /* A premature PCM reservation must not prevent the mandatory page.
         * Retry the original allocation order before reporting failure. */
        if (arena_reserved) { (void)mk61_app_buffer_unreserve(services); arena_reserved = false; }
        if (audio_prepared) {
            (void)services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_CLOSE, 0, 0, NULL);
            audio_prepared = false;
        }
        if (!acquire_frames(&paired_frames)) { error = "Not enough memory"; goto done; }
    }
    if (previous_frame.data) aw_display_init(&display, previous_frame.data);
    mk61_service_file_info info;
    mk61_service_file_bytes stat = {"MEMLIST.BIN", &info, 0, sizeof(info)};
    if (!services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(stat), &stat) ||
        info.directory || !info.size || info.size > 4096 ||
        !file_read("MEMLIST.BIN", 0, screen.data, info.size)) {
        error = "Missing MEMLIST.BIN"; goto done;
    }
    if (!aw_assets_init(&assets, entries, screen.data, info.size, external.size, NULL, bank_read, store_read, store_write)) {
        error = "Invalid game data"; goto done;
    }
    mk61_api->display_clear();
    mk61_api->display_write_m8(0, 0, "Loading sounds...", 17);
    mk61_api->service();
    if (!mk61_api->graphics_begin()) { error = "Display unavailable"; goto done; }
    graphics = true;
    assets.progress = pump;
    next_keys = next_audio = mk61_api->millis_ms();
    aw_prepared_cache prepared = {0};
    mk61_service_file_info prepared_info;
    mk61_service_file_bytes prepared_stat = {"AWCACHE.BIN", &prepared_info, 0, sizeof(prepared_info)};
    const bool has_prepared = services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0,
                                              sizeof(prepared_stat), &prepared_stat) &&
        !prepared_info.directory &&
        aw_prepared_open(&prepared, screen.data, info.size, assets.count, prepared_info.size,
                         screen.data + 4096, AW_VIDEO_PAGE_BYTES - 4096, NULL, prepared_read);
    for (unsigned id = 0; id < assets.count && !input.quit && !pump_failed; ++id) {
        const aw_asset_entry *e = &assets.entries[id];
        if (e->type || !e->bank || !e->size || !e->packed_size) continue;
        if ((!has_prepared || !aw_prepared_load(&prepared, &assets, id)) &&
            !aw_assets_load(&assets, id) && assets.fault) {
            error = "Cannot load game"; goto done;
        }
    }
    if (input.quit) goto done;
    if (pump_failed) { error = "Input unavailable"; goto done; }
    uint32_t spi_hz = 24000000;
    const uint32_t actual_spi_hz = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_SPI_HZ,
                                               0, sizeof(spi_hz), &spi_hz);
    storm_lcd = (aw_storm_output){page_select, page_show, page_rect, wait_for_frame_lead,
                                 try_select, try_rect, actual_spi_hz};
    compute = mk61_app_compute_begin(services);
    if (!aw_video_init(video, &assets, assets.used, screen.data, present, NULL)) { error = "Video init failed"; goto done; }
    /* The native monochrome framebuffer is borrowed until graphics_end.
     * Store the previous color frame there losslessly, freeing the second
     * direct buffer to cache a game page. Once the old frame is compared,
     * the same borrowed framebuffer is scratch for the color rectangles. */
    mk61_service_framebuffer borrowed = {0};
    if (previous_frame.data && assets.used <= assets.capacity &&
        5 * AW_VIDEO_PAGE_BYTES <= assets.capacity - assets.used &&
        services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_FRAMEBUFFER, sizeof(borrowed), 0, &borrowed) &&
        borrowed.pixels && borrowed.bytes >= 12800 && borrowed.width == 320 && borrowed.height == 320 &&
        aw_display_compact_init(compact_display, &assets, assets.used + 4 * AW_VIDEO_PAGE_BYTES,
                                borrowed.pixels, 12800, borrowed.pixels, 12800) &&
        aw_video_use_spare(video, previous_frame.data)) compact_ready = true;
    if (compact_ready && 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES <= assets.capacity - assets.used)
        (void)aw_video_use_packed_page3(video, assets.used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES);
    aw_vm_host host = {NULL, frame_wait, pump, sound, music, stop_audio};
    if (!aw_vm_init(vm, &assets, video, host, (uint16_t)mk61_api->millis_ms())) { error = "VM init failed"; goto done; }
    aw_audio_init(audio, &assets, vm);
    if (!aw_vm_set_part(vm, AW_VM_FIRST_PART)) { error = "Cannot load game"; goto done; }
    if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_OPEN, 0, sizeof(request), &request)) {
        error = "Audio unavailable"; goto done;
    }
    audio_open = true;
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
                const uint32_t result = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PAGES_BEGIN_V2, 0, sizeof(config), &config);
                if (result == 1) {
                    aw_video_track_bands(video, &band_state);
                    pages_ready = true;
                    break;
                }
                if (result != 2 || input.quit || pump_failed) break;
                pump(NULL);
            }
        }
        if (pages_ready) {
            mk61_service_file_info storm_info;
            mk61_service_file_bytes request = {storm_cache, &storm_info, 0, sizeof(storm_info)};
            if (services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(request), &request) &&
                !storm_info.directory)
                aw_storm_load(storm, &assets, second + AW_VIDEO_PAGE_BYTES, borrowed.pixels,
                              storm_info.size, storm_read, NULL);
        }
    }
    first_strip = true; last_frame = mk61_api->millis_ms();
    next_keys = next_audio = last_frame;
    (void)services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(previous), 0, previous);
    while (!input.quit && !pump_failed) {
        pump(NULL);
        if (!aw_vm_frame(vm, &input)) {
            if (!input.quit) error = "Game runtime error";
            break;
        }
    }
    if (pump_failed && !input.quit) error = "Audio or input error";
done:
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
    if (error) message(error, "Press any key");
    return 0;
}
