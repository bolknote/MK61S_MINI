/* Optional lock-step comparison with the unmodified Raw interpreter. */
extern "C" {
#include "../examples/portable-apps/ANOTHER/vm.h"
}
#include "vm.h"
#include "resource.h"
#include "video.h"
#include "mixer.h"
#include "sfxplayer.h"
#include "sys.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static uint32_t checksum(const uint8_t *pixels, const uint16_t *palette) {
    uint32_t value = 2166136261u;
    for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) value = (value ^ pixels[i]) * 16777619u;
    for (unsigned i = 0; i < 16; ++i) value = (value ^ palette[i]) * 16777619u;
    return value;
}
struct ReferenceSystem : System {
    uint16_t colors[16] = {};
    std::vector<uint32_t> frames;
#ifdef AW_REFERENCE_DIRECT_LEVEL
    std::vector<std::vector<uint8_t>> pixel_frames, color_frames;
#endif
    void init(const char *) override { memset(&input, 0, sizeof(input)); }
    void destroy() override {}
    void setPalette(const uint8_t *p) override {
        for (unsigned i = 0; i < 16; ++i) {
            const unsigned r = p[2*i] & 15, g = p[2*i+1] >> 4, b = p[2*i+1] & 15;
            colors[i] = (uint16_t)((((r << 1) | (r >> 3)) << 11) |
                                  (((g << 2) | (g >> 2)) << 5) | ((b << 1) | (b >> 3)));
        }
    }
    void updateDisplay(const uint8_t *pixels) override {
        frames.push_back(checksum(pixels, colors));
#ifdef AW_REFERENCE_DIRECT_LEVEL
        pixel_frames.emplace_back(pixels, pixels + AW_VIDEO_PAGE_BYTES);
        const uint8_t *color = (const uint8_t *)colors;
        color_frames.emplace_back(color, color + sizeof(colors));
#endif
    }
    void processEvents() override {}
    void sleep(uint32_t) override {}
    uint32_t getTimeStamp() override { return 0; }
    void startAudio(AudioCallback, void *) override {}
    void stopAudio() override {}
    uint32_t getOutputSampleRate() override { return 25000; }
    int addTimer(uint32_t, TimerCallback, void *) override { return 1; }
    void removeTimer(int) override {}
    void *createMutex() override { return nullptr; }
    void destroyMutex(void *) override {}
    void lockMutex(void *) override {}
    void unlockMutex(void *) override {}
};
struct Host {
    const char *directory;
    uint8_t *memory;
    std::vector<uint32_t> frames;
#ifdef AW_REFERENCE_DIRECT_LEVEL
    std::vector<std::vector<uint8_t>> pixel_frames, color_frames;
#endif
};
static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    Host *h = (Host *)ctx; char path[1024];
    snprintf(path, sizeof(path), "%s/BANK%02X", h->directory, bank);
    FILE *f = fopen(path, "rb"); if (!f) return false;
    bool ok = fseek(f, offset, SEEK_SET) == 0 && fread(out, 1, size, f) == size;
    fclose(f); return ok;
}
static bool rd(void *ctx, uint32_t offset, void *out, uint32_t size) {
    if (offset > 2097152 || size > 2097152 - offset) return false;
    memcpy(out, ((Host *)ctx)->memory + offset, size); return true;
}
static bool wr(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    if (offset > 2097152 || size > 2097152 - offset) return false;
    memcpy(((Host *)ctx)->memory + offset, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    Host *h = (Host *)ctx;
    h->frames.push_back(checksum(pixels, palette));
#ifdef AW_REFERENCE_DIRECT_LEVEL
    h->pixel_frames.emplace_back(pixels, pixels + AW_VIDEO_PAGE_BYTES);
    const uint8_t *color = (const uint8_t *)palette;
    h->color_frames.emplace_back(color, color + 16 * sizeof(*palette));
#endif
    return true;
}
static bool frame_wait(void *, unsigned) { return true; }

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s DATA_DIR\n", argv[0]); return 2; }
    char path[1024]; snprintf(path, sizeof(path), "%s/MEMLIST.BIN", argv[1]);
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); return 1; }
    uint8_t list[4096]; size_t bytes = fread(list, 1, sizeof(list), f); fclose(f);
    Host host = {argv[1], (uint8_t *)calloc(1, 2097152), {}};
    uint8_t *pixels = (uint8_t *)calloc(1, AW_VIDEO_PAGE_BYTES);
    uint8_t *spare = nullptr;
    uint8_t *background = nullptr;
    uint8_t *background_tail = nullptr;
#ifdef AW_VIDEO_BACKGROUND
#ifdef AW_VIDEO_BACKGROUND_SPLIT
    background = (uint8_t *)calloc(1, 4096);
    background_tail = (uint8_t *)calloc(1, 2048);
    if (!background || !background_tail) return 1;
#else
    background = (uint8_t *)calloc(1, 6144);
    if (!background) return 1;
#endif
#endif
#ifdef AW_VIDEO_TWO_PAGES
    spare = (uint8_t *)calloc(1, AW_VIDEO_PAGE_BYTES);
    if (!spare) return 1;
