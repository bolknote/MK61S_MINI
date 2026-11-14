#ifndef MK61_ANOTHER_AUDIO_H
#define MK61_ANOTHER_AUDIO_H
#include "vm.h"

#define AW_AUDIO_RATE 25000u
#define AW_AUDIO_BLOCK 120u

typedef struct {
    uint32_t data, position, increment;
    uint16_t length, loop, loop_length;
    uint8_t volume;
    bool active, zero_prefix;
} aw_audio_channel;
typedef struct {
    aw_assets *assets;
    aw_vm *vm;
    aw_audio_channel channels[4];
    uint16_t instruments[15], volumes[15];
    uint8_t orders[128], order, order_count;
    uint16_t resource, row, delay;
    uint32_t until_event;
    bool music_active, fault;
} aw_audio;

void aw_audio_init(aw_audio *a, aw_assets *assets, aw_vm *vm);
void aw_audio_stop(aw_audio *a);
void aw_audio_sound(aw_audio *a, unsigned id, unsigned frequency_index, unsigned volume, unsigned channel);
void aw_audio_music(aw_audio *a, unsigned id, unsigned delay, unsigned position);
bool aw_audio_render(aw_audio *a, int16_t *out, unsigned count);
/* Prepare an experimental M3 job, advancing the mixer/tracker by *frames.
 * The caller must preserve a snapshot until the remote result is accepted. */
bool aw_audio_prepare_m3(aw_audio *a, uint8_t *packet, unsigned capacity,
                         unsigned max_frames, unsigned gain, uint16_t sequence,
                         unsigned *frames, unsigned *bytes);

#endif
