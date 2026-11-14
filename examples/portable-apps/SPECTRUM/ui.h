#ifndef MK61_SPECTRUM_UI_H
#define MK61_SPECTRUM_UI_H
#include "mk61_app.h"
#include "spectrum.h"
unsigned spectrum_video_mode(const spectrum*);
bool spectrum_video_strip(const spectrum*,unsigned mode,unsigned strip,uint8_t* pixels,mk61_service_color_frame*);
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
