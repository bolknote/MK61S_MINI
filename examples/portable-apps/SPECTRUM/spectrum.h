#ifndef MK61_SPECTRUM_H
#define MK61_SPECTRUM_H
#include <stdbool.h>
#include <stdint.h>
#include "../../../third_party/z80/z80.h"
#include "../../../third_party/emu2149/emu2149.h"
#include "memory.h"
#include "peripherals.h"
#include "disk.h"

#ifndef SPECTRUM_APP_PROFILE
#define SPECTRUM_APP_PROFILE 0
#endif
#define SPECTRUM_HAS_SINCLAIR (SPECTRUM_APP_PROFILE!=1 && SPECTRUM_APP_PROFILE!=3 && SPECTRUM_APP_PROFILE!=7)
#define SPECTRUM_HAS_PENTAGON (SPECTRUM_APP_PROFILE==0 || SPECTRUM_APP_PROFILE==1 || SPECTRUM_APP_PROFILE==3 || SPECTRUM_APP_PROFILE==7)
#define SPECTRUM_HAS_FAST_VIDEO (SPECTRUM_APP_PROFILE==0 || (SPECTRUM_APP_PROFILE>=3 && SPECTRUM_APP_PROFILE<=5))
#define SPECTRUM_HAS_EXTENDED_VIDEO (SPECTRUM_HAS_FAST_VIDEO || SPECTRUM_APP_PROFILE>=7)
#define SPECTRUM_HAS_PREFERENCES (SPECTRUM_APP_PROFILE<3)
#define SPECTRUM_HAS_TIMEX (SPECTRUM_HAS_SINCLAIR && SPECTRUM_HAS_EXTENDED_VIDEO)
#define SPECTRUM_HAS_TIMEX_2068 (SPECTRUM_APP_PROFILE==5)
#define SPECTRUM_HAS_PENTAGON_VIDEO (SPECTRUM_HAS_PENTAGON && SPECTRUM_HAS_EXTENDED_VIDEO)
#define SPECTRUM_HAS_RASTER (SPECTRUM_APP_PROFILE==0 || SPECTRUM_APP_PROFILE==2)
#define SPECTRUM_HAS_BEAM_VIDEO (SPECTRUM_HAS_TIMEX_2068 || SPECTRUM_APP_PROFILE>=7)
#define SPECTRUM_RASTER_ENABLED (SPECTRUM_HAS_RASTER || SPECTRUM_HAS_BEAM_VIDEO)
#define SPECTRUM_HAS_TAPE_RECORD (SPECTRUM_APP_PROFILE<=1 || SPECTRUM_HAS_TIMEX_2068 || SPECTRUM_APP_PROFILE==6)

#define SPECTRUM_RAM_BYTES 49152U
#define SPECTRUM_ROM_BYTES 16384U
#define SPECTRUM_FRAME_TSTATES 69888U
#define SPECTRUM_128_FRAME_TSTATES 70908U
#define SPECTRUM_128_CPU_HZ 3546900U
#define SPECTRUM_128_AY_HZ 1773400U
#define SPECTRUM_TS2068_FRAME_TSTATES (262U*224U)
#define SPECTRUM_TS2068_CPU_HZ 3528000U
#define SPECTRUM_TS2068_AY_HZ 1764000U
#define SPECTRUM_BITMAP_BYTES 6144U
#define SPECTRUM_ATTRIBUTE_BYTES 768U
#define SPECTRUM_RASTER_STRIP_ROWS 32U
#define SPECTRUM_RASTER_STRIPS 8U
#define SPECTRUM_RASTER_CELLS (40U*SPECTRUM_RASTER_STRIP_ROWS)
#define SPECTRUM_RASTER_STRIP_BYTES (5U*SPECTRUM_RASTER_CELLS)
#define SPECTRUM_RASTER_BYTES (SPECTRUM_RASTER_STRIP_BYTES*SPECTRUM_RASTER_STRIPS)
#define SPECTRUM_RASTER_PACKED_STRIP_BYTES (3U*SPECTRUM_RASTER_CELLS+SPECTRUM_RASTER_CELLS/8U)
#define SPECTRUM_RASTER_PACKED_BYTES (SPECTRUM_RASTER_PACKED_STRIP_BYTES*SPECTRUM_RASTER_STRIPS)

enum { SPECTRUM_VIDEO_16C=1, SPECTRUM_VIDEO_HICOLOR=2, SPECTRUM_VIDEO_HIRES=6, SPECTRUM_VIDEO_WIDE=64 };
enum { SPECTRUM_WIDE_WIDTH=320, SPECTRUM_WIDE_HEIGHT=304,
       SPECTRUM_WIDE_STRIP_ROWS=48, SPECTRUM_WIDE_STRIPS=7 };