#endif
    aw_assets *assets = (aw_assets *)calloc(1, sizeof(aw_assets));
    aw_video *video = (aw_video *)calloc(1, sizeof(aw_video));
    aw_vm *vm = (aw_vm *)calloc(1, sizeof(aw_vm));
    aw_vm_host hooks = {}; hooks.frame_wait = frame_wait;
    if (!host.memory || !pixels || !assets || !video || !vm ||
        !aw_assets_init(assets, list, bytes, 2097152, &host, bank_read, rd, wr) ||
        !aw_video_init(video, assets, assets->used, pixels, present, &host) ||
        (spare && !aw_video_use_spare(video, spare)) ||
        (background && !(background_tail ? aw_video_use_background_split(video, background, 4096, background_tail, 2048) :
                         aw_video_use_background(video, background, 6144))) ||
#ifdef AW_VIDEO_PACKED3
        !aw_video_use_packed_page3(video, assets->used + 5 * AW_VIDEO_PAGE_BYTES, AW_VIDEO_PAGE3_PACKED_BYTES) ||
#endif
        !aw_vm_init(vm, assets, video, hooks, 1)) return 1;
    vm->vars[0xBC] = 0x10; vm->vars[0xC6] = 0x80; vm->vars[0xF2] = 4000; vm->vars[0xDC] = 33;
#ifdef AW_REFERENCE_DIRECT_LEVEL
    constexpr uint16_t first_part = 0x3E82; constexpr unsigned limit = 500, input_start = 0;
#else
    constexpr uint16_t first_part = 0x3E81; constexpr unsigned limit = 5000, input_start = 2610;
#endif
    if (!aw_vm_set_part(vm, first_part)) return 1;
    ReferenceSystem sys; sys.init("");
    Video raw_video(nullptr, &sys); Resource raw_res(&raw_video, argv[1]); raw_video.res = &raw_res;
    Mixer mixer(&sys); SfxPlayer player(&mixer, &raw_res, &sys);
    VirtualMachine raw_vm(&mixer, &raw_res, &player, &raw_video, &sys);
    raw_video.init(); raw_res.allocMemBlock(); raw_res.readEntries();
    raw_vm.init(); raw_vm.vmVariables[0x3C] = 1;
    raw_vm.vmVariables[0xBC] = 0x10; raw_vm.vmVariables[0xC6] = 0x80;
    raw_vm.vmVariables[0xF2] = 4000; raw_vm.vmVariables[0xDC] = 33;
    mixer.init(); player.init(); raw_vm.initForPart(first_part);
    aw_input input = {};
    size_t compared = 0;
    for (unsigned n = 0; n < limit; ++n) {
        if (n >= input_start) {
            const unsigned phase = (n - input_start) % 360;
            input.directions = phase < 120 ? AW_INPUT_RIGHT : phase < 240 ? AW_INPUT_LEFT : AW_INPUT_UP;
            input.button = (phase % 80) < 16;
            sys.input.dirMask = input.directions; sys.input.button = input.button;
        }
        if (!aw_vm_frame(vm, &input)) { fprintf(stderr, "our VM failed at frame %u\n", n); return 1; }
        raw_vm.checkThreadRequests(); raw_vm.inp_updatePlayer(); raw_vm.hostFrame();
        if (host.frames.size() != sys.frames.size()) {
            fprintf(stderr, "display count mismatch at step %u: %zu vs %zu\n", n, host.frames.size(), sys.frames.size()); return 1;
        }
        while (compared < host.frames.size()) {
            if (host.frames[compared] != sys.frames[compared]
#ifdef AW_REFERENCE_DIRECT_LEVEL
                || host.pixel_frames[compared] != sys.pixel_frames[compared]
                || host.color_frames[compared] != sys.color_frames[compared]
#endif
            ) {
                fprintf(stderr, "frame %zu differs at step %u: %08X vs %08X\n", compared, n,
                        host.frames[compared], sys.frames[compared]); return 1;
            }
            ++compared;
        }
        if (vm->part != raw_res.currentPartId) {
            fprintf(stderr, "part mismatch at step %u\n", n); return 1;
        }
        for (unsigned i = 0; i < 256; ++i) if (vm->vars[i] != raw_vm.vmVariables[i]) {
            fprintf(stderr, "variable %02X differs at step %u: %d vs %d\n", i, n,
                    vm->vars[i], raw_vm.vmVariables[i]); return 1;
        }
    }
#ifdef AW_REFERENCE_DIRECT_LEVEL
    unsigned changes = 0; for (size_t i = 1; i < host.frames.size(); ++i) changes += host.frames[i] != host.frames[i-1];
    printf("%zu display frames match Raw byte-for-byte; %u frame changes\n", compared, changes);
    const bool passed = compared >= 400 && changes >= 100 && vm->part == 0x3E82;
#else
    printf("%zu display frames match Raw\n", compared);
    const bool passed = compared >= 4000 && vm->part >= 0x3E82;
#endif
    player.free(); mixer.free(); raw_res.freeMemBlock(); free(raw_video._pages[0]);
    free(vm); free(video); free(assets); free(pixels); free(spare); free(background); free(background_tail); free(host.memory);
    return passed ? 0 : 1;
}
