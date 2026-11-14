#include "../examples/portable-apps/ANOTHER/vm.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint8_t bank[256], *store; uint32_t size; unsigned frames; } memory;
static bool bank(void *ctx, uint8_t id, uint32_t at, void *out, uint32_t n) {
    memory *m = ctx; if (id != 1 || at > sizeof(m->bank) || n > sizeof(m->bank) - at) return false;
    memcpy(out, m->bank + at, n); return true;
}
static bool read_store(void *ctx, uint32_t at, void *out, uint32_t n) {
    memory *m = ctx; if (at > m->size || n > m->size - at) return false;
    memcpy(out, m->store + at, n); return true;
}
static bool write_store(void *ctx, uint32_t at, const void *in, uint32_t n) {
    memory *m = ctx; if (at > m->size || n > m->size - at) return false;
    memcpy(m->store + at, in, n); return true;
}
static bool present(void *ctx, const uint8_t *pixels, const uint16_t *palette) {
    memory *m = ctx; (void)palette; assert(pixels[0] == 0x55); ++m->frames; return true;
}
static void entry(uint8_t *p, unsigned offset, unsigned size) {
    p[7] = 1; p[11] = (uint8_t)offset; p[14] = p[18] = (uint8_t)(size >> 8);
    p[15] = p[19] = (uint8_t)size;
}
int main(void) {
    uint8_t list[128 * 20 + 1] = {0};
    entry(list + 0x7D * 20, 0, 32); entry(list + 0x7E * 20, 32, 27); entry(list + 0x7F * 20, 96, 1);
    list[128 * 20] = 0xFF;
    const uint8_t code[] = {
        0x00,1,0,2, 0x03,1,0,3, 0x08,1,0,21,
        0x0E,2,5, 0x0D,2, 0x0B,0,0, 0x10,2, 0x06, 0x11,
        0x00,2,0,7, 0x06, 0x11
    };
    /* Thread 1 starts at the second MOV instruction. */
    uint8_t program[sizeof(code)]; memcpy(program, code, sizeof(code)); program[11] = 24;
    memory m = {0}; m.size = 4096 + 4 * AW_VIDEO_PAGE_BYTES; m.store = calloc(1, m.size);
    uint8_t *frame = malloc(AW_VIDEO_PAGE_BYTES); aw_assets *a = calloc(1, sizeof(*a));
    aw_video *video = calloc(1, sizeof(*video)); aw_vm *vm = calloc(1, sizeof(*vm));
    assert(m.store && frame && a && video && vm);
    memcpy(m.bank + 32, program, sizeof(program));
    /* The declared code length must include both threads. */
    entry(list + 0x7E * 20, 32, sizeof(program));
    assert(aw_assets_init(a, list, sizeof(list), m.size, &m, bank, read_store, write_store));
    assert(aw_video_init(video, a, 4096, frame, present, &m));
    aw_vm_host hooks = {0};
    assert(aw_vm_init(vm, a, video, hooks, 123)); assert(aw_vm_set_part(vm, AW_VM_LAST_PART));
    aw_input input = {AW_INPUT_LEFT | AW_INPUT_UP, 1, 'a', false, false};
    assert(aw_vm_frame(vm, &input));
    assert(vm->vars[1] == 5 && vm->vars[2] == 0 && vm->vars[0xDA] == 'A');
    assert(vm->vars[0xFC] == -1 && vm->vars[0xFB] == -1 && vm->vars[0xFE] == (2 | 8 | 0x80));
    assert(m.frames == 1 && vm->requested_pc[1] == 24);
    assert(aw_vm_frame(vm, &input)); assert(vm->vars[2] == 7);
    assert(aw_vm_frame(vm, &input)); assert(vm->pc[0] == 0xFFFF && vm->pc[1] == 0xFFFF);
    free(vm); free(video); free(a); free(frame); free(m.store);
    puts("Another World VM tests passed"); return 0;
}
