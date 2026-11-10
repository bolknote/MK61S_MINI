#ifndef MK61_SPECTRUM_H
#define MK61_SPECTRUM_H
#include <stdbool.h>
#include <stdint.h>
#include "../../../third_party/z80/z80.h"
#include "../../../third_party/emu2149/emu2149.h"
#include "memory.h"
#include "peripherals.h"
#include "disk.h"

#define SPECTRUM_RAM_BYTES 49152U
#define SPECTRUM_ROM_BYTES 16384U
#define SPECTRUM_FRAME_TSTATES 69888U
#define SPECTRUM_BITMAP_BYTES 6144U
#define SPECTRUM_ATTRIBUTE_BYTES 768U

typedef struct spectrum {
    z80 cpu;
    uint8_t* ram;
    const uint8_t* rom;
    uint8_t keys[8],joystick,border,beeper;
    uint32_t frames,frame_tstates;
    spectrum_memory* memory; /* NULL: ordinary 48K; otherwise banked RAM. */
    bool pentagon;
    PSG ay;
    PSG ay2;
    spectrum_sound sound;
    spectrum_disk disk;
    uint8_t extensions,joystick_mode,sound_chip,sound_layout;
    uint8_t ulaplus_select,ulaplus_mode,ulaplus_palette[64];
    uint32_t sample_rate,sample_phase;
    int32_t audio_input,audio_output;
    void* audio_context;
    void (*audio_sample)(void*,int16_t);
} spectrum;
typedef struct {
    void* context;
    uint32_t size;
    bool (*read)(void*,uint32_t,uint8_t*,uint32_t);
} spectrum_source;
enum spectrum_error {
    SPECTRUM_OK, SPECTRUM_IO, SPECTRUM_FORMAT, SPECTRUM_UNSUPPORTED
};
void spectrum_init(spectrum*,uint8_t* ram,const uint8_t* rom);
void spectrum_reset(spectrum*);
void spectrum_set_audio(spectrum*,uint32_t rate,void (*sample)(void*,int16_t),void* context);
void spectrum_attach_memory(spectrum*,spectrum_memory*);
void spectrum_refresh_map(spectrum*);
uint32_t spectrum_frame_cycles(const spectrum*);
uint32_t spectrum_run(spectrum*,uint32_t tstates);
void spectrum_keyboard(spectrum*,const uint8_t wire_keys[32]);
uint8_t spectrum_port_in(spectrum*,uint16_t port);
void spectrum_video(const spectrum*,uint8_t bitmap[6144],uint8_t tiles[768]);
void spectrum_video8(const spectrum*,uint8_t bitmap[6144],uint8_t tiles[1536]);
uint16_t spectrum_color(unsigned index);
uint16_t spectrum_palette(const spectrum*,unsigned index);
uint16_t spectrum_border(const spectrum*);
/* 48K SNA and Z80 v1/v2/v3. File suffix selects the format; no heuristics.
 * A complete validation pass precedes all memory/register changes. An I/O
 * error during the commit pass requires a reset before resuming execution. */
enum spectrum_error spectrum_load_sna(spectrum*,const spectrum_source*);
enum spectrum_error spectrum_load_z80(spectrum*,const spectrum_source*);
#endif
