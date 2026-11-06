#include "cosmic_clock.hpp"
#include "cosmic_clock_plan.hpp"
#include "audio_stream.hpp"
#include "io_worker.hpp"
#include "psram.hpp"
#include "script.hpp"
#include "terminal_core.hpp"
#include "hardware/clocks.h"
#include "hardware/pll.h"
#include "hardware/resets.h"
#include "hardware/structs/clocks.h"
#include "hardware/structs/ssi.h"
#include "hardware/sync.h"
#include "hardware/vreg.h"
#include "hardware/watchdog.h"
#include "pico/flash.h"
#include "pico/stdlib.h"
#include "tusb.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>
namespace picocalc::cosmic_clock {
namespace {
Lease lease;
alarm_id_t timeout_alarm=0;
bool(*is_idle)()=nullptr;
uint32_t transitions=0;
bool switched=false;
bool bus_cleared=false;
AudioClock audio_clock;
[[noreturn]] void reset_to125(){watchdog_reboot(0,0,0);while(true)tight_loop_contents();}
[[maybe_unused]] int64_t expire(alarm_id_t,void*) {
    // Core1 completes the current I2C STOP before resetting the master. If a
    // peripheral cannot finish, the existing8s watchdog remains independent.
    io_worker::drain();reset_to125();
}
uint32_t measure(uint32_t source) {
    const uint64_t end=time_us_64()+50000;
    while(clocks_hw->fc0.status&CLOCKS_FC0_STATUS_RUNNING_BITS)if(time_us_64()>=end)return 0;
    clocks_hw->fc0.ref_khz=clock_get_hz(clk_ref)/1000;
    clocks_hw->fc0.interval=10;clocks_hw->fc0.min_khz=0;clocks_hw->fc0.max_khz=UINT32_MAX;
    clocks_hw->fc0.src=source;
    while(!(clocks_hw->fc0.status&CLOCKS_FC0_STATUS_DONE_BITS))if(time_us_64()>=end)return 0;
    return clocks_hw->fc0.result>>CLOCKS_FC0_RESULT_KHZ_LSB;
}
bool healthy(uint32_t target) {
    const uint32_t khz=measure(CLOCKS_FC0_SRC_VALUE_CLK_SYS);
    const Plan* plan=find(target);
    return clock_get_hz(clk_sys)==target*1000000 && clock_get_hz(clk_usb)==USB_HZ &&
        clock_get_hz(clk_peri)==PERI_HZ && ssi_hw->baudr==4 && plan &&
        psram::diagnostic_clock_divider256()==plan->pio_div256 && khz && khz+100>=target*1000 && khz<=target*1000+100;
}
void __no_inline_not_in_flash_func(write_clock)(void* raw) {
    // USB controller is held in reset; the SDK's temporary48MHz step cannot
    // encounter RP2040-E16. XIP stays enabled and never exceeds62.5MHz.
    const auto& plan=*(const Plan*)raw;
    set_sys_clock_pll(plan.vco_hz,plan.postdiv1,plan.postdiv2);
}
struct Hardware {
    bool foreground=false;
    bool idle(){const auto tone=script::tone_status();return (foreground || (is_idle && is_idle())) && !audio_stream::active() && !tone.wrap && !tone.software;}
    void stop_click(){audio_stream::stop_key_click();}
    void drain(){io_worker::drain();}
    bool pio(uint32_t div){return psram::diagnostic_clock_divider(div);}
    void disconnect(){tud_disconnect();}
    bool deinit_usb(){return tud_deinit(0);}
    void hold_usb_reset(){reset_block(RESETS_RESET_USBCTRL_BITS);}
    void detach_delay(){sleep_ms(200);}
    bool change_clock(const Plan& plan){
        if(plan.mhz>125){vreg_set_voltage(VREG_VOLTAGE_1_20);busy_wait_us_32(1000);}
        return flash_safe_execute(write_clock,(void*)&plan,50)==PICO_OK;
    }
    bool healthy(uint32_t mhz){
        if(!cosmic_clock::healthy(mhz))return false;
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
        if(mhz==125){vreg_set_voltage(VREG_VOLTAGE_1_10);busy_wait_us_32(1000);}
#endif
        return true;
    }
    void release_usb_reset(){unreset_block_wait(RESETS_RESET_USBCTRL_BITS);}
    bool init_usb(){const tusb_rhport_init_t init{TUSB_ROLE_DEVICE,TUSB_SPEED_FULL};return tusb_init(0,&init);}
    void connect(){tud_connect();}
    [[noreturn]] void reboot(){reset_to125();}
};
struct Reset {
    Writer write;void* context;
    void stop_click(){audio_stream::stop_key_click();}
    void drain(){io_worker::drain();}
    void prepare_psram(){psram::prepare_reset();}
    void reply(){constexpr char line[]="CCEND reboot_to=125\n";write(context,line,sizeof(line)-1);}
    void arm_reset(){watchdog_reboot(0,0,50);}
    void spin(){tight_loop_contents();}
};
struct I2cPins {
    static constexpr unsigned SDA=PICO_DEFAULT_I2C_SDA_PIN,SCL=PICO_DEFAULT_I2C_SCL_PIN;
    void init(){for(unsigned pin:{SDA,SCL}){gpio_init(pin);gpio_pull_up(pin);gpio_put(pin,false);}}
    void release_sda(){gpio_set_dir(SDA,GPIO_IN);}
    void release_scl(){gpio_set_dir(SCL,GPIO_IN);}
    void low_sda(){gpio_set_dir(SDA,GPIO_OUT);}
    void low_scl(){gpio_set_dir(SCL,GPIO_OUT);}
    bool sda_high(){return gpio_get(SDA);}
    bool scl_high(){return gpio_get(SCL);}
    void delay(){busy_wait_us_32(50);}
};
bool apply(uint32_t mhz,bool foreground=false) {
    const Plan* plan=find(mhz),*old=find(clock_get_hz(clk_sys)/1000000);
    if(!plan || !old)return false;
    Hardware hardware;hardware.foreground=foreground;
    if(!transition(hardware,*old,*plan))return false;
    ++transitions;return true;
}
uint32_t hash(uint32_t h,const uint8_t* data,unsigned size){while(size--)h=(h^*data++)*16777619U;return h;}
int nibble(char c){return c>='0'&&c<='9'?c-'0':c>='A'&&c<='F'?c-'A'+10:c>='a'&&c<='f'?c-'a'+10:-1;}
bool usb_probe(const char* args,Writer write,void* context) {
    usize sequence=0;char encoded[65];
    if(!terminal_core::parse_unsigned(args,10,UINT32_MAX,sequence) ||
       !terminal_core::parse_token(args,encoded,sizeof(encoded)) || !terminal_core::at_end(args) || std::strlen(encoded)!=64)return false;
    uint8_t received[32];
    for(unsigned i=0;i<32;++i){const int a=nibble(encoded[i*2]),b=nibble(encoded[i*2+1]);if(a<0||b<0)return false;received[i]=uint8_t(a*16+b);}
    const uint32_t rx=hash(2166136261U,received,sizeof(received));uint32_t rng=rx^sequence,tx=2166136261U;
    char line[128];constexpr char digits[]="0123456789ABCDEF";
    for(unsigned at=0;at<2048;at+=32) {
        uint8_t data[32];char hex[65];
        for(unsigned i=0;i<32;++i){rng=rng*1664525U+1013904223U;data[i]=uint8_t(rng>>24);hex[i*2]=digits[data[i]>>4];hex[i*2+1]=digits[data[i]&15];}
        hex[64]=0;tx=hash(tx,data,sizeof(data));
        const int n=std::snprintf(line,sizeof(line),"CCDATA at=%u %s\n",at,hex);write(context,line,(unsigned)n);
    }
    const int n=std::snprintf(line,sizeof(line),"CCUSB seq=%lu rx=%08lX tx=%08lX bytes=2048 usb=%lu\n",
        (unsigned long)sequence,(unsigned long)rx,(unsigned long)tx,(unsigned long)clock_get_hz(clk_usb));write(context,line,(unsigned)n);return true;
}
}
void bootstrap() {
    // USB is not initialized yet. Keep its PLL/output at stock48MHz.
    // boot2 CLKDIV4 keeps XIP31.25/50/62.5MHz, never above stock62.5.
#if defined(MK61_PICOCALC_COSMIC_CLOCK_DIAG) && MK61_PICOCALC_COSMIC_CLOCK_DIAG
    vreg_set_voltage(VREG_VOLTAGE_1_20);
#else
    vreg_set_voltage(VREG_VOLTAGE_1_10);
#endif
    busy_wait_us_32(1000);
    clock_configure_undivided(clk_peri,0,CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLKSRC_PLL_USB,PERI_HZ);
    I2cPins pins;bus_cleared=clear_i2c(pins);
}
void idle_check(bool(*predicate)()){is_idle=predicate;}
uint32_t pwm_divider16(){const Plan* p=find(clock_get_hz(clk_sys)/1000000);return p?p->pwm_div16:20;}
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
namespace {
struct AudioBackend {
    bool switch_to(uint32_t mhz){return apply(mhz,true);}
    [[noreturn]] void reboot(){reset_to125();}
};
}
bool audio_begin(){if(get_core_num()!=0)return false;AudioBackend backend;return audio_clock.begin(backend);}
void audio_end(){if(get_core_num()!=0)return;AudioBackend backend;audio_clock.end(backend);}
#endif
bool command(const char* args,Writer write,void* context) {
    if(!write)return false;
    args=terminal_core::skip_spaces(args);
    if(!std::strncmp(args,"echo ",5))return usb_probe(args+5,write,context);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    // Production clock ownership belongs to the audio stream. A diagnostic
    // lease must never reset an interactive game after105 seconds.
    if(std::strcmp(args,"status"))return false;
#else
    if(!std::strncmp(args,"begin ",6)) {
        args+=6;usize mhz=0;
        if(!terminal_core::parse_unsigned(args,10,250,mhz) || !terminal_core::at_end(args) ||
           !is_idle || !is_idle() || !lease.arm(mhz,time_us_64()))return false;
        timeout_alarm=add_alarm_in_ms(LEASE_MS,expire,nullptr,true);
        if(timeout_alarm<=0){lease.clear();return false;}
        switched=false;
        char line[96];const int n=std::snprintf(line,sizeof(line),"CCARM mhz=%lu lease_ms=%lu usb_hz=48000000\n",(unsigned long)mhz,(unsigned long)LEASE_MS);
        write(context,line,(unsigned)n);return true;
    } else if(!std::strcmp(args,"switch")) {
        if(!lease.active || switched)return false;
        if(!apply(lease.mhz))return false;
        switched=true;
        return true; // Host reconnects and explicitly requests fresh status.
    } else if(!std::strcmp(args,"end")) {
        if(!is_idle || !is_idle())return false;
        Reset reset{write,context};planned_reboot(reset);
    } else if(std::strcmp(args,"status"))return false;
#endif
    const uint32_t cpu=clock_get_hz(clk_sys),khz=measure(CLOCKS_FC0_SRC_VALUE_CLK_SYS),usb=measure(CLOCKS_FC0_SRC_VALUE_CLK_USB);
    const Plan* p=find(cpu/1000000);if(!p)return false;
    const auto ram=psram::statistics();char line[240];
    const int n=std::snprintf(line,sizeof(line),"CCLOCK mhz=%lu measured_khz=%lu usb_hz=%lu usb_khz=%lu peri_hz=%lu sys_div256=%lu pio_div256=%lu pwm_div16=%lu psram_hz=%lu xip_hz=%lu active=%u lease_ms=%lu changes=%lu i2c_clear=%u\n",
        (unsigned long)p->mhz,(unsigned long)khz,(unsigned long)clock_get_hz(clk_usb),(unsigned long)usb,(unsigned long)clock_get_hz(clk_peri),
        (unsigned long)clocks_hw->clk[clk_sys].div,(unsigned long)psram::diagnostic_clock_divider256(),(unsigned long)p->pwm_div16,
        (unsigned long)ram.hz,(unsigned long)(cpu/ssi_hw->baudr),lease.active,(unsigned long)LEASE_MS,(unsigned long)transitions,bus_cleared);
    if(n<0 || (unsigned)n>=sizeof(line))return false;
    write(context,line,(unsigned)n);
    return healthy(p->mhz) && usb>=47900 && usb<=48100;
}
}
