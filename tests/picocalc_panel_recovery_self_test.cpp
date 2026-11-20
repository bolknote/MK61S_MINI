#include "worker_deadline_trace.hpp"
#include "pwm_duty_ring.hpp"
// HOST-only controller boundary. Panel::flush/transfer are included verbatim
// from production hardware.cpp by picocalc_panel_recovery_self_test.py.
#include "rust_types.h"
#include "lcd_scroll.hpp"
#include "lcd_shell_update.hpp"
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
    lcd::ShellTheme theme{};
    const u8* data() const { return pixels.data(); }
    const lcd::ShellTheme& color_theme() const { return theme; }
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
void traced_frame_transfer(void(*transfer)(void*),void* context);
void injected_crc_work();
bool inject_crc_work=false,mask_crc_irq=false;
audio_stream::DutyRing::Result injected_pwm_result=audio_stream::DutyRing::EARLY;
struct Controller {
    std::array<u16,lcd::WIDTH*480> colors{};
    std::vector<Command> commands;
    lcd::Region region{0,lcd::HEIGHT};
    unsigned origin=0,x0=0,x1=319,y0=0,y1=319,cursor=0;
    bool pending=false,fail_completion=false,inverted=false,gram_480=false,partial=false,display_on=true;
    bool ignore_scroll_while_blank=false;
    unsigned partial_first=0,partial_last=479;
    void* context=nullptr;
    void (*transfer)(void*)=nullptr;
    unsigned word(const u8* data) { return ((unsigned)data[0]<<8)|data[1]; }
    void command(u8 op,const u8* data,unsigned count) {
        commands.push_back({op,count?std::vector<u8>(data,data+count):std::vector<u8>{}});
        if(op==0x33) {
            require(count==6,"VSCRDEF length");
            region={(u16)word(data),(u16)word(data+2)};
            gram_480=region.top==0 && region.height==480 && word(data+4)==0;
            require(gram_480 || (region.valid() && region.top+region.height+word(data+4)==lcd::HEIGHT),"VSCRDEF geometry");
        } else if(op==0x37) {
            require(count==2,"VSCSAD length");
            if(!ignore_scroll_while_blank || display_on) origin=word(data);
        } else if(op==0x2A) {
            require(count==4,"CASET length");x0=word(data);x1=word(data+2);
        } else if(op==0x2B) {
            require(count==4,"PASET length");y0=word(data);y1=word(data+2);
        } else if(op==0x30) {
            require(count==4,"PTLAR length");partial_first=word(data);partial_last=word(data+2);
            require(partial_first<=partial_last && partial_last<480,"partial area bounds");
        } else if(op==0x12 || op==0x13) {
            require(count==0,"partial mode command length");partial=op==0x12;
        } else if(op==0x20 || op==0x21) {
            require(count==0,"inversion command length");inverted=op==0x20;
        } else if(op==0x28 || op==0x29) {
            require(count==0,"display on/off command length");display_on=op==0x29;
        } else require(false,"unexpected controller command");
    }
    void pixels(const u16* source,unsigned count) {
        const unsigned width=x1-x0+1;
        require(x0<=x1 && x1<lcd::WIDTH && y0<=y1 && y1<480,"bounded LCD window");
        require(cursor+count<=width*(y1-y0+1),"bounded pixel payload");
        for(unsigned i=0;i<count;++i,++cursor) {
            const unsigned x=x0+cursor%width,y=y0+cursor/width;
            colors[y*lcd::WIDTH+x]=source[i];
        }
    }
    const u16* visible_row(unsigned y) const {
        const unsigned physical=gram_480?(origin+y)%480:y<region.top || y>=region.top+region.height?y:
            region.top+(y-region.top+origin-region.top)%region.height;
        return colors.data()+physical*lcd::WIDTH;
    }
    bool visible(const Screen& expected) const {
        if(gram_480 ? origin>=480 : origin<region.top || origin>=region.top+region.height) return false;
        const auto& theme=expected.color_theme();
        std::array<u16,lcd::WIDTH> background;
        for(unsigned y=0;y<lcd::HEIGHT;++y) {
            theme.background_row(0,y,lcd::WIDTH,background.data());
            const u16* actual=visible_row(y);
            const u8* bitmap=expected.data()+y*lcd::STRIDE;
            for(unsigned x=0;x<lcd::WIDTH;++x) {
                const bool ink=bitmap[x/8]&(0x80U>>(x%8));
                if(actual[x]!=(ink?lcd::color(theme.at(x,y)):background[x])) return false;
            }
        }
        return true;
    }
    unsigned count(u8 op) const {
        unsigned n=0;for(const auto& c:commands) n+=c.op==op;return n;
    }
    void run() {
        require(pending && transfer,"queued actual Panel transfer");
        traced_frame_transfer(transfer,context);pending=false;
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
u64 clock_now=0;
u64 time_us_64() { return ++clock_now; }
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
u32 crc32(const u8* bytes,unsigned size,void (*progress)()) {
    if(progress)progress();
    injected_crc_work();
    u32 result=0;for(unsigned i=0;i<size;++i) result=result*33U+bytes[i];return result;
}
}
void Panel::start_scanline(const u16* pixels,unsigned count) { controller.pixels(pixels,count); }
bool Panel::finish_scanline(bool) {
    if(controller.fail_completion) { controller.fail_completion=false;return false; }
    return true;
}
bool Panel::transfer_chain(const lcd::Rect& rect,u32&,bool color) {
    stream_.reset(rect);
    for(unsigned i=0;i<stream_.count;++i) {
        const auto block=lcd::Stream::prepare(rect,i,scanlines,[&](unsigned row,u16* out) {
            if(color) lcd::color_scanline(color_frame_,rect,row,out,color_palette_);
            else lcd::shell_scanline(previous_bytes(),rect,row,previous_theme_,out);
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
namespace {
void traced_frame_transfer(void(*transfer)(void*),void* context) {
    io_worker::FrameDeadlineScope frame(WorkerDeadlineTrace::FRAME);transfer(context);
}
void injected_crc_work() {
    if(!inject_crc_work)return;
    inject_crc_work=false;
    using audio_stream::DutyRing;
    DutyRing ring;std::array<u32,64> samples{};
    ring.prime_block(samples.data(),[](u32* out,unsigned n){for(unsigned i=0;i<n;++i)out[i]=i;});
    const u64 first=clock_now,dma_start=first-1260;
    // Boundary model only: inject750us of work at the real Panel CRC call.
    // A pending highest-priority IRQ is delayed only in the masked control.
    clock_now=first+(mask_crc_irq?750:20);
    injected_pwm_result=ring.refill_block(samples.data(),[&]{return u32((clock_now-dma_start)/40);},
        [&](u32* out,unsigned n){for(unsigned i=0;i<n;++i)out[i]=i;clock_now+=100;});
    if(injected_pwm_result==DutyRing::LATE)io_worker::deadline_trace.audio_fault(u32(clock_now));
    if(!mask_crc_irq)clock_now+=730;
}
}

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
void shell_theme_session(bool chain) {
    controller=Controller{};
    Panel panel;
    Screen frame;
    if(chain) { panel.dma_tx_=0;panel.dma_rx_=1;panel.dma_control_=2; }
    frame.pixels[0]=0x80;
    require(panel.flush(frame) && controller.pending,"initial shell frame queued");
    controller.run();
    require(controller.visible(frame),"initial shell palette arrives at the LCD");
    frame.theme.reset(lcd::Ink::OCHRE);
    require(panel.flush(frame) && controller.pending,"theme-only change queues a redraw");
    controller.run();
    require(controller.visible(frame) && controller.visible_row(0)[0]==lcd::color(lcd::Ink::OCHRE),
            "theme-only redraw updates the actual RGB565 pixel");
    require(panel.flush(frame) && !controller.pending,"unchanged bitmap and theme skip DMA");
    std::printf("Panel shell palette chain=%u: theme-only redraw and RGB565 output PASS\n",chain);
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
    require(controller.region==mono.region && controller.origin==mono.region.top+16,
            "color preserves the active scroll mapping");
    for(unsigned y=0;y<lcd::HEIGHT;++y) {
        const u16* row=controller.visible_row(y);
        for(unsigned x=0;x<lcd::WIDTH;++x)
            require(row[x]==(x>=32 && x<288 && y>=64 && y<256?0x001F:0x1234),
                    "immutable copied palette pixels and border");
    }
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"changed color accepted");controller.run();
    require(controller.visible_row(64)[32]==0xF800,"changed tile pixels");
    const auto frames=panel.frames();require(panel.color(MK61_COLOR_PRESENT,&f)==1 && !controller.pending && panel.frames()==frames,"identical color skips LCD");
    f.background=0x5678;require(panel.color(MK61_COLOR_PRESENT,&f)==1,"border-only change");controller.run();
    require(controller.visible_row(0)[0]==0x5678 && controller.visible_row(64)[32]==0xF800,"border preserves image");
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
    controller.run();
    require(controller.visible_row(64)[32]==0xBCBC && controller.visible_row(64)[33]==0xAFAF,
            "copied 64-color palette used");
    require(panel.color_palette(clut.data())==1,"palette update accepted");
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"palette-only redraw accepted");
    controller.run();
    require(controller.visible_row(64)[33]==0x5555 && controller.visible_row(0)[0]==0x5678,
            "palette redraw preserves border");
    bits[0]^=1;require(panel.color(MK61_COLOR_PRESENT,&f)==1,"queue last color transfer");
    require(panel.color(MK61_COLOR_END)==1 && !controller.pending && !panel.color_active(),"end drains transfer before APP buffer release");
    std::array<u8,320> indexed{};indexed.fill(0x13);
    mk61_service_color_frame band{};band.pixels=indexed.data();band.pixel_bytes=indexed.size();
    band.y=80;band.width=320;band.height=2;
    band.format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
    band.palette[1]=0x1234;band.palette[3]=0x5678;
    require(panel.color(MK61_COLOR_PRESENT,&band)==1 && controller.pending,"single-page INDEX4 band accepted");
    controller.run();
    for(unsigned x=0;x<band.width;++x)
        require(controller.visible_row(band.y)[x]==band.palette[x&1?3:1],"single-page INDEX4 RGB565 order");
    band.palette[3]=0x9ABC;
    require(panel.color(MK61_COLOR_PRESENT,&band)==1 && controller.pending,"INDEX4 palette-only redraw");
    controller.run();
    require(controller.visible_row(band.y+1)[319]==0x9ABC,"single-page INDEX4 uses the new palette");
    std::array<u8,480> narrow{};
    for(unsigned i=0;i<narrow.size();++i) narrow[i]=u8(i*37);
    band.x=260;band.y=96;band.width=60;band.height=16;
    band.pixels=narrow.data();band.pixel_bytes=narrow.size();
    for(unsigned i=0;i<16;++i) band.palette[i]=u16(i*71);
    require(panel.color(MK61_COLOR_PRESENT,&band)==1 && controller.pending,"narrow INDEX4 window accepted");
    controller.run();
    require(panel.strips()==(chain?1:16),"960 pixels fit in one DMA transfer");
    for(unsigned y=0;y<band.height;++y) for(unsigned x=0;x<band.width;++x)
        require(controller.visible_row(band.y+y)[band.x+x]==lcd::color_pixel(band,x,y),
                "contiguous DMA rows retain their pixels and stride");
    require(panel.color(MK61_COLOR_END)==1,"single-page INDEX4 ended");
    mono.region={};require(panel.flush(mono),"mono restoration accepted");controller.run();
    require(controller.visible(mono),"complete mono snapshot restored after color");
    std::printf("Panel color session chain=%u: copy/busy, scrolling, palette/border, dirty retry, drain and mono restoration PASS\n",chain);
}
void color_clock_session() {
    controller=Controller{};Panel panel;Screen mono;
    panel.spi_hz_=hardware_spi_hz=12000000;clock_changes=0;
    panel.applied_spi_request_=MK61_PICOCALC_LCD_SPI_HZ;
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
void external_clock_session() {
    controller=Controller{};Panel panel;Screen mono;
    panel.spi_hz_=hardware_spi_hz=12000000;
    panel.applied_spi_request_=MK61_PICOCALC_LCD_SPI_HZ;clock_changes=0;
    BatteryStatus battery;battery.available=true;battery.percent=100;
    for(const u8 state:{0U,0xA0U,0xB1U}) {
        battery.power_status=state;panel.power_supply(battery,false);
        panel.flush(mono);if(controller.pending) controller.run();
        require(!panel.external_power() && hardware_spi_hz==12000000,"unknown/battery/100 percent never infers external power");
    }
    for(const u8 state:{0xB7U,0xBBU,0xB3U}) {
        battery.power_status=state;panel.power_supply(battery,false);
        if(hardware_spi_hz!=24000000) require(panel.needs_refresh(),"clock-only change wakes an otherwise unchanged resident frame");
        panel.flush(mono);
        require(panel.external_power() && hardware_spi_hz==24000000,"charging/DONE/external all accelerate native UI");
    }
    mono.pixels[0]^=1;panel.flush(mono);require(controller.pending,"accelerated frame in flight");
    battery.clear_power();panel.power_supply(battery,false);
    require(panel.needs_refresh(),"power loss requests service without pixel changes");
    const auto changes=clock_changes;
    require(!panel.flush(mono) && controller.pending && clock_changes==changes,"power loss never retunes or drains in-flight DMA");
    controller.run();panel.flush(mono);
    require(hardware_spi_hz==12000000 && !controller.pending,"power loss restores normal clock even when pixels identical");
    panel.power_supply(battery,true);panel.flush(mono);
    require(hardware_spi_hz==24000000,"Pico VBUS supplies external power without PMU telemetry");
    mono.pixels[1]^=1;controller.fail_completion=true;panel.flush(mono);controller.run();
    require(panel.flush(mono) && controller.pending && hardware_spi_hz==12000000 && panel.clock_fallbacks()==1,
            "failed automatic fast transfer retries complete frame at normal clock");
    controller.run();panel.power_supply(battery,true);panel.flush(mono);
    require(hardware_spi_hz==12000000,"failed fast clock stays disabled throughout same power session");
    panel.power_supply(battery,false);panel.flush(mono);panel.power_supply(battery,true);panel.flush(mono);
    require(hardware_spi_hz==24000000,"new external-power session may retry fast clock");
    const u32 slow=12000000,fast=24000000;
    require(panel.color(MK61_COLOR_SPI_HZ,&slow)==12000000,"explicit APP slow request has priority");
    require(panel.color(MK61_COLOR_END)==1 && hardware_spi_hz==24000000,"APP END restores powered UI clock");
    panel.power_supply(battery,false);
    require(panel.color(MK61_COLOR_SPI_HZ,&fast)==24000000,"existing explicit APP fast ABI remains available");
    require(panel.color(MK61_COLOR_END)==1 && hardware_spi_hz==12000000,"APP END restores current battery UI clock");
    panel.power_supply(battery,true);
    require(panel.color(MK61_COLOR_END)==1 && hardware_spi_hz==24000000,"END also refreshes automatic policy without an explicit APP override");
    std::array<u8,32> bits{};std::array<u8,4> tiles{};
    mk61_service_color_frame frame{};frame.pixels=bits.data();frame.tiles=tiles.data();
    frame.pixel_bytes=bits.size();frame.tile_bytes=tiles.size();frame.width=frame.height=16;frame.format=MK61_COLOR_TILE1;
    require(panel.color(MK61_COLOR_PRESENT,&frame)==1,"automatic fast paletted frame queued");
    panel.power_supply(battery,false);
    require(panel.color(MK61_COLOR_PRESENT,&frame)==2 && hardware_spi_hz==24000000,"paletted DMA not disturbed by power loss");
    controller.run();
    require(panel.color(MK61_COLOR_PRESENT,&frame)==1 && hardware_spi_hz==12000000,"automatic paletted clock follows power even for identical pixels");
    panel.color(MK61_COLOR_END);
    puts("Panel powered UI: PMU/VBUS/unknown, hot unplug during DMA, same pixels, sticky error fallback and APP clock priority PASS");
}
void input_response_session() {
    controller=Controller{};Panel panel;Screen mono;
    panel.flush(mono);controller.run();require(!panel.responses(),"untagged frames do not count as key response");
    const auto first=time_us_64();panel.note_input(first);clock_now+=5000;
    mono.pixels[0]^=1;panel.flush(mono);clock_now+=8000;
    const auto second=time_us_64();panel.note_input(second);controller.run();
    require(panel.responses()==1 && panel.response_us()>=13000 && panel.response_us()<13100,
            "response spans input, preparation and actual LCD completion");
    mono.pixels[1]^=1;panel.flush(mono);clock_now+=3000;controller.run();
    require(panel.responses()==2 && panel.response_us()>=3000 && panel.response_us()<3100 && panel.response_max_us()>=13000,
            "input during DMA belongs to next snapshot");
    panel.note_input(time_us_64());clock_now+=1000;mono.pixels[2]^=1;
    controller.fail_completion=true;panel.flush(mono);controller.run();require(panel.responses()==2,"failed frame is not a visible response");
    clock_now+=2000;panel.flush(mono);controller.run();
    require(panel.responses()==3 && panel.response_us()>=3000,"retry preserves original input timestamp");
    puts("Panel response timing: actual completion, in-flight next input and failed-transfer retry PASS");
}
void color_inversion_session() {
    controller=Controller{};Panel panel;Screen mono;
    const u32 on=1,off=0,invalid=2;
    require(panel.color(MK61_COLOR_INVERT,&on)==0,"inversion requires an active color image");
    std::array<u8,128> pixels{};
    mk61_service_color_frame f{};f.pixels=pixels.data();f.pixel_bytes=pixels.size();
    f.width=f.height=16;f.format=MK61_COLOR_INDEX4;f.palette[0]=0xffff;
    require(panel.color(MK61_COLOR_PRESENT,&f)==1 && controller.pending,"color frame queued");
    require(panel.color(MK61_COLOR_INVERT,&on)==2 && !controller.count(0x20),"inversion waits for DMA");
    controller.run();
    require(panel.color(MK61_COLOR_INVERT,&invalid)==0,"invalid inversion rejected");
    require(panel.color(MK61_COLOR_INVERT,&on)==1 && controller.inverted && controller.count(0x20)==1,
            "inversion changes the whole panel with one command");
    require(panel.color(MK61_COLOR_INVERT,&on)==1 && controller.count(0x20)==1,"repeated mode is a no-op");
    require(panel.color(MK61_COLOR_PRESENT,&f)==0 && !controller.pending,"drawing while inverted is rejected");
    require(panel.color(MK61_COLOR_INVERT,&off)==1 && !controller.inverted && controller.count(0x21)==1,
            "normal mode restores without changing GRAM");
    require(panel.color(MK61_COLOR_INVERT,&on)==1 && controller.inverted,"inversion can resume");
    require(panel.color(MK61_COLOR_END)==1 && !controller.inverted && controller.count(0x21)==2,
            "ending an APP restores the native mode");
    require(panel.flush(mono) && controller.pending,"ordinary interface redraws after the APP");controller.run();
    require(controller.visible(mono),"ordinary interface remains correct after inversion");
    puts("Panel inversion: idle boundary, idempotence, drawing guard and APP cleanup PASS");
}
void color_pages_session() {
    controller=Controller{};Panel panel;Screen mono;
    // Reproduce the optical symptom with the unscrolled scanout at startup.
    controller.ignore_scroll_while_blank=true;
    mk61_service_color_pages bad{250,100},config{60,200};
    const u32 page0=0,page1=1,invalid=2,on=1,off=0;
    u32 first_page=page0;
    require(panel.color(MK61_COLOR_PAGES_BEGIN,&config)==0,"legacy page request falls back");
    require(panel.color(MK61_COLOR_PAGES_BEGIN_V2,&bad)==0,"reject pages beyond the visible screen");
    require(panel.color(MK61_COLOR_PAGES_BEGIN_V2,&config)==1 && !controller.display_on,
            "hide the first frame until the compensated colors and scan window are ready");
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==0,"unwritten page cannot be shown");
    require(panel.color(MK61_COLOR_PAGE_SELECT,&invalid)==0,"invalid page rejected");
    mk61_service_color_scroll scroll{60,200,0,1};
    require(panel.color(MK61_COLOR_SCROLL_BEGIN,&scroll)==0,"scroll transaction cannot overlap page mode");
    std::array<u8,12800> bytes;
    mk61_service_color_frame f{};f.pixels=bytes.data();f.width=320;f.x=0;
    f.format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
    f.y=60;f.height=80;f.pixel_bytes=12800;
    require(panel.color(MK61_COLOR_PAGE_SELECT,&page0)==1,"select page while display is blanking");
    require(panel.color(MK61_COLOR_PRESENT,&f)==2 && !controller.pending && !controller.inverted && !controller.partial,
            "wait for blanking before writing compensated GRAM or changing polarity");
    clock_now+=50000;
    auto draw=[&](u32 page,u16 color) {
        require(panel.color(MK61_COLOR_PAGE_SELECT,&page)==1,"page selected");
        f.palette[1]=color;
        f.palette[2]=color^0xffff;
        for(unsigned y=0;y<config.height;y+=80) {
            f.y=(u16)(config.top+y);f.height=(u16)(config.height-y<80?config.height-y:80);f.pixel_bytes=160*f.height;
            for(unsigned row=0;row<f.height;++row)
                std::memset(bytes.data()+160*row,y+row<config.height/2U?0x11:0x22,160);
            require(panel.color(MK61_COLOR_PRESENT,&f)==1 && controller.pending,"page strip queued");
            require(panel.color(MK61_COLOR_PAGE_SELECT,&page)==2,"cannot switch page during DMA");
            controller.run();
        }
    };
    auto visible=[&](unsigned page,u16 color) {
        require(controller.gram_480 && controller.partial && controller.inverted && controller.display_on,
                "page scan, partial mode and compensated polarity are active");
        for(unsigned y=0;y<320;++y) {
            // The optical capture shows PTLAR gating physical rows, before
            // VSCSAD selects their GRAM addresses. Outside is panel-driven.
            const bool active=y>=controller.partial_first && y<=controller.partial_last;
            require(active==(y>=config.top && y<(unsigned)config.top+config.height),
                    "partial window must stay at the same screen rows");
            if(!active) continue;
            const unsigned address=(controller.origin+y)%480;
            require(address==(y+(page==first_page?0:config.height))%480,
                    "every visible row must come from the selected GRAM page");
            const u16 expected=y-config.top<config.height/2U?color:color^0xffff;
            for(unsigned x=0;x<320;++x)
                require((controller.colors[address*320+x]^0xffffu)==expected,"GRAM complement restores exact row color");
        }
    };
    draw(page0,0x1234);
    require(!controller.display_on && controller.origin==0 &&
            controller.colors[60*320+123]==(0x1234^0xffffu),
            "first page is written at its screen coordinates in compensated polarity");
    require(controller.inverted && controller.partial && controller.count(0x30)==1,
            "configure the centered scan window before making any of the first page visible");
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==2 && !controller.display_on,
            "first SHOW waits while the new scan configuration takes effect");
    clock_now+=50000;
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==1,"first page published");visible(0,0x1234);
    require(panel.color(MK61_COLOR_PRESENT,&f)==1 && !controller.pending,"matching palettes keep the dirty check effective");
    draw(page1,0xabcd);visible(0,0x1234);
    const auto switches=controller.commands.size();
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page1)==1,"second page published");visible(1,0xabcd);
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==1,"first page can be shown again");visible(0,0x1234);
    require(!controller.pending && controller.commands.size()==switches+2 && controller.commands[switches].op==0x37 &&
            controller.commands[switches+1].op==0x37,"a page switch only writes the scroll address");
    require(controller.count(0x30)==1 && controller.count(0x28)==1 && controller.count(0x29)==1,
            "later page switches change only the GRAM origin without another blanking interval");
    require(panel.color(MK61_COLOR_INVERT,&on)==0,"page mode owns the hardware polarity");
    require(panel.color(MK61_COLOR_INVERT,&off)==1 && controller.count(0x20)==1 && controller.inverted,
            "idempotent normal-color barrier leaves compensation intact");
    require(panel.color(MK61_COLOR_PAGES_END)==1 && !controller.inverted && !controller.partial && controller.origin==0,
            "page end restores inversion, partial mode and normal origin");
    require(panel.flush(mono) && controller.pending,"shell can redraw after page end");controller.run();
    require(controller.visible(mono),"shell pixels restored after page mode");

    require(panel.color(MK61_COLOR_PAGES_BEGIN_V2,&config)==1,"restart page transaction");
    require(panel.color(MK61_COLOR_PAGE_SELECT,&page0)==1,"select failure test page");
    f.y=60;f.height=80;f.pixel_bytes=12800;controller.fail_completion=true;
    clock_now+=50000;
    require(panel.color(MK61_COLOR_PRESENT,&f)==1,"failure test strip queued");controller.run();
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==0,"failed DMA cannot publish a page");
    require(panel.color(MK61_COLOR_END)==1 && controller.display_on,"APP exit cancels and unblanks a failed first page");
    require(panel.flush(mono) && controller.pending,"failure is recovered by shell redraw");controller.run();
    require(controller.visible(mono),"failure recovery restores shell pixels");

    require(panel.color(MK61_COLOR_PAGES_BEGIN_V2,&config)==1 && !controller.display_on,
            "blank a fresh session before touching the active raster");
    require(panel.color(MK61_COLOR_END)==1 && controller.display_on && !controller.inverted && !controller.partial,
            "early exit restores the display even before the first transfer");

    config={70,240};
    first_page=page1;
    require(panel.color(MK61_COLOR_PAGES_BEGIN_V2,&config)==1,"begin with the other logical page first");
    clock_now+=50000;
    draw(page1,0xac61);
    clock_now+=50000;
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page1)==1,"either logical page can be first");
    visible(1,0xac61);
    const auto writes=controller.count(0x2b);
    draw(page0,0x9daa);
    require(controller.count(0x2b)==writes+4,"the hidden page splits a transfer crossing GRAM row 479");
    visible(1,0xac61);
    require(panel.color(MK61_COLOR_PAGE_SHOW,&page0)==1,"show the wrapped GRAM page");
    visible(0,0x9daa);
    require(panel.color(MK61_COLOR_END)==1,"end the wrapped page session");
    puts("Panel pages: unscrolled startup, fixed scan window, wrapped GRAM, exact RGB565 and failure cleanup PASS");
}
}
void frame_deadline_session() {
    using namespace picocalc;
    using audio_stream::DutyRing;
    auto& trace=io_worker::deadline_trace;
    for(u64 origin:{1000000ULL,0xfffffff0ULL})for(bool masked:{false,true})
    for(bool color:{false,true})for(bool chain:{false,true}) {
        controller=Controller{};Panel panel;Screen mono;
        trace.mark=trace.fault_site=trace.fault_age_us=0;
        clock_now=origin;mask_crc_irq=masked;inject_crc_work=true;
        if(chain){panel.dma_tx_=0;panel.dma_rx_=1;panel.dma_control_=2;}
        std::array<u8,6144> bits{};std::array<u8,768> tiles{};tiles.fill(0x12);
        if(color) {
            mk61_service_color_frame f{};f.pixels=bits.data();f.tiles=tiles.data();
            f.pixel_bytes=bits.size();f.tile_bytes=tiles.size();f.width=256;f.height=192;
            f.x=32;f.y=64;f.format=MK61_COLOR_TILE1;f.background=0x1234;
            f.palette[1]=0x001f;f.palette[2]=0xf800;
            require(panel.color(MK61_COLOR_PRESENT,&f)==1,"fault-vector color frame accepted");
        }else {for(auto& byte:mono.pixels)byte=0x69;require(panel.flush(mono),"fault-vector mono frame accepted");}
        controller.run();
        require(!inject_crc_work && !trace.mark,"actual frame restored outer publication");
        require(injected_pwm_result==(masked?DutyRing::LATE:DutyRing::REFILLED),"750us IRQ mask is observable; enabled work can preempt");
        require(trace.fault_site==(masked?WorkerDeadlineTrace::LCD_CRC:0),"nested CRC identifies exact injected boundary");
        require(!masked || trace.fault_age_us>=750,"record IRQ delay without changing timestamp");
        if(color) {
            for(unsigned y=0;y<320;++y)for(unsigned x=0;x<320;++x)
                require(controller.colors[y*320+x]==(x>=32 && x<288 && y>=64 && y<256?0x001f:0x1234),"injected boundary preserves every color pixel");
        }else require(controller.visible(mono),"injected boundary preserves every mono pixel");
    }
    trace.mark=trace.fault_site=trace.fault_age_us=0;clock_now=1000000;
    {io_worker::FrameDeadlineScope parent(WorkerDeadlineTrace::FRAME);
     io_worker::frame_trace_core=0;
     {io_worker::FrameDeadlineScope ignored(WorkerDeadlineTrace::LCD_CRC);clock_now+=50;
      trace.audio_fault(u32(clock_now));require(trace.fault_site==WorkerDeadlineTrace::FRAME,"core0 cannot replace core1 marker");}
     io_worker::frame_trace_core=1;}
    require(!trace.mark,"ignored core0 scope leaves core1 publication alone");
    std::puts("Actual Panel frame diagnostics:16 mono/color/chain/wrap vectors preserve every pixel; enabled750us work preempts, masked750us remains LATE at nested CRC; core0 never changes core1 trace PASS");
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
        try { shell_theme_session(chain); }
        catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel shell palette FAIL: %s\n",error.what()); }
        try { color_session(chain); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel color FAIL: %s\n",error.what()); }
    }
    try { color_clock_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel clock FAIL: %s\n",error.what()); }
    try { external_clock_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel power clock FAIL: %s\n",error.what()); }
    try { input_response_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel input timing FAIL: %s\n",error.what()); }
    try { color_inversion_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel inversion FAIL: %s\n",error.what()); }
    try { color_pages_session(); } catch(const std::exception& error) { ++failed;std::fprintf(stderr,"Panel pages FAIL: %s\n",error.what()); }
    try {frame_deadline_session();}catch(const std::exception& error){++failed;std::fprintf(stderr,"Frame IRQ diagnostics FAIL: %s\n",error.what());}
    return failed?1:0;
}
