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
    std::array<u16,lcd::WIDTH*lcd::HEIGHT> colors{};
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
            colors[y*lcd::WIDTH+x]=source[i];
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
u32 hardware_spi_hz=12000000,clock_changes=0;
u32 spi_set_baudrate(int,u32 requested) {
    require(!controller.pending,"SPI clock changes only after the queued LCD transfer finishes");
    ++clock_changes;hardware_spi_hz=requested>=24000000?24000000:12000000;
    return hardware_spi_hz;
}
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
bool frames_suspended() { return false; }
bool submit_frame(void* context,void (*transfer)(void*)) {
    require(!controller.pending,"single in-flight frame");
    controller.context=context;controller.transfer=transfer;controller.pending=true;return true;
}
void service() {}
void drain() { if(controller.pending) controller.run(); }
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
bool Panel::transfer_chain(const lcd::Rect& rect,u32&,bool color) {
    stream_.reset(rect);
    for(unsigned i=0;i<stream_.count;++i) {
        const auto block=lcd::Stream::prepare(rect,i,scanlines,[&](unsigned row,u16* out) {
            if(color) lcd::color_scanline(color_frame_,rect,row,out,color_palette_);
            else lcd::scanline(previous_,rect,row,(u8*)out);
        });
        controller.pixels(scanlines,block.count);
        if(!finish_scanline()) return false;
    }
    return true;
}
bool Panel::transfer_fill(u16 color,unsigned width,unsigned height) {
    for(unsigned x=0;x<width;++x) scanlines[x]=color;
    for(unsigned y=0;y<height;++y) {
        controller.pixels(scanlines,width);
        if(!finish_scanline()) return false;
    }
    return true;
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
    require(panel.flush(frame),"initial frame accepted");
    require(!panel.flush(frame),"busy panel does not acknowledge an unsubmitted frame");
    controller.run();require(controller.visible(frame),"initial exact frame");
    require(panel.flush(frame) && !controller.pending,"identical completed frame acknowledged without DMA");
    if(fail_first) {
        frame=shifted(frame,16);controller.commands.clear();controller.fail_completion=true;
        panel.flush(frame);controller.run();
        require(controller.count(0x33)==1 && controller.count(0x37)==0 && panel.errors()==1,
                "fault must follow first VSCRDEF and precede VSCSAD");
        controller.commands.clear();panel.flush(frame);
        require(panel.update_.count==1 && panel.update_.bytes==lcd::WIDTH*lcd::HEIGHT*2,"full recovery frame");
        controller.run();
        if(controller.count(0x33)>1 || controller.count(0x37)!=1) {
            std::fprintf(stderr,"Partial-region recovery top=%u height=%u: VSCRDEF=%u VSCSAD=%u origin=%u expected=%u\n",
                         region.top,region.height,controller.count(0x33),controller.count(0x37),controller.origin,region.top);
            require(false,"recovery must publish the zero-offset origin of the actual scroll region");
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
    require(controller.count(0x33)<=1 && controller.count(0x37)==1,
            "configured-region retry publishes the origin of the actual scroll region");
    require(controller.region==frame.region && controller.origin==frame.region.top && panel.scroll_offset()==0,
            "region switch resets absolute origin");
    require(controller.visible(frame),"region-switch full redraw exact");
    frame.region={};frame.pixels[1]^=1;panel.flush(frame);controller.run();
    require(controller.region==lcd::Region{0,320} && controller.origin==0 && controller.visible(frame),
            "leaving scroll view restores ordinary full-screen mapping");
    std::printf("Panel actual flush/transfer: top=%u height=%u first_failure_recovery=%u scrolls=%u both_wraps configured_region_failure_retry fixed_pixels PASS\n",
                region.top,region.height,fail_first?1U:0U,steps);
}
void changed_view_before_retry(lcd::Region initial,lcd::Region failed,bool ordinary_exit) {
    controller=Controller{};Panel panel;Screen frame;frame.region=initial;
    for(auto& value:frame.pixels) value=byte();
    panel.flush(frame);controller.run();
    frame=shifted(frame,16);panel.flush(frame);controller.run();
    require(controller.region==initial && controller.origin==initial.top+16 && controller.visible(frame),
            "view-change fixture begins with a successfully configured scroll");
    if(ordinary_exit) {
        frame.region={};frame.pixels[0]^=1;panel.flush(frame);controller.run();
        require(controller.region==lcd::Region{0,320} && controller.origin==0 &&
                panel.configured_region_==lcd::Region{0,320} && controller.visible(frame),
                "ordinary fixture has cached full-screen definition and origin zero");
    }
    frame.region=failed;frame.pixels[2]^=1;
    controller.commands.clear();controller.fail_completion=true;
    panel.flush(frame);controller.run();
    require(controller.count(0x33)==1 && controller.count(0x37)==0 && panel.errors()==1 && controller.region==failed,
            "changed-view fault follows the actual definition change before origin publication");
    frame.region=ordinary_exit?lcd::Region{}:initial;frame.pixels[3]^=1;
    const auto expected=ordinary_exit?lcd::Region{0,320}:initial;
    controller.commands.clear();panel.flush(frame);
    require(panel.update_.count==1 && panel.update_.bytes==lcd::WIDTH*lcd::HEIGHT*2,
            "view change before retry still forces a full frame");
    controller.run();
    const bool visible=controller.visible(frame);
    if(controller.count(0x33)!=1 || controller.count(0x37)!=1 || controller.region!=expected ||
       controller.origin!=expected.top || panel.scroll_offset()!=0 || !visible) {
        std::fprintf(stderr,"View changed before retry initial=%u/%u failed=%u/%u target=%u/%u: VSCRDEF=%u VSCSAD=%u actual=%u/%u cached=%u/%u origin=%u visible=%u\n",
                     initial.top,initial.height,failed.top,failed.height,expected.top,expected.height,
                     controller.count(0x33),controller.count(0x37),controller.region.top,controller.region.height,
                     panel.configured_region_.top,panel.configured_region_.height,controller.origin,visible?1U:0U);
        require(false,"changed-view retry must redefine the actual region and publish its matching origin");
    }
    std::printf("Panel changed-view retry: initial=%u/%u failed=%u/%u target=%u/%u actual_definition origin fixed_pixels PASS\n",
                initial.top,initial.height,failed.top,failed.height,expected.top,expected.height);
}
void color_session(bool chain) {
    controller=Controller{};Panel panel;Screen mono;
    mono.region={40,240};for(auto& value:mono.pixels) value=byte();
    panel.flush(mono);controller.run();mono=shifted(mono,16);panel.flush(mono);controller.run();
    if(chain) { panel.dma_tx_=0;panel.dma_rx_=1;panel.dma_control_=2; }
    std::array<u8,6144> bits{};std::array<u8,768> tiles{};tiles.fill(0x12);
    mk61_service_color_frame f{};f.pixels=bits.data();f.tiles=tiles.data();f.pixel_bytes=bits.size();f.tile_bytes=tiles.size();
    f.width=256;f.height=192;f.x=32;f.y=64;f.format=MK61_COLOR_TILE1;f.background=0x1234;
    f.palette[1]=0x001F;f.palette[2]=0xF800;
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"color accepted");
    bits.fill(255);require(panel.color(MK61_COLOR_PRESENT,&f)==2,"in-flight color rejects without copying");
    require(!panel.flush(mono),"ordinary UI cannot overwrite color session");controller.run();
    require(controller.region==lcd::Region{0,320} && controller.origin==0,"color resets scrolled coordinates");
    for(unsigned y=0;y<320;++y) for(unsigned x=0;x<320;++x)
        require(controller.colors[y*320+x]==(x>=32 && x<288 && y>=64 && y<256?0x001F:0x1234),"immutable copied palette pixels and border");
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"changed color accepted");controller.run();
    require(controller.colors[64*320+32]==0xF800,"changed tile pixels");
    const auto frames=panel.frames();require(panel.color(MK61_COLOR_PRESENT,&f)==1 && !controller.pending && panel.frames()==frames,"identical color skips LCD");
    f.background=0x5678;require(panel.color(MK61_COLOR_PRESENT,&f)==1,"border-only change");controller.run();
    require(controller.colors[0]==0x5678 && controller.colors[64*320+32]==0xF800,"border preserves image");
    bits[0]=0;controller.fail_completion=true;panel.color(MK61_COLOR_PRESENT,&f);controller.run();
    require(panel.errors()==1,"color completion failure recorded");
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"color full retry");
    controller.run();
    std::array<u8,1536> pairs{};pairs.fill(61);pairs[1]=52;
    std::array<u16,64> clut{};clut[61]=0xAFAF;clut[52]=0xBCBC;
    require(panel.color_palette(clut.data())==1,"64-color palette accepted");
    f.format=MK61_COLOR_TILE8;f.tiles=pairs.data();f.tile_bytes=pairs.size();bits[0]=0x80;
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"64-color tile frame accepted");
    clut[61]=0x5555;require(panel.color_palette(clut.data())==2,"busy palette rejects without mutation");
    controller.run();require(controller.colors[64*320+32]==0xBCBC && controller.colors[64*320+33]==0xAFAF,"copied 64-color palette used");
    require(panel.color_palette(clut.data())==1,"palette update accepted");
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"palette-only redraw accepted");
    controller.run();require(controller.colors[64*320+33]==0x5555 && controller.colors[0]==0x5678,"palette redraw preserves border");
    bits[0]^=1;require(panel.color(MK61_COLOR_PRESENT,&f)==1,"queue last color transfer");
    require(panel.color(MK61_COLOR_END)==1 && !controller.pending && !panel.color_active(),"end drains transfer before APP buffer release");
    mono.region={};require(panel.flush(mono),"mono restoration accepted");controller.run();
    require(controller.visible(mono),"complete mono snapshot restored after color");
    std::printf("Panel color session chain=%u: copy/busy, scrolling, palette/border, dirty retry, drain and mono restoration PASS\n",chain);
}
void color_clock_session() {
    controller=Controller{};Panel panel;Screen mono;
    panel.spi_hz_=hardware_spi_hz=12000000;clock_changes=0;
    const auto clock=[&](u32 hz) {
        // Native services allow an unaligned request; the driver must copy it.
        u8 bytes[8]{};std::memcpy(bytes+1,&hz,sizeof(hz));
        return panel.color(MK61_COLOR_SPI_HZ,bytes+1);
    };
    require(!panel.color(MK61_COLOR_SPI_HZ),"null clock request rejected");
    require(!clock(32000000) && !clock(1) && !clock(UINT32_MAX) && !clock_changes,"unsupported rates leave SPI untouched");
    require(panel.flush(mono) && controller.pending,"ordinary frame queued before clock switch");
    require(clock(24000000)==24000000 && !controller.pending && panel.frames()==1 && hardware_spi_hz==24000000,"12 -> 24 MHz drains actual old frame");
    mono.pixels[0]^=1;require(panel.flush(mono) && controller.pending,"next frame queued");
    require(clock(24000000)==24000000 && controller.pending && clock_changes==1,"repeated request does not stall queued frame");
    require(!clock(32000000) && controller.pending && clock_changes==1,"invalid request cannot drain or retune an active frame");
    require(panel.color(MK61_COLOR_END)==1 && !controller.pending && panel.spi_hz()==12000000 && !panel.color_spi_request_,"END restores default even before first color frame");
    require(clock(12000000)==12000000 && clock(0)==12000000 && !panel.color_spi_request_,"explicit normal/default rates accepted");
    require(clock(24000000)==24000000,"second accelerated session");
    std::array<u8,32> bits{};std::array<u8,4> tiles{};
    mk61_service_color_frame f{};f.pixels=bits.data();f.tiles=tiles.data();f.pixel_bytes=bits.size();f.tile_bytes=tiles.size();
    f.width=f.height=16;f.format=MK61_COLOR_TILE1;
    require(panel.color(MK61_COLOR_PRESENT,&f)==1 && controller.pending,"color frame queued at 24 MHz");
    require(panel.color(MK61_COLOR_END)==1 && !controller.pending && !panel.color_active() && hardware_spi_hz==12000000,"END drains color and restores default");
    const auto changes=clock_changes;
    require(panel.color(MK61_COLOR_END)==1 && clock_changes==changes,"repeated END is harmless");
    std::puts("Panel actual color clock: in-flight drain, repeated/invalid/unaligned request, 12/24/default and early/normal END restore PASS");
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
    for(auto partial:{picocalc::lcd::Region{40,240},picocalc::lcd::Region{42,238}}) {
        for(bool ordinary_exit:{false,true}) {
            const auto initial=ordinary_exit?picocalc::lcd::Region{0,320}:
                partial.top==40?picocalc::lcd::Region{42,238}:picocalc::lcd::Region{40,240};
            try { changed_view_before_retry(initial,partial,ordinary_exit); }
            catch(const std::exception& error) {
                ++failed;std::fprintf(stderr,"Panel changed-view failed-region=%u/%u ordinary_exit=%u FAIL: %s\n",
                                     partial.top,partial.height,ordinary_exit?1U:0U,error.what());
            }
        }
    }
    for(bool chain:{false,true}) {
        try { color_session(chain); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel color FAIL: %s\n",error.what()); }
    }
    try { color_clock_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel clock FAIL: %s\n",error.what()); }
    return failed?1:0;
}
