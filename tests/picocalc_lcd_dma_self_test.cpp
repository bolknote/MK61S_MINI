// Production DMA configuration/fill methods, with a paced host SPI endpoint.
#include "rust_types.h"
#include "lcd_update.hpp"
#include "lcd_scroll.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <vector>
#define MK61_PICOCALC_SCREEN_HPP
namespace picocalc {
struct KeyEvent;
class Screen { public: static constexpr unsigned WIDTH=lcd::WIDTH,HEIGHT=lcd::HEIGHT,BYTES=lcd::BYTES; };
}
#define private public
#include "hardware.hpp"
#undef private
namespace picocalc {
namespace {
struct Config {
    unsigned size=0,dreq=0,chain=0;
    bool read_increment=false,write_increment=false,quiet=false;
};
struct Channel { Config config;const void* read=nullptr;volatile void* write=nullptr;unsigned count=0;bool busy=false; };
std::array<Channel,3> channels{};
struct Spi { u32 dr=0; } spi;
constexpr int spi1=1,DMA_SIZE_16=1;
u16 scanlines[lcd::STRIP_ROWS*Screen::WIDTH];
std::vector<u16> wire;
unsigned services=0,starts=0,aborts=0;
u64 now=0,max_service_gap=0,last_service=0;
bool stall=false,audio_active=false;
Config dma_channel_get_default_config(unsigned ch) { Config c;c.chain=ch;return c; }
void channel_config_set_transfer_data_size(Config* c,unsigned value) { c->size=value; }
void channel_config_set_dreq(Config* c,unsigned value) { c->dreq=value; }
void channel_config_set_read_increment(Config* c,bool value) { c->read_increment=value; }
void channel_config_set_write_increment(Config* c,bool value) { c->write_increment=value; }
void channel_config_set_chain_to(Config* c,unsigned value) { c->chain=value; }
void channel_config_set_irq_quiet(Config* c,bool value) { c->quiet=value; }
unsigned spi_get_dreq(int,bool tx) { return tx?11:12; }
Spi* spi_get_hw(int) { return &spi; }
bool spi_is_busy(int) { return false; }
void tight_loop_contents() { assert(false); }
u64 time_us_64() { return now; }
u64 make_timeout_time_us(unsigned n) { return now+n; }
void best_effort_wfe_or_timeout(u64 until) { now=until; }
void dma_channel_configure(unsigned ch,const Config* config,volatile void* target,const void* source,unsigned count,bool start) {
    assert(ch<channels.size() && !start);channels[ch]={*config,source,target,count,false};
}
void dma_channel_set_read_addr(unsigned ch,const void* source,bool start) { assert(!start);channels[ch].read=source; }
void dma_channel_set_trans_count(unsigned ch,unsigned count,bool start) { assert(!start);channels[ch].count=count; }
bool dma_channel_is_busy(unsigned ch) { return channels[ch].busy; }
void progress() {
    auto& tx=channels[0];auto& rx=channels[1];
    if(!tx.busy || stall) return;
    assert(tx.count==rx.count && tx.config.size==DMA_SIZE_16 && rx.config.size==DMA_SIZE_16);
    assert(tx.config.dreq==11 && rx.config.dreq==12 && !tx.config.write_increment && !rx.config.write_increment);
    const unsigned n=tx.count<128?tx.count:128;const auto* source=static_cast<const u16*>(tx.read);
    for(unsigned i=0;i<n;++i) wire.push_back(source[tx.config.read_increment?i:0]);
    if(tx.config.read_increment) tx.read=source+n;
    tx.count-=n;rx.count-=n;tx.busy=rx.busy=tx.count!=0;
}
void dma_start_channel_mask(u32 mask) {
    assert(mask==3 && channels[0].count==channels[1].count);
    channels[0].busy=channels[1].busy=true;++starts;
}
int spi_write16_blocking(int,const u16* pixels,unsigned count) {
    wire.insert(wire.end(),pixels,pixels+count);return count;
}
}
namespace m3_audio { bool transport_active() { return audio_active; } }
namespace io_worker {
void timed_wait(unsigned us) { best_effort_wfe_or_timeout(make_timeout_time_us(us)); }
void service() {
    ++services;
    const u64 gap=now-last_service;if(gap>max_service_gap)max_service_gap=gap;
    last_service=now;progress();
}
void wait_for_progress();
}
namespace dma_support {
void enable_irq(unsigned) {}
bool wait(unsigned first,int second) {
    assert(first==0 && second==1);while(channels[0].busy) progress();return true;
}
}
void Panel::abort_dma() { channels[0].busy=channels[1].busy=false;dma_irq_ready_=false;++aborts; }
#include "picocalc_lcd_dma_production.inc"
}
int main() {
    using namespace picocalc;
    Panel panel;panel.dma_tx_=0;panel.dma_rx_=1;panel.dma_control_=2;
    // Arbitrary, unequal component bytes; fills do not rely on grayscale.
    for(u16 color:{0x1234,0xF81F,0x0000,0xFFFF}) {
        wire.clear();const unsigned before=starts;
        assert(panel.transfer_fill(color,319,317));
        assert(starts==before+1 && wire.size()==319*317 && services>0 && !panel.dma_irq_ready_);
        for(auto pixel:wire) assert(pixel==color);
        // A fill's non-incrementing DMA config must never leak into an image.
        wire.clear();const u16 pixels[]={0x0102,0x0304,0xA5B6,0xFFFF};
        panel.start_scanline(pixels,4);assert(panel.finish_scanline());
        assert(wire==std::vector<u16>(pixels,pixels+4) && channels[0].config.read_increment);
        panel.configure_dma();assert(channels[0].config.chain==2 && channels[0].config.quiet);
    }
    stall=true;wire.clear();const u64 before=now;
    assert(!panel.transfer_fill(0xAAAA,320,320));
    assert(now-before==1000000 && aborts==1 && !panel.dma_irq_ready_ && !channels[0].busy && !channels[1].busy);
    stall=false;assert(panel.transfer_fill(0xABCD,3,5));
    // The actual LCD fill loop and production worker wait share the CPU with
    // M3 UART. No DMA completion IRQ arrives during a constant long fill.
    audio_active=true;max_service_gap=0;last_service=now;
    assert(panel.transfer_fill(0x1234,320,320));
    assert(max_service_gap<=50 && max_service_gap>0);
    audio_active=false;max_service_gap=0;last_service=now;
    assert(panel.transfer_fill(0x1234,320,320));
    assert(max_service_gap==1000);
    Panel fallback;wire.clear();assert(fallback.transfer_fill(0x5678,7,11));
    assert(wire.size()==77);for(auto pixel:wire) assert(pixel==0x5678);
    puts("LCD production DMA: arbitrary RGB565 constant fill, serviced wait, bounded timeout, increment/chain restoration and no-DMA fallback PASS");
}
