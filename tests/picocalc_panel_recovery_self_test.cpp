// HOST-only controller boundary. Panel::flush/transfer are included verbatim
// from production hardware.cpp by picocalc_panel_recovery_self_test.py.
#include "rust_types.h"
#include "lcd_scroll.hpp"
#include "diagnostics.hpp"
#include <array>
#include <atomic>
#include <cstring>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

// Drawing is outside this test: supply already-rendered LCD rows while using
// the actual Panel class, Scroll and Update rather than a mirrored driver.
#define MK61_PICOCALC_SCREEN_HPP
namespace picocalc {
struct KeyEvent;
class Screen {
public:
    static constexpr unsigned WIDTH=lcd::WIDTH, HEIGHT=lcd::HEIGHT, BYTES=lcd::BYTES;
    std::array<u8,BYTES> pixels{};
    lcd::Region region{};
    const u8* data() const { return pixels.data(); }
    lcd::Region scroll_region() const { return region; }
};
}
#define private public
#include "hardware.hpp"
#undef private

namespace picocalc {
namespace {
void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
struct Command { u8 op;std::vector<u8> data; };
struct Controller {
    std::array<u8,lcd::BYTES> gram{};
    std::vector<Command> commands;
    lcd::Region region{0,lcd::HEIGHT};
    unsigned origin=0,x0=0,x1=319,y0=0,y1=319,cursor=0;
    bool pending=false,fail_completion=false;
    void* context=nullptr;
    void (*transfer)(void*)=nullptr;
    unsigned word(const u8* data) { return ((unsigned)data[0]<<8)|data[1]; }
    void command(u8 op,const u8* data,unsigned count) {
        commands.push_back({op,count?std::vector<u8>(data,data+count):std::vector<u8>{}});
        if(op==0x33) {
            require(count==6,"VSCRDEF length");
            region={(u16)word(data),(u16)word(data+2)};
            require(region.valid() && region.top+region.height+word(data+4)==lcd::HEIGHT,"VSCRDEF geometry");
        } else if(op==0x37) {
            require(count==2,"VSCSAD length");origin=word(data);
        } else if(op==0x2A) {
            require(count==4,"CASET length");x0=word(data);x1=word(data+2);
        } else if(op==0x2B) {
            require(count==4,"PASET length");y0=word(data);y1=word(data+2);
        } else require(false,"unexpected controller command");
    }
    void pixels(const u16* source,unsigned count) {
        const unsigned width=x1-x0+1;
        require(x0<=x1 && x1<lcd::WIDTH && y0<=y1 && y1<lcd::HEIGHT,"bounded LCD window");
        require(cursor+count<=width*(y1-y0+1),"bounded pixel payload");
        for(unsigned i=0;i<count;++i,++cursor) {
            const unsigned x=x0+cursor%width,y=y0+cursor/width;
            const u8 bit=(u8)(0x80U>>(x%8));
            require(source[i]==0 || source[i]==0xFFFF,"black/white RGB565");
            auto& target=gram[y*lcd::STRIDE+x/8];
            target=source[i]?(u8)(target|bit):(u8)(target&~bit);
        }
    }
    bool visible(const Screen& expected) const {
        if(origin<region.top || origin>=region.top+region.height) return false;
        for(unsigned y=0;y<lcd::HEIGHT;++y) {
            const unsigned physical=y<region.top || y>=region.top+region.height?y:
                region.top+(y-region.top+origin-region.top)%region.height;
            if(std::memcmp(expected.data()+y*lcd::STRIDE,gram.data()+physical*lcd::STRIDE,lcd::STRIDE)) return false;
        }
        return true;
    }
    unsigned count(u8 op) const {
        unsigned n=0;for(const auto& c:commands) n+=c.op==op;return n;
    }
    void run() {
        require(pending && transfer,"queued actual Panel transfer");
        transfer(context);pending=false;
    }
} controller;
constexpr unsigned DC=0,CS=1;
constexpr int SPI_CPOL_0=0,SPI_CPHA_0=0,SPI_MSB_FIRST=0;
int spi1=1;
u16 scanlines[lcd::STRIP_ROWS*lcd::WIDTH]{};
u64 time_us_64() { static u64 now=0;return ++now; }
void busy_wait_us(unsigned) {}
void gpio_put(unsigned,bool) {}
void spi_set_format(int,unsigned,int,int,int) {}
int spi_write_blocking(int,const u8* bytes,unsigned count) {
    require(count==1 && bytes[0]==0x2C,"RAMWR command");controller.cursor=0;return 1;
}
void command(u8 op,const u8* data=nullptr,unsigned size=0) { controller.command(op,data,size); }
}
namespace diagnostics {
Scope::Scope(Point point):point_(point),start_(0),generation_(0) {}
Scope::~Scope() { (void)point_;(void)start_;(void)generation_; }
}
namespace io_worker {
bool frame_pending() { return controller.pending; }
bool submit_frame(void* context,void (*transfer)(void*)) {
    require(!controller.pending,"single in-flight frame");
    controller.context=context;controller.transfer=transfer;controller.pending=true;return true;
}
void service() {}
}
namespace dma_support {
u32 crc32(const u8* bytes,unsigned size) {
    u32 result=0;for(unsigned i=0;i<size;++i) result=result*33U+bytes[i];return result;
}
}
void Panel::start_scanline(const u16* pixels,unsigned count) { controller.pixels(pixels,count); }
bool Panel::finish_scanline() {
    if(controller.fail_completion) { controller.fail_completion=false;return false; }
    return true;
}
bool Panel::transfer_chain(const lcd::Rect&,u32&,u64&) {
    require(false,"this host fixture uses the ordinary scanline completion boundary");return false;
}

#include "picocalc_panel_production.inc"
}

