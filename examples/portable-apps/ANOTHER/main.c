#include "mk61_app.h"
#include "audio.h"
#include "display.h"
#include "display_compact.h"
#include "pacing.h"
#include <string.h>

#define EXTERNAL_BYTES (2u * 1024u * 1024u)
static const mk61_app_services *services;
static mk61_service_buffer external, screen, previous_frame, background_cache, background_tail;
static aw_assets assets;
static aw_video video;
static aw_display display;
static aw_display_compact compact_display;
static aw_vm vm;
static aw_audio audio;
static aw_input input;
static uint8_t keys[32], previous[32];
static int16_t pending[AW_AUDIO_BLOCK];
static unsigned pending_at, pending_count;
static uint32_t next_keys, next_audio, last_frame;
static bool audio_open, first_strip, pump_failed, compact_ready;
static void pump(void *ctx);

static bool acquire_direct(mk61_service_buffer *buffer, unsigned bytes) {
    if (mk61_app_buffer_acquire(services, bytes, MK61_BUFFER_DIRECT, buffer) && buffer->data) return true;
    if (buffer->handle) mk61_app_buffer_release(services, buffer->handle);
    *buffer = mk61_app_buffer_request();
    return false;
}
static void drop_background(void) {
    video.background = video.background_tail = NULL;
    video.background_valid = video.background_attempted = false;
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
        if (c == 'c' && vm.part != AW_VM_LAST_PART) input.code = true;
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
            if (!aw_audio_render(&audio, pending, AW_AUDIO_BLOCK)) { pump_failed = true; return; }
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
}
static bool frame_wait(void *ctx, unsigned slices) {
    (void)ctx;
    const uint32_t deadline = aw_frame_deadline(last_frame, mk61_api->millis_ms(), slices);
    while ((int32_t)(mk61_api->millis_ms() - deadline) < 0 && !input.quit && !pump_failed) pump(NULL);
    last_frame = deadline;
    return !input.quit && !pump_failed;
}
static bool present_rect(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height,
                         const uint8_t *pixels, const uint16_t *palette, bool clear) {
    (void)ctx;
    mk61_service_color_frame frame = {0};
    frame.x = (uint16_t)x; frame.y = (uint16_t)(60 + y);
    frame.width = (uint16_t)width; frame.height = (uint16_t)height; frame.background = 0;
    frame.pixels = pixels; frame.pixel_bytes = width * height / 2;
    frame.format = MK61_COLOR_INDEX4 | (clear ? 0 : MK61_COLOR_PRESERVE_OUTSIDE);
    memcpy(frame.palette, palette, sizeof(frame.palette));
    for (;;) {
        const uint32_t result = services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_PRESENT, 0, sizeof(frame), &frame);
        if (result == 1) break;
        if (result != 2 || input.quit || pump_failed) return false;
        pump(NULL);
    }
    pump(NULL);
    return !input.quit && !pump_failed;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    (void)ctx;
    if (compact_ready)
        return aw_display_compact_present(&compact_display, pixels, palette, present_rect, NULL);
    if (previous_frame.data)
        return aw_display_present(&display, pixels, palette, present_rect, NULL);
    for (unsigned y = 0; y < 200;) {
        const unsigned rows = 200 - y < 80 ? 200 - y : 80;
        if (!present_rect(NULL, 0, y, 320, rows, pixels + y * 160, palette, first_strip)) return false;
        first_strip = false; y += rows;
    }
    return true;
}
static void sound(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel) {
    (void)ctx; aw_audio_sound(&audio, id, freq, volume, channel);
}
static void music(void *ctx, unsigned id, unsigned delay, unsigned pos) {
    (void)ctx; aw_audio_music(&audio, id, delay, pos);
}
static void stop_audio(void *ctx) { (void)ctx; aw_audio_stop(&audio); }
static void message(const char *line1, const char *line2) {
    mk61_api->display_clear();
    mk61_api->display_write_m8(0, 0, line1, (uint32_t)strlen(line1));
    if (line2) mk61_api->display_write_m8(0, 1, line2, (uint32_t)strlen(line2));
    (void)mk61_api->key_wait();
}

