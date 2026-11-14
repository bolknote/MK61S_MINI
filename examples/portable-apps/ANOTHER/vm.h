#ifndef MK61_ANOTHER_VM_H
#define MK61_ANOTHER_VM_H

#include "video.h"

#define AW_VM_THREADS 64u
#define AW_VM_FIRST_PART 0x3E80u
#define AW_VM_LAST_PART 0x3E89u

enum { AW_INPUT_LEFT = 1, AW_INPUT_RIGHT = 2, AW_INPUT_UP = 4, AW_INPUT_DOWN = 8 };
typedef struct {
    uint8_t directions, button, last_char;
    bool code, quit;
} aw_input;
typedef struct {
    void *ctx;
    bool (*frame_wait)(void *ctx, unsigned slices);
    void (*pump)(void *ctx);
    void (*sound)(void *ctx, unsigned id, unsigned freq, unsigned volume, unsigned channel);
    void (*music)(void *ctx, unsigned id, unsigned delay, unsigned position);
    void (*stop_audio)(void *ctx);
} aw_vm_host;
typedef struct {
    aw_assets *assets;
    aw_video *video;
    aw_vm_host host;
    int16_t vars[256];
    uint16_t pc[AW_VM_THREADS], requested_pc[AW_VM_THREADS], stack[64];
    uint8_t paused[AW_VM_THREADS], requested_pause[AW_VM_THREADS], loaded[AW_ASSET_LIMIT];
    uint16_t part, next_part, code_id, polygon_id, polygon2_id, palette_id;
    uint32_t cursor;
    uint8_t sp, palette_request;
    bool fault;
} aw_vm;

bool aw_vm_init(aw_vm *vm, aw_assets *assets, aw_video *video, aw_vm_host host, uint16_t seed);
bool aw_vm_set_part(aw_vm *vm, uint16_t part);
bool aw_vm_frame(aw_vm *vm, aw_input *input);

#endif