namespace {
using namespace picocalc;
u32 random_word=0x239A14B7;
u8 byte() { random_word^=random_word<<13;random_word^=random_word>>17;random_word^=random_word<<5;return (u8)random_word; }
Screen shifted(const Screen& before,int delta) {
    Screen next=before;
    for(unsigned y=0;y<before.region.height;++y) {
        const int source=(int)y+delta;
        for(unsigned x=0;x<lcd::STRIDE;++x)
            next.pixels[(before.region.top+y)*lcd::STRIDE+x]=source>=0 && source<before.region.height?
                before.pixels[(before.region.top+source)*lcd::STRIDE+x]:byte();
    }
    return next;
}
void recovery(lcd::Region region,bool fail_first) {
    controller=Controller{};Panel panel;Screen frame;frame.region=region;
    for(auto& value:frame.pixels) value=byte();
    panel.flush(frame);controller.run();require(controller.visible(frame),"initial exact frame");
    if(fail_first) {
        frame=shifted(frame,16);controller.commands.clear();controller.fail_completion=true;
        panel.flush(frame);controller.run();
        require(controller.count(0x33)==1 && controller.count(0x37)==0 && panel.errors()==1,
                "fault must follow first VSCRDEF and precede VSCSAD");
        controller.commands.clear();panel.flush(frame);
        require(panel.update_.count==1 && panel.update_.bytes==lcd::WIDTH*lcd::HEIGHT*2,"full recovery frame");
        controller.run();
        if(controller.count(0x33)!=1 || controller.count(0x37)!=1) {
            std::fprintf(stderr,"Partial-region recovery top=%u height=%u: VSCRDEF=%u VSCSAD=%u origin=%u expected=%u\n",
                         region.top,region.height,controller.count(0x33),controller.count(0x37),controller.origin,region.top);
            require(false,"recovery must explicitly restore scroll definition and zero-offset origin");
        }
        require(controller.region==region && controller.origin==region.top && panel.scroll_offset()==0,
                "partial zero-offset origin includes fixed top");
        require(controller.visible(frame),"all recovery pixels and fixed header/footer exact");
    }
    unsigned offset=0,steps=0;bool forward_wrap=false,backward_wrap=false;
    for(int delta:{61,61,61,61,61,61,-47,-47,-47,-47,-47,-47}) {
        const unsigned before=offset;
        offset=(offset+(delta%(int)region.height+region.height)%region.height)%region.height;
        forward_wrap|=delta>0 && offset<before;backward_wrap|=delta<0 && offset>before;
        frame=shifted(frame,delta);controller.commands.clear();panel.flush(frame);controller.run();
        require(controller.region==region && controller.origin==region.top+offset && panel.scroll_offset()==offset,
                "successful scroll maps absolute controller origin");
        require(controller.visible(frame),"successful bidirectional wrapping frame exact");++steps;
    }
    require(forward_wrap && backward_wrap,"fixture exercises both wrap directions");
    require(panel.scroll_offset()!=0,"configured-region fault starts from nonzero offset");
    frame.region=region.top==42?lcd::Region{40,240}:lcd::Region{42,238};frame.pixels[0]^=1;
    const auto previous_errors=panel.errors();
    controller.commands.clear();controller.fail_completion=true;panel.flush(frame);controller.run();
    require(controller.count(0x33)==1 && controller.count(0x37)==0 && panel.errors()==previous_errors+1,
            "region-switch fault follows VSCRDEF and precedes VSCSAD");
    require(controller.region==frame.region,"fault actually changed controller region");
    controller.commands.clear();panel.flush(frame);
    require(panel.update_.count==1 && panel.update_.bytes==lcd::WIDTH*lcd::HEIGHT*2,
            "configured-region failure forces full retry");
    controller.run();
    require(controller.count(0x33)==1 && controller.count(0x37)==1,
            "configured-region retry restores definition and origin explicitly");
    require(controller.region==frame.region && controller.origin==frame.region.top && panel.scroll_offset()==0,
            "region switch resets absolute origin");
    require(controller.visible(frame),"region-switch full redraw exact");
    frame.region={};frame.pixels[1]^=1;panel.flush(frame);controller.run();
    require(controller.region==lcd::Region{0,320} && controller.origin==0 && controller.visible(frame),
            "leaving scroll view restores ordinary full-screen mapping");
    std::printf("Panel actual flush/transfer: top=%u height=%u first_failure_recovery=%u scrolls=%u both_wraps configured_region_failure_retry fixed_pixels PASS\n",
                region.top,region.height,fail_first?1U:0U,steps);
}
}
int main() {
    unsigned failed=0;
    for(auto region:{picocalc::lcd::Region{40,240},picocalc::lcd::Region{42,238},picocalc::lcd::Region{0,320}}) {
        try { recovery(region,region.top!=0); }
        catch(const std::exception& error) {
            ++failed;std::fprintf(stderr,"Panel region top=%u height=%u FAIL: %s\n",region.top,region.height,error.what());
        }
    }
    return failed?1:0;
}
