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
static aw_display_compact compact;
static uint8_t compact_previous[12800];
static uint64_t fallback_frames[10];
#else
static aw_display display;
static uint8_t display_previous[AW_VIDEO_PAGE_BYTES];
#endif
static uint16_t displayed_pixels[AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT];
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
        displayed_pixels[(y + row) * AW_VIDEO_WIDTH + x + col] = palette[(b >> ((col & 1) ? 0 : 4)) & 15];
    }
    return true;
}
#endif

typedef struct {
    const char *path;
    uint8_t *store;
    uint32_t capacity, frames, checksum, music_events, sound_events, nonzero_samples, sample_count, peak_packet;
    uint64_t source_bytes, packet_bytes;
#ifdef AW_DISPLAY_ANALYZE
    uint64_t store_reads, store_read_bytes, store_writes, store_write_bytes;
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
#else
        aw_display_init(&display, display_previous);
#endif
    }
    display_part = h->audio->vm->part - AW_VM_FIRST_PART;
    assert(display_part < 10);
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
    assert(aw_display_compact_present(&compact, pixels, palette, display_rect, NULL));
    fallback_frames[display_part] += compact.external;
#else
    assert(aw_display_present(&display, pixels, palette, display_rect, NULL));
#endif
    ++display_frames[display_part];
    for (unsigned i = 0; i < AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT; ++i) {
        const uint8_t b = pixels[i / 2];
        assert(displayed_pixels[i] == palette[(b >> ((i & 1) ? 0 : 4)) & 15]);
    }
#endif
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) checksum = (checksum ^ pixels[i]) * 16777619u;
    for (unsigned i = 0; i < 16; ++i) checksum = (checksum ^ palette[i]) * 16777619u;
    h->checksum = checksum; ++h->frames; return true;
}
static bool frame_wait(void *ctx, unsigned slices) {
    host *h = ctx; int16_t samples[64]; uint8_t packet[512], output[72];
    unsigned remaining = slices * 500;
    while (remaining) {
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
int main(int argc, char **argv) {
    if (argc < 2 || argc > 3) { fprintf(stderr, "usage: %s DATA_DIR [WALK_STEPS]\n", argv[0]); return 2; }
    const unsigned limit = argc == 3 ? (unsigned)strtoul(argv[2], NULL, 10) : 5000;
    if (!limit || limit > 100000) return 2;
    char path[1024]; snprintf(path, sizeof(path), "%s/MEMLIST.BIN", argv[1]);
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); return 1; }
    uint8_t list[4096]; size_t len = fread(list, 1, sizeof(list), f); fclose(f);
    host h = {0}; h.path = argv[1]; h.capacity = 2u * 1024u * 1024u; h.store = calloc(1, h.capacity);
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
        !aw_assets_init(a, list, len, h.capacity, &h, bank_read, store_read, store_write) ||
        !aw_video_init(video, a, a->used, pixels, present, &h) ||
        (spare && !aw_video_use_spare(video, spare)) ||
        (background && !aw_video_use_background(video, background, 6144)) ||
#ifdef AW_VIDEO_PACKED3
        !aw_video_use_packed_page3(video, a->used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES) ||
#endif
        !aw_vm_init(vm, a, video, callbacks, 1)) {
        fprintf(stderr, "initialization failed\n"); return 1;
    }
    aw_audio_init(h.audio, a, vm); aw_audio_init(h.remote, a, vm);
    /* The probe starts after the protection part; seed the same variables
     * that Raw's BYPASS_PROTECTION test build initializes. */
    vm->vars[0xBC] = 0x10; vm->vars[0xC6] = 0x80; vm->vars[0xF2] = 4000; vm->vars[0xDC] = 33;
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
    for (unsigned i = 0; i < 10; ++i) if (display_frames[i])
        printf("compact part=%04X external_fallback_frames=%llu\n", AW_VM_FIRST_PART + i,
               (unsigned long long)fallback_frames[i]);
#endif
#endif
    free(h.remote); free(h.audio); free(vm); free(video); free(a); free(pixels); free(spare); free(background); free(h.store);
    return passed ? 0 : 1;
}
