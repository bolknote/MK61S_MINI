#ifndef MK61_SPECTRUM_UI_H
#define MK61_SPECTRUM_UI_H
#include "mk61_app.h"
#include "spectrum.h"
enum { SPECTRUM_VIDEO_WORK_BYTES=10240 };
typedef struct {
    const spectrum_memory_io* io;
    uint32_t address,frames;
#if SPECTRUM_HAS_PENTAGON
    uint32_t previous,previous_frames;
#endif
    uint16_t border;
    bool ulaplus;
    uint16_t palette[64];
} spectrum_video_snapshot;
unsigned spectrum_video_mode(const spectrum*);
bool spectrum_video_strip(const spectrum*,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame*);
bool spectrum_video_capture(const spectrum*,unsigned mode,uint8_t* work,spectrum_video_snapshot*);
bool spectrum_video_snapshot_strip(const spectrum*,const spectrum_video_snapshot*,unsigned mode,unsigned strip,
                                   uint8_t* pixels,mk61_service_color_frame*);
void spectrum_hicolor_flash(const spectrum*,spectrum_hicolor_changes*);
void spectrum_timex_patch(const spectrum*,const spectrum_video_snapshot*,unsigned mode,unsigned strip,
                          const spectrum_video_damage*,uint8_t* pixels);
void spectrum_timex_frame(const spectrum_video_snapshot*,unsigned mode,unsigned strip,
                          const spectrum_video_damage*,uint8_t* pixels,mk61_service_color_frame*);
// Column interval that can be omitted between two dirty regions in a Wide strip.
typedef struct { uint8_t left,right; } spectrum_wide_gap;
bool spectrum_pentagon_flash(const spectrum*,uint8_t* work,spectrum_video_damage strips[SPECTRUM_WIDE_STRIPS],
                             spectrum_wide_gap gaps[SPECTRUM_WIDE_STRIPS]);
void spectrum_pentagon_wide_window(mk61_service_color_frame*,const spectrum_wide_gap*,bool right,uint8_t* pixels);
bool spectrum_pentagon_patch(const spectrum*,unsigned mode,unsigned strip,const spectrum_video_damage*,
                            uint8_t* pixels,uint32_t wide_reference);
void spectrum_pentagon_frame(unsigned mode,unsigned strip,const spectrum_video_damage*,const uint8_t*,
                             mk61_service_color_frame*);
void spectrum_pentagon_clip(unsigned mode,const spectrum_video_damage*,uint8_t*,mk61_service_color_frame*);
typedef struct {
    const mk61_app_services* api;
    const uint8_t* font;
    mk61_service_color_frame frame;
} spectrum_ui;
static inline void spectrum_display_fast(const mk61_app_services* api) {
    uint32_t hz=24000000;
    /* Optional on older firmware; the display remains usable at its default.
     * The host restores its clock on COLOR_END or any APP return. */
    (void)api->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_SPI_HZ,0,sizeof(hz),&hz);
}
bool spectrum_ui_begin(spectrum_ui*,const mk61_app_services*,const spectrum*,bool running);
void spectrum_ui_window(spectrum_ui*,unsigned x,unsigned y,unsigned width,const char* title,
                        const char* const* labels,unsigned count,unsigned selected);
void spectrum_ui_footer(spectrum_ui*,const char* text);
bool spectrum_ui_present(spectrum_ui*);
#endif
