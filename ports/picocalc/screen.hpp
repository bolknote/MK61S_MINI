#ifndef MK61_PICOCALC_SCREEN_HPP
#define MK61_PICOCALC_SCREEN_HPP

#include "calculator.hpp"
#include "ui.hpp"
#include "text_screen.hpp"
#include "calculator_face.hpp"
#include "battery.hpp"
#include "lcd_scroll.hpp"

namespace picocalc {
class Services;

class Screen {
public:
    static constexpr unsigned WIDTH = 320, HEIGHT = 320;
    static constexpr unsigned STRIDE = WIDTH / 8;
    static constexpr unsigned BYTES = STRIDE * HEIGHT;
    void render(const Snapshot& model, bool keyboard_online, const Ui* ui = nullptr, const Services* services = nullptr, BatteryStatus battery = {});
    void logical_frame(const Ui& ui, const Services& services, u8 out[1536]) const;
    const u8* data() const { return pixels_; }
    lcd::Region scroll_region() const { return scroll_region_; }
    bool pixel(unsigned x, unsigned y) const {
        return x < WIDTH && y < HEIGHT && (pixels_[y * STRIDE + x / 8] & (0x80U >> (x % 8)));
    }
private:
    u8 pixels_[BYTES] = {};
    text_screen::Grid face_grid_;
    u8 face_[calculator_face::FRAME_BYTES] = {};
    const Settings* font_settings_ = nullptr;
    BatteryStatus battery_;
    lcd::Region scroll_region_;
    u32 native_revision_ = 0;
    bool native_valid_ = false;
    void set_pixel(unsigned x, unsigned y);
    void text(unsigned x, unsigned y, const char* value, unsigned height = 14, unsigned right=WIDTH-8);
    void status_field(unsigned left, unsigned width, const char* value);
    void line(unsigned y);
    void bitmap(const u8* frame,unsigned width,unsigned height,unsigned left=0,unsigned top=0);
    void native_bitmap(const u8* frame);
    void calculator(const Snapshot& model, const Ui& ui);
};

} // namespace picocalc
#endif
