#ifndef MK61_PICOCALC_SCREEN_HPP
#define MK61_PICOCALC_SCREEN_HPP

#include "calculator.hpp"
#include "ui.hpp"
#include "text_screen.hpp"
#include "calculator_face.hpp"
#include "battery.hpp"
#include "lcd_scroll.hpp"
#include "shell_color.hpp"
#include "utility_scene.hpp"

namespace picocalc {
class Services;

class Screen {
public:
    Screen();
    static constexpr unsigned WIDTH = 320, HEIGHT = 320;
    static constexpr unsigned STRIDE = WIDTH / 8;
    static constexpr unsigned BYTES = STRIDE * HEIGHT;
    bool render(const Snapshot& model, bool keyboard_online, const Ui* ui = nullptr, const Services* services = nullptr, BatteryStatus battery = {});
    void invalidate() { key_valid_=native_valid_=false;present_pending_=true; }
    bool presentation_pending() const { return present_pending_; }
    void presented() { present_pending_=false; }
    u32 renders() const { return renders_; }
    u32 skipped() const { return skipped_; }
    u32 partial_renders() const { return partial_renders_; }
    void animation_tick(u32 now_ms,u32 reads=0,u32 writes=0) { animation_.tick(now_ms,reads,writes); }
    void begin_bootloader(u32 now_ms) { animation_.begin_bootloader(now_ms);invalidate(); }
    bool bootloader_pending() const { return animation_.bootloader_pending(); }
    bool bootloader_ready() const { return animation_.ready(); }
    bool bootloader_timed_out() const { return animation_.timed_out(); }
    void logical_frame(const Ui& ui, const Services& services, u8 out[1536]) const;
    const u8* data() const { return pixels_; }
    const lcd::ShellTheme& color_theme() const { return theme_; }
    lcd::Region scroll_region() const { return scroll_region_; }
    bool pixel(unsigned x, unsigned y) const {
        return x < WIDTH && y < HEIGHT && (pixels_[y * STRIDE + x / 8] & (0x80U >> (x % 8)));
    }
private:
    // Exact visible inputs, not a lossy hash of them. A probe is much cheaper
    // than clearing the raster, decoding glyphs and planning LCD windows.
    struct RenderKey {
        u8 bytes[1536]{};unsigned used=0,animation_at=0;bool overflow=false;
        void data(const void* value,unsigned size);
        void number(u32 value);
        void text(const char* value);
        bool same(const RenderKey& other) const;
        bool same_scene(const RenderKey& other) const;
    } key_;
    bool key_valid_=false;
    bool present_pending_=true;
    u32 renders_=0,skipped_=0,partial_renders_=0;
    RenderKey key(const Snapshot&,bool,const Ui&,const Services*,BatteryStatus) const;
    void paint(const Snapshot&,bool,const Ui*,const Services*,BatteryStatus);
    u8 pixels_[BYTES] = {};
    lcd::ShellTheme theme_{};
    u8 face_[calculator_face::FRAME_BYTES] = {};
    const Settings* font_settings_ = nullptr;
    BatteryStatus battery_;
    lcd::Region scroll_region_;
    u32 native_revision_ = 0;
    bool native_valid_ = false;
    utility::Animation animation_;
    utility::Mode utility_mode(const Ui&,const Services*) const;
    void utility_theme(utility::Mode,unsigned phase);
    void utility_page(utility::Mode,unsigned phase,const Ui&,const Services*);
    void utility_caption(unsigned top,const char*,unsigned height=16);
    void set_pixel(unsigned x, unsigned y);
    void clear_pixel(unsigned x, unsigned y);
    void fill_rect(unsigned x,unsigned y,unsigned width,unsigned height);
    void text(unsigned x, unsigned y, const char* value, unsigned height = 14, unsigned right=WIDTH-8, bool erase=false);
    unsigned text_width(const char* value,unsigned height) const;
    void text_center(unsigned left,unsigned width,unsigned top,const char* value,
                     unsigned height,bool inverse=false);
    void rounded_label(unsigned left,unsigned top,unsigned width,unsigned height);
    void header(const char* title,bool keyboard_online,const Snapshot* calculator=nullptr);
    void main_menu(const Ui& ui,bool keyboard_online);
    void settings_menu(const Ui& ui);
    void calculator_tabs(const Ui& ui);
    void status_field(unsigned left, unsigned width, const char* value);
    void line(unsigned y);
    void bitmap(const u8* frame,unsigned width,unsigned height,unsigned left=0,unsigned top=0);
    void native_bitmap(const u8* frame);
    void segment_row(unsigned left,unsigned top,const u8 masks[12]);
    void calculator(const Snapshot& model, const Ui& ui);
    void browser(const Services& services,bool keyboard_online);
};

} // namespace picocalc
#endif
