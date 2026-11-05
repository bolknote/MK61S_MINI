#ifndef MK61_SPECTRUM_UI_H
#define MK61_SPECTRUM_UI_H
#include "mk61_app.h"
#include "spectrum.h"
typedef struct {
    const mk61_app_services* api;
    const uint8_t* font;
    mk61_service_color_frame frame;
} spectrum_ui;
bool spectrum_ui_begin(spectrum_ui*,const mk61_app_services*,const spectrum*,bool running);
void spectrum_ui_window(spectrum_ui*,unsigned x,unsigned y,unsigned width,const char* title,
                        const char* const* labels,unsigned count,unsigned selected);
void spectrum_ui_footer(spectrum_ui*,const char* text);
bool spectrum_ui_present(spectrum_ui*);
#endif