enum { SPECTRUM_BEAM_ROWS=16, SPECTRUM_BEAM_FRAME_BYTES=SPECTRUM_HAS_PENTAGON?
       SPECTRUM_WIDE_WIDTH*SPECTRUM_WIDE_HEIGHT/2:4*32*192 };
static inline unsigned spectrum_beam_width(unsigned mode) { return mode==SPECTRUM_VIDEO_16C?256:320; }
static inline unsigned spectrum_beam_height(unsigned mode) { return mode==SPECTRUM_VIDEO_WIDE?304:192; }
static inline unsigned spectrum_beam_row_bytes(unsigned mode) {
    return SPECTRUM_HAS_PENTAGON?spectrum_beam_width(mode)/2:4*32;
}
typedef struct { uint8_t left,right,top,bottom; } spectrum_video_damage;
typedef struct {
    spectrum_video_damage strips[3];
    uint8_t windows;
    bool repaint;
} spectrum_hicolor_changes;
typedef struct {
    spectrum_video_damage strips[2][SPECTRUM_WIDE_STRIPS];
    uint8_t mode,bank,upper,windows,repaint;
} spectrum_pentagon_changes;
#if SPECTRUM_HAS_TIMEX_2068
enum { SPECTRUM_TIMEX_DOCK, SPECTRUM_TIMEX_EXROM, SPECTRUM_TIMEX_CHUNK_BYTES=8192 };
typedef struct {
    uint8_t present[2],writable[2],slot;
} spectrum_cartridge;
#endif
static inline void spectrum_video_include_cell(spectrum_video_damage* d,unsigned x,unsigned y,unsigned rows) {
    if(!d->bottom) {*d=(spectrum_video_damage){x,x+1,y,y+rows};return;}
    if(x<d->left) d->left=(uint8_t)x;
    if(x>=d->right) d->right=(uint8_t)(x+1);
    if(y<d->top) d->top=(uint8_t)y;
    if(y+rows>d->bottom) d->bottom=(uint8_t)(y+rows);
}