int main(void) {
    const char *error = NULL; bool graphics = false, paired_frames = false; uint32_t compute = 0;
    services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
        MK61_SERVICE_CAP_COLOR_DISPLAY | MK61_SERVICE_CAP_TEXT_COLORS | MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_AUDIO_STREAM);
    if (!services) { message("Update PicoCalc", "firmware / PSRAM"); return 0; }
    if (!mk61_app_buffer_acquire(services, EXTERNAL_BYTES, MK61_BUFFER_EXTERNAL, &external)) {
        error = "Not enough memory"; goto done;
    }
    /* Adjacent pages use one service slot, leaving two for a background
     * cache even when the free heap is split into smaller blocks. */
    if (acquire_direct(&screen, 2 * AW_VIDEO_PAGE_BYTES)) {
        paired_frames = true;
        previous_frame.data = screen.data + AW_VIDEO_PAGE_BYTES;
    } else {
        if (!acquire_direct(&screen, AW_VIDEO_PAGE_BYTES)) { error = "Not enough memory"; goto done; }
        (void)acquire_direct(&previous_frame, AW_VIDEO_PAGE_BYTES);
    }
    if (previous_frame.data) aw_display_init(&display, previous_frame.data);
    mk61_service_file_info info;
    mk61_service_file_bytes stat = {"MEMLIST.BIN", &info, 0, sizeof(info)};
    if (!services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(stat), &stat) ||
        info.directory || !info.size || info.size > 4096 ||
        !file_read("MEMLIST.BIN", 0, screen.data, info.size)) {
        error = "Missing MEMLIST.BIN"; goto done;
    }
    if (!aw_assets_init(&assets, screen.data, info.size, EXTERNAL_BYTES, NULL, bank_read, store_read, store_write)) {
        error = "Invalid game data"; goto done;
    }
    if (!mk61_api->graphics_begin()) { error = "Display unavailable"; goto done; }
    graphics = true;
    uint32_t spi_hz = 24000000;
    (void)services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_SPI_HZ, 0, sizeof(spi_hz), &spi_hz);
    compute = mk61_app_compute_begin(services);
    if (!aw_video_init(&video, &assets, assets.used, screen.data, present, NULL)) { error = "Video init failed"; goto done; }
    /* The native monochrome framebuffer is borrowed until graphics_end.
     * Store the previous color frame there losslessly, freeing the second
     * direct buffer to cache a game page. Once the old frame is compared,
     * the same borrowed framebuffer is scratch for the color rectangles. */
    mk61_service_framebuffer borrowed = {0};
    if (previous_frame.data && assets.used <= assets.capacity &&
        5 * AW_VIDEO_PAGE_BYTES <= assets.capacity - assets.used &&
        services->call(MK61_SERVICE_DISPLAY, MK61_SERVICE_DISPLAY_FRAMEBUFFER, sizeof(borrowed), 0, &borrowed) &&
        borrowed.pixels && borrowed.bytes >= 12800 && borrowed.width == 320 && borrowed.height == 320 &&
        aw_display_compact_init(&compact_display, &assets, assets.used + 4 * AW_VIDEO_PAGE_BYTES,
                                borrowed.pixels, 12800, borrowed.pixels, 12800) &&
        aw_video_use_spare(&video, previous_frame.data)) compact_ready = true;
    if (compact_ready && 5 * AW_VIDEO_PAGE_BYTES + AW_VIDEO_PAGE3_PACKED_BYTES <= assets.capacity - assets.used)
        (void)aw_video_use_packed_page3(&video, assets.used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES);
    aw_vm_host host = {NULL, frame_wait, pump, sound, music, stop_audio};
    if (!aw_vm_init(&vm, &assets, &video, host, (uint16_t)mk61_api->millis_ms())) { error = "VM init failed"; goto done; }
    aw_audio_init(&audio, &assets, &vm);
    if (!aw_vm_set_part(&vm, AW_VM_FIRST_PART)) { error = "Cannot load game"; goto done; }
    mk61_service_audio request = {0}; request.rate = AW_AUDIO_RATE; request.volume = 100;
    if (!services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_OPEN, 0, sizeof(request), &request)) {
        error = "Audio unavailable"; goto done;
    }
    audio_open = true; assets.progress = pump;
    if (compact_ready) {
        if (acquire_direct(&background_cache, 6144)) {
            if (!aw_video_use_background(&video, background_cache.data, 6144)) drop_background();
        } else if (paired_frames && acquire_direct(&background_cache, 4096)) {
            if (!acquire_direct(&background_tail, 2048) ||
                !aw_video_use_background_split(&video, background_cache.data, 4096, background_tail.data, 2048))
                drop_background();
        }
    }
    first_strip = true; last_frame = mk61_api->millis_ms();
    next_keys = next_audio = last_frame;
    (void)services->call(MK61_SERVICE_KEYBOARD, MK61_SERVICE_KEY_BITMAP, sizeof(previous), 0, previous);
    while (!input.quit && !pump_failed) {
        pump(NULL);
        if (!aw_vm_frame(&vm, &input)) {
            if (!input.quit) error = "Game runtime error";
            break;
        }
    }
    if (pump_failed && !input.quit) error = "Audio or input error";
done:
    if (audio_open) services->call(MK61_SERVICE_AUDIO_STREAM, MK61_AUDIO_CLOSE, 0, 0, NULL);
    if (compute) (void)mk61_app_compute_end(services, compute);
    if (graphics) { services->call(MK61_SERVICE_COLOR_DISPLAY, MK61_COLOR_END, 0, 0, NULL); mk61_api->graphics_end(); }
    drop_background();
    if (previous_frame.handle) mk61_app_buffer_release(services, previous_frame.handle);
    if (screen.handle) mk61_app_buffer_release(services, screen.handle);
    if (external.handle) mk61_app_buffer_release(services, external.handle);
    if (error) message(error, "Press any key");
    return 0;
}
