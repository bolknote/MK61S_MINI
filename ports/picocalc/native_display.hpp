#ifndef MK61_PICOCALC_NATIVE_DISPLAY_HPP
#define MK61_PICOCALC_NATIVE_DISPLAY_HPP
#include "settings.hpp"
#include "loadable_app_services.h"
#include "usb_screen_surface.hpp"
#include <memory>
namespace picocalc {
// Native APPs use the same text/cursor/UI rasterizer as STM32 USB Screen.
// The application owns its logical surface; only complete frames are published.
class NativeDisplay {
public:
    explicit NativeDisplay(const Settings& settings,bool native=false);
    unsigned width() const { return native_?320:192; }
    unsigned height() const { return native_?320:64; }
    void settings(const Settings& settings);
    void flush();
    unsigned columns();
    unsigned rows();
    u32 clear();
    u32 write(unsigned x,unsigned y,const char* text,unsigned length);
    u32 call(u32 operation,u32 b,u32 c,void* payload);
    bool bitmap_begin();
    bool bitmap_present(const u8* frame,unsigned size);
    void bitmap_end();
    u32 revision() const { return revision_; }
private:
    void layout();
    bool load_text_font();
    bool put(u16 cp);
    void native_layout();
    void native_flush();
    void native_put(u16 cp);
    unsigned native_advance(u16 cp) const;
    unsigned native_measure(const char* text,unsigned length) const;
    u32 native_call(u32 operation,u32 b,u32 c,void* payload);
    bool native_=false,native_dirty_=true,native_cursor_=false,native_blink_=false,native_phase_=false;
    unsigned nx_=0,ny_=0,ncols_=32,nrows_=18,npitch_=18,ncell_=8,update_=0;
    u32 blink_at_=0,gutters_=0,tails_=0;
    u16 cells_[20][64]{};
    u8 pixels_[usb_screen::FRAME_BYTES]{};
    usb_screen::Surface surface_;
    Settings settings_;
    bool ui_=false,bitmap_=false;
    u32 font_revision_=0,ui_font_revision_=0,revision_=1,published_=0;
    std::unique_ptr<u8[]> font_bytes_;
    prepared_font::Face font_;
};
}
#endif