typedef struct spectrum {
    z80 cpu;
    uint8_t* ram;
    const uint8_t* rom;
    uint8_t keys[8],joystick,border,beeper,key_rows;
    uint32_t frames,frame_tstates,frame_origin;
#if SPECTRUM_HAS_TIMEX_2068
    uint32_t contention_origin;
#endif
    spectrum_memory* memory; /* NULL: ordinary 48K; otherwise banked RAM. */
    bool pentagon;
    PSG ay;
    PSG ay2;
    spectrum_sound sound;
    spectrum_disk disk;
    void* ear_context;
    bool (*ear)(void*,const z80*);
#if SPECTRUM_HAS_TAPE_RECORD
    void* mic_context;
    void (*mic)(void*,uint32_t,bool);
#endif
    void* video_context;
    uint8_t* video_bytes;
    bool (*video_store)(void*,unsigned,const uint8_t*);
    spectrum_hicolor_changes* hicolor;
#if SPECTRUM_HAS_PENTAGON
    spectrum_pentagon_changes* pentagon_video;
#endif
    uint16_t video_cell;
#if SPECTRUM_HAS_BEAM_VIDEO
    uint8_t beam_mode;
    bool beam_geometry_changed,beam_io;
#endif
    uint8_t extensions,joystick_mode,sound_chip,sound_layout;
    uint8_t ulaplus_select,ulaplus_mode,timex_mode,ulaplus_palette[64];
#if SPECTRUM_HAS_TIMEX_2068
    spectrum_cartridge cartridge;
    uint8_t timex_hsr;
    bool timex_ntsc;
#endif
    uint32_t sample_rate,sample_phase;
    int32_t audio_input,audio_output;
    void* audio_context;
    void (*audio_sample)(void*,int16_t);
} spectrum;
enum { SPECTRUM_48, SPECTRUM_P512, SPECTRUM_P1024, SPECTRUM_128, SPECTRUM_TC2048, SPECTRUM_TC2068, SPECTRUM_TS2068 };
static inline bool spectrum_is_128(const spectrum* s) {
    return SPECTRUM_HAS_SINCLAIR && !SPECTRUM_HAS_TIMEX_2068 && s->memory && s->memory->banks==8;
}
static inline bool spectrum_is_pentagon(const spectrum* s) {
    return SPECTRUM_APP_PROFILE==1 || (SPECTRUM_HAS_PENTAGON && s->pentagon);
}
static inline unsigned spectrum_model(const spectrum* s) {
#if SPECTRUM_HAS_TIMEX_2068
    return s->timex_ntsc?SPECTRUM_TS2068:SPECTRUM_TC2068;
#else
    return spectrum_is_pentagon(s)?(s->memory && s->memory->extended?SPECTRUM_P1024:SPECTRUM_P512):
        spectrum_is_128(s)?SPECTRUM_128:SPECTRUM_48;
#endif
}
static inline bool spectrum_timex_2068(unsigned model) { return model==SPECTRUM_TC2068 || model==SPECTRUM_TS2068; }
static inline unsigned spectrum_cpu_clock(unsigned model) {
    return model==SPECTRUM_TS2068?SPECTRUM_TS2068_CPU_HZ:model==SPECTRUM_128?SPECTRUM_128_CPU_HZ:3500000;
}
static inline unsigned spectrum_ay_clock(const spectrum* s) {
    return spectrum_model(s)==SPECTRUM_TS2068?SPECTRUM_TS2068_AY_HZ:spectrum_is_128(s)?SPECTRUM_128_AY_HZ:1750000;
}
static inline unsigned spectrum_timex_mode(const spectrum* s) {
    return SPECTRUM_HAS_TIMEX && (s->extensions&SPECTRUM_TIMEX)?s->timex_mode&7:0;
}
static inline bool spectrum_timex_supported(unsigned port) {
    const unsigned mode=port&7;
    return mode<=SPECTRUM_VIDEO_HICOLOR || mode==SPECTRUM_VIDEO_HIRES;
}
static inline unsigned spectrum_pentagon_video_mode(const spectrum* s) {
    const unsigned mode=SPECTRUM_HAS_PENTAGON_VIDEO && s->memory && s->memory->extended?s->memory->control&0x41:0;
    return mode&1?SPECTRUM_VIDEO_16C:mode;
}
typedef struct {
    void* context;
    uint32_t size;
    bool (*read)(void*,uint32_t,uint8_t*,uint32_t);
} spectrum_source;
enum spectrum_error {
    SPECTRUM_OK, SPECTRUM_IO, SPECTRUM_FORMAT, SPECTRUM_UNSUPPORTED, SPECTRUM_MEDIA
};
#if SPECTRUM_HAS_TIMEX_2068
void spectrum_timex_map(spectrum*);
bool spectrum_timex_access(spectrum*,uint16_t address,bool writing,uint8_t*);
spectrum_cartridge spectrum_timex_stage(spectrum*);
uint32_t spectrum_timex_chunk(const spectrum_cartridge*,unsigned bank,unsigned chunk);
enum spectrum_error spectrum_load_dck(spectrum*,const spectrum_source*);
#endif
void spectrum_init(spectrum*,uint8_t* ram,const uint8_t* rom);
void spectrum_reset(spectrum*);
void spectrum_reset_cpu(spectrum*);
void spectrum_set_audio(spectrum*,uint32_t rate,void (*sample)(void*,int16_t),void* context);
void spectrum_attach_memory(spectrum*,spectrum_memory*);
void spectrum_refresh_map(spectrum*);
void spectrum_hicolor_watch(spectrum*,spectrum_hicolor_changes*);
void spectrum_hicolor_dirty(spectrum_hicolor_changes*,unsigned offset);
void spectrum_pentagon_watch(spectrum*,spectrum_pentagon_changes*);
uint32_t spectrum_frame_cycles(const spectrum*);
uint32_t spectrum_run(spectrum*,uint32_t tstates);
void spectrum_raster_begin(spectrum*,uint8_t*,void*,bool (*)(void*,unsigned,const uint8_t*));
#if SPECTRUM_HAS_BEAM_VIDEO
void spectrum_beam_begin(spectrum*,unsigned,uint8_t*,void*,bool (*)(void*,unsigned,const uint8_t*));
bool spectrum_beam_span(const spectrum*,unsigned mode,unsigned row,unsigned first,unsigned last,uint8_t* pixels);
#if SPECTRUM_HAS_TIMEX
void spectrum_timex_beam_expand(uint8_t* pixels,unsigned rows);
#endif
#endif
void spectrum_raster_end(spectrum*);
/* Expand a stored strip in a SPECTRUM_RASTER_STRIP_BYTES buffer for LCD. */
void spectrum_raster_expand(uint8_t*);
void spectrum_keyboard(spectrum*,const uint8_t wire_keys[32]);
uint8_t spectrum_port_in(spectrum*,uint16_t port);
void spectrum_video(const spectrum*,uint8_t bitmap[6144],uint8_t tiles[768]);
void spectrum_video8(const spectrum*,uint8_t bitmap[6144],uint8_t tiles[1536]);
uint16_t spectrum_color(unsigned index);
uint16_t spectrum_ulaplus_color(unsigned grb);
uint16_t spectrum_palette(const spectrum*,unsigned index);
uint16_t spectrum_border(const spectrum*);
/* 48K SNA and Z80 v1/v2/v3. File suffix selects the format; no heuristics.
 * A complete validation pass precedes all memory/register changes. An I/O
 * error during the commit pass requires a reset before resuming execution. */
enum spectrum_error spectrum_load_sna(spectrum*,const spectrum_source*);
enum spectrum_error spectrum_load_z80(spectrum*,const spectrum_source*);
enum spectrum_error spectrum_z80_model(const spectrum_source*,unsigned*);
#endif
