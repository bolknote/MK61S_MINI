// The production main-loop frame block is included verbatim by the runner.
#include "frame_schedule.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using u8=uint8_t;using u32=uint32_t;using u64=uint64_t;
namespace {
u64 clock_us=0,next_frame=0,render_cost=7000;
u64 time_us_64() { return clock_us; }
bool pending=false,host_disk=false,visible=false;
unsigned snapshots=0;
struct Model { char indicator[8]="42"; };
Model display_snapshot() { ++snapshots;return {}; }
bool calculator_visible() { return visible; }
char previous_indicator[8]="42";
struct {
    bool boot=false,changed=true;
    unsigned renders=0,ticks=0,presentations=0;
    u32 tick_at=0;
    void animation_tick(u32 at,u32,u32) { ++ticks;tick_at=at; }
    bool bootloader_pending() const { return boot; }
    void render(Model,bool,void*,void*,int) { ++renders;clock_us+=render_cost; }
    bool presentation_pending() const { return changed; }
    void presented() { ++presentations; }
} screen;
struct {
    bool refresh=false;
    unsigned submissions=0;
    bool needs_refresh() const { return refresh; }
    template<class T> bool flush(const T&) { ++submissions;return true; }
} panel;
struct { bool holds=false;bool holds_frame() const { return holds; } } remote_screen;
struct { bool online() const { return true; } int battery() const { return 0; } } keyboard;
bool panel_ready=true,usb_force_warning_drawn=false;
int ui=0;
struct { bool warning=false;bool usb_force_confirmation() const { return warning; } } services;
}
namespace picocalc {
namespace usb {
struct Counters { u32 reads=0,writes=0,active_read_bytes=0; } counter;
const Counters& counters() { return counter; }
}
namespace files { bool usb_active() { return host_disk; } }
namespace io_worker { bool frame_pending() { return pending; } }
}
void tick(u64 now) {
    clock_us=now;
#include "picocalc_frame_schedule_production.inc"
}
int main() {
    tick(0);assert(screen.renders==1 && next_frame==20000 && clock_us==7000);
    tick(19999);assert(screen.renders==1);
    render_cost=19000;tick(20000);
    assert(screen.renders==2 && next_frame==40000 && clock_us==39000);
    const auto before=snapshots;pending=true;
    tick(40000);tick(100000);
    assert(snapshots==before && screen.renders==2 && next_frame==40000);
    pending=false;tick(101000);
    assert(screen.renders==3 && next_frame==121000); // Newest state, one frame.
    tick(101000);assert(screen.renders==3); // No catch-up queue.
    host_disk=true;picocalc::usb::counter.active_read_bytes=8192;
    tick(121000);assert(screen.renders==3);
    picocalc::usb::counter.active_read_bytes=0;tick(122000);
    assert(screen.renders==4);
    remote_screen.holds=true;tick(142000);assert(screen.renders==4);
    screen.boot=true;tick(143000);assert(screen.renders==5);
    remote_screen.holds=false;screen.boot=false;
    panel_ready=false;tick(163000);assert(screen.renders==5);
    panel_ready=true;screen.changed=false;tick(164000);
    assert(screen.renders==6 && panel.submissions==5); // Identical raster stays put.
    host_disk=true;picocalc::usb::counter.active_read_bytes=8192;
    screen.changed=true;services.warning=true;
    tick(184000);assert(screen.renders==7 && usb_force_warning_drawn);
    tick(204000);assert(screen.renders==7);
    services.warning=false;
    tick(204001);assert(screen.renders==8 && !usb_force_warning_drawn);
    host_disk=false;
    render_cost=0;
    const u64 late=(u64(1)<<32)*1000+70000;tick(late);
    assert(next_frame==late+20000 && screen.tick_at==(u32)(late/1000));
    puts("Production frame cadence: render cost excluded, no hidden snapshots/backlog, USB READ priority, wake/ROM and timer wrap PASS");
}
