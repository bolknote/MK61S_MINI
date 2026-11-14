/* Exercise the original game data from boot through the level-code screen. */
#include "../examples/portable-apps/ANOTHER/vm.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STORE_SIZE (2u * 1024u * 1024u)
typedef struct {
    const char *directory;
    uint8_t *store, pixels[AW_VIDEO_PAGE_BYTES];
    unsigned frames;
} host;
static bool bank_read(void *ctx, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    host *h = ctx; char path[1024];
    if (snprintf(path, sizeof(path), "%s/BANK%02X", h->directory, bank) >= (int)sizeof(path)) return false;
    FILE *f = fopen(path, "rb"); if (!f) return false;
    bool ok = fseek(f, offset, SEEK_SET) == 0 && fread(out, 1, size, f) == size; fclose(f); return ok;
}
static bool store_read(void *ctx, uint32_t offset, void *out, uint32_t size) {
    host *h = ctx; if (offset > STORE_SIZE || size > STORE_SIZE - offset) return false;
    memcpy(out, h->store + offset, size); return true;
}
static bool store_write(void *ctx, uint32_t offset, const void *in, uint32_t size) {
    host *h = ctx; if (offset > STORE_SIZE || size > STORE_SIZE - offset) return false;
    memcpy(h->store + offset, in, size); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    host *h = ctx; (void)palette; memcpy(h->pixels, pixels, sizeof(h->pixels)); ++h->frames; return true;
}
static bool wait_frame(void *ctx, unsigned slices) { (void)ctx; (void)slices; return true; }

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s DATA_DIR\n", argv[0]); return 2; }
    char path[1024]; snprintf(path, sizeof(path), "%s/MEMLIST.BIN", argv[1]);
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); return 2; }
    uint8_t list[4096]; size_t size = fread(list, 1, sizeof(list), f); fclose(f);
    host *h = calloc(1, sizeof(*h)); aw_assets *assets = calloc(1, sizeof(*assets));
    aw_video *video = calloc(1, sizeof(*video)); aw_vm *vm = calloc(1, sizeof(*vm));
    uint8_t *pixels = malloc(AW_VIDEO_PAGE_BYTES); assert(h && assets && video && vm && pixels);
    h->directory = argv[1]; h->store = calloc(1, STORE_SIZE); assert(h->store);
    aw_vm_host hooks = {h, wait_frame, NULL, NULL, NULL, NULL};
    assert(aw_assets_init(assets, list, size, STORE_SIZE, h, bank_read, store_read, store_write));
    assert(aw_video_init(video, assets, assets->used, pixels, present, h));
    assert(aw_vm_init(vm, assets, video, hooks, 1)); assert(aw_vm_set_part(vm, AW_VM_FIRST_PART));
    aw_input input = {0};
    unsigned steps = 0;
    while (vm->part == AW_VM_FIRST_PART && steps++ < 2000) assert(aw_vm_frame(vm, &input));
    assert(vm->part == 0x3E81);
    input.code = true;
    const unsigned before = h->frames;
    for (unsigned i = 0; i < 80; ++i) assert(aw_vm_frame(vm, &input));
    assert(vm->part == AW_VM_LAST_PART && h->frames > before + 40);
    uint8_t before_input[AW_VIDEO_PAGE_BYTES]; memcpy(before_input, h->pixels, sizeof(before_input));
    for (const char *p = "ldkd"; *p; ++p) {
        input.last_char = (uint8_t)*p;
        for (unsigned i = 0; i < 20; ++i) assert(aw_vm_frame(vm, &input));
    }
    unsigned changed = 0;
    for (unsigned y = 80; y < 88; ++y)
        for (unsigned x = 184 / 2; x < 220 / 2; ++x)
            changed += before_input[y * AW_VIDEO_STRIDE + x] != h->pixels[y * AW_VIDEO_STRIDE + x];
    assert(changed > 10); /* Entered letters are rendered in the access-code field. */
    printf("Another World boot and level-code screen: %u steps, %u changed bytes\n", steps, changed);
    free(h->store); free(h); free(vm); free(video); free(assets); free(pixels); return 0;
}
