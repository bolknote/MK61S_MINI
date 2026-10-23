#include "calculator.hpp"
#include "hardware.hpp"
#include "math_probe.hpp"
#include "screen.hpp"
#include "ui.hpp"
#include "settings.hpp"
#include "storage.hpp"
#include "services.hpp"
#include "usb_diagnostics.hpp"
#include "script.hpp"
#include "m61_platform.hpp"
#include "input.hpp"
#include "clock.hpp"
#include "power.hpp"
#include "buffers.hpp"
#include "usb_screen.hpp"
#include "terminal.hpp"
#include "terminal_command_ids.hpp"
#include "version.hpp"
#include "io_worker.hpp"
#include "console.hpp"
#include "diagnostics.hpp"
#include "firmware.hpp"
#include "language_cache.hpp"
#include "psram.hpp"
#include "external_cache.hpp"
#include "dma_support.hpp"
#include "native_runtime.hpp"
#include "m61_text.hpp"
#include "tusb.h"
#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "hardware/watchdog.h"
#include "pico/bootrom.h"
#include "pico/rand.h"
#include "pico/unique_id.h"
#include "pico/stdlib.h"
#include <cstdio>
#include <cstring>
extern "C" { extern u32 __StackBottom[], __StackTop[]; }

namespace {
picocalc::Calculator calculator;
picocalc::Keyboard keyboard;
picocalc::Panel panel;
picocalc::Screen screen;
picocalc::Ui ui;
picocalc::Services services;
picocalc::Terminal terminal(calculator,services,ui);
picocalc::UsbScreen remote_screen;
picocalc::SleepPolicy power;
picocalc::SleepClocks sleep_clocks;
bool sleep_applied=false;
bool physical_event=false;
bool panel_ready = false;
u32 physical_keys = 0;
u8 last_physical_key = 0;
bool settings_dirty = false;
const char* settings_status = "DEFAULT";
u64 save_at = 0, last_activity = 0;
u64 last_usb_service = 0;
u32 max_usb_gap = 0;
unsigned math_failures = 0;
constexpr u32 FRAME_INTERVAL_US=20000;
constexpr u32 STACK_PATTERN = 0xD52AC37E;
bool calculator_visible() {
    return !services.active() && ui.page()==picocalc::Page::CALCULATOR && !m61_text::display_owned();
}
picocalc::Snapshot display_snapshot() {
    // Text/graphics pages own their entire raster. Reading and formatting all
    // five calculator values cannot change those pixels and stalls the VM.
    return calculator_visible()?calculator.snapshot():picocalc::Snapshot{};
}
void mark_stack() {
    uintptr_t sp;
    __asm volatile("mrs %0, msp" : "=r"(sp));
    for(volatile u32* p = __StackBottom; (uintptr_t)p + 256 < sp; ++p) *p = STACK_PATTERN;
}
u32 used_stack() {
    volatile u32* p = __StackBottom;
    while(p < __StackTop && *p == STACK_PATTERN) ++p;
    return (u32)((uintptr_t)__StackTop - (uintptr_t)p);
}

void tone(u8 volume, unsigned duration = 25) {
    if(volume == 0) return;
    picocalc::script::tone(2000,duration);
}
void wake(u64 now) {
    if(sleep_clocks.active()) {
        sleep_clocks.leave();
        keyboard.clock_changed();
    }
    power.wake(now);
}
void input(u8 code, bool physical) {
    calculator.wake_core();
    power.activity(time_us_64());
    if(power.asleep()) { wake(time_us_64());return; }
    const bool accepted = services.active() ? services.input(code) :
        (ui.page() == picocalc::Page::CALCULATOR && picocalc::script::input(code)) || ui.input(code, calculator) ||
        (!m61_text::calculator_suspended() && calculator.input(code));
    if(accepted) {
        last_activity = time_us_64();
        tone(ui.settings().volume);
        if(physical) { ++physical_keys; last_physical_key = code; }
    }
    calculator.wake_core();
}
void save_settings() {
    if(!settings_dirty) return;
    const bool saved = picocalc::save_device_settings(ui.settings());
    settings_status = saved ? "SAVED" : "ERROR";
    if(saved) settings_dirty = false;
    else save_at = time_us_64() + 5000000;
}

void report(unsigned math_failures) {
    char diagnostic_status[512];
    const unsigned diagnostic_size=picocalc::diagnostics::status_report(diagnostic_status,sizeof(diagnostic_status));
    std::printf("%.*s",(int)diagnostic_size,diagnostic_status);
    const unsigned firmware_size=picocalc::firmware::report(diagnostic_status,sizeof(diagnostic_status));
    std::printf("%.*s",(int)firmware_size,diagnostic_status);
    std::printf("UI_FONT_FAMILY=%u UI_FONT_SIZE=%u UI_FONT_KEY=%08lX\n",
        ui.settings().ui_font_family,ui.settings().ui_font_size,(unsigned long)ui.settings().ui_font_key);
    const auto settings_storage=picocalc::settings_storage_statistics();
    std::printf("SETTINGS_WRITES=%lu SETTINGS_ERASES=%lu SETTINGS_SEQUENCE=%lu\n",
        (unsigned long)settings_storage.writes,(unsigned long)settings_storage.erases,
        (unsigned long)settings_storage.sequence);
    const auto cache=picocalc::language_cache::statistics();
    std::printf("VM_CACHE=RAM+SD BYTES=%u USED=%u RAM_HIT=%lu RAM_MISS=%lu SD_HIT=%lu SD_MISS=%lu COMPILES=%lu STORES=%lu REJECTED=%lu PACKS=%lu THAWS=%lu PACKED=%u\n",
        cache.allocated,cache.used,(unsigned long)cache.ram_hits,(unsigned long)cache.ram_misses,
        (unsigned long)cache.disk_hits,(unsigned long)cache.disk_misses,(unsigned long)cache.compiles,
        (unsigned long)cache.stores,(unsigned long)cache.rejected,
        (unsigned long)cache.packs,(unsigned long)cache.thaws,cache.packed);
    const auto psram=picocalc::psram::statistics();
    const auto external=picocalc::external_cache::statistics();
    std::printf("PSRAM=%s BYTES=%lu ID=%06lX SPI_HZ=%lu READ_BYTES=%lu WRITE_BYTES=%lu ERRORS=%lu MODE=%s QPI_FALLBACKS=%lu READ_BATCHES=%lu WRITE_BATCHES=%lu TAIL_TIMEOUTS=%lu TAIL_STATE=%08lX\n",
        psram.ready?"OK":"UNAVAILABLE",(unsigned long)(psram.ready?picocalc::psram::CAPACITY:0),
        (unsigned long)psram.id,(unsigned long)psram.hz,(unsigned long)psram.read_bytes,
        (unsigned long)psram.write_bytes,(unsigned long)psram.errors,psram.qpi?"QPI":"SPI",(unsigned long)psram.qpi_fallbacks,
        (unsigned long)psram.read_batches,(unsigned long)psram.write_batches,
        (unsigned long)psram.tail_timeouts,(unsigned long)psram.tail_state);
    std::printf("EXT_CACHE=%s VM_HIT=%lu VM_MISS=%lu SD_HIT=%lu SD_MISS=%lu REJECTED=%lu STORES=%lu VM_BYTES=%lu SD_BYTES=%lu EVICTIONS=%lu\n",
        external.ready?"PSRAM":"OFF",(unsigned long)cache.psram_hits,(unsigned long)cache.psram_misses,
        (unsigned long)external.sector_hits,(unsigned long)external.sector_misses,
        (unsigned long)external.rejected,(unsigned long)external.stores,(unsigned long)external.module_bytes,
        (unsigned long)external.sector_bytes,(unsigned long)external.evictions);
    const auto buffers=shared_memory::buffer_statistics();
    const auto app_buffers=services.native_buffer_statistics();
    std::printf("APP_BUFFERS=%lu APP_BUFFER_BYTES=%lu APP_EXTERNAL_BYTES=%lu APP_WINDOWS=%lu\n",
        (unsigned long)app_buffers.count,(unsigned long)app_buffers.bytes,
        (unsigned long)app_buffers.external_bytes,(unsigned long)app_buffers.windows);
    std::printf("BUFFERS=shared SRAM_USED=%lu PSRAM_USED=%lu PSRAM_CAPACITY=%lu LARGEST=%lu ACTIVE=%lu EXTERNAL=%lu PINNED=%lu RECLAIMS=%lu IO_ERRORS=%lu VALID=%u\n",
        (unsigned long)buffers.internal_used,(unsigned long)buffers.external_used,(unsigned long)buffers.external_capacity,
        (unsigned long)buffers.external_largest,(unsigned long)buffers.active,(unsigned long)buffers.external_active,
        (unsigned long)buffers.pinned,(unsigned long)buffers.reclaims,(unsigned long)buffers.io_errors,
        shared_memory::validate_buffer_invariants());
    const auto model = calculator.snapshot();
    std::printf("MK61S PICOCALC PICO-H %s RP2040 %lu MHz\n",
                picocalc::VERSION,(unsigned long)(clock_get_hz(clk_sys) / 1000000));
    std::printf("TERMINAL=%s\n",terminal.raw()?"RAW":"COMMAND");
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
    std::printf("CORE=shared MATH=compact-binary64/owned-M0-IEEE MATH_TEST=%s failures=%u\n",
#else
    std::printf("CORE=shared MATH=compact-binary64/GCC-IEEE-softfloat MATH_TEST=%s failures=%u\n",
#endif
                math_failures ? "FAIL" : "OK", math_failures);
    std::printf("KBD=%s errors=%lu dropped=%lu X=[%s] IP=%02u RUN=%u BUSY=%u\n",
                keyboard.online() ? "OK" : "WAIT", (unsigned long)keyboard.errors(),
                (unsigned long)model.dropped_keys, model.indicator, model.ip, model.running,
                !calculator.idle());
    char raw[INDICATOR_STRING_LENGTH];
    read_stack_register(X, raw, nullptr);
    std::printf("X_RAW=[%s] PANEL_INIT=%u PHYSICAL_KEYS=%lu LAST_PHYSICAL=0x%02X\n",
                raw, panel_ready, (unsigned long)physical_keys, last_physical_key);
    const auto battery=keyboard.battery();
    std::printf("BATTERY_PERCENT=%d BATTERY_CHARGING=%u BATTERY_AVAILABLE=%u BATTERY_ERRORS=%lu\n",
        battery.percent,battery.charging,battery.available,(unsigned long)keyboard.battery_errors());
    std::printf("CONSOLE=%s CONSOLE_SWITCHES=%lu RX_USB=%lu RX_UART=%lu\n",
        picocalc::console::routing.selected()?(picocalc::console::routing.output()==picocalc::console::Channel::USB?"USB":"UART"):"BOOT",
        (unsigned long)picocalc::console::routing.switches(),
        (unsigned long)picocalc::console::routing.received(picocalc::console::Channel::USB),
        (unsigned long)picocalc::console::routing.received(picocalc::console::Channel::UART));
    std::printf("LCD_BKL=%d KBD_BKL=%d\n", keyboard.lcd_backlight(), keyboard.key_backlight());
    std::printf("LCD=ST7365P RGB565 SPI_HZ=%lu FRAMES=%lu\n",
                (unsigned long)panel.spi_hz(), (unsigned long)panel.frames());
    std::printf("LCD_DMA=%u LCD_BYTES=%lu LCD_RECTS=%lu LCD_US=%lu LCD_FULL_FRAMES=%lu LCD_CHAIN=%u LCD_STRIPS=%lu LCD_CHAIN_PAUSES=%lu\n",
        panel.dma(),(unsigned long)panel.last_bytes(),(unsigned long)panel.last_rectangles(),
        (unsigned long)panel.last_us(),(unsigned long)panel.full_frames(),panel.chained_dma(),(unsigned long)panel.strips(),(unsigned long)panel.chain_pauses());
    const auto dma=picocalc::dma_support::statistics();
    const auto sd=picocalc::sd::statistics();
    const auto idle=picocalc::idle_statistics();
    std::printf("SD_DMA=%u READS=%lu WRITES=%lu TRANSFERS=%lu HW_CRC=%lu CRC_ERRORS=%lu\n",
        sd.dma,(unsigned long)sd.reads,(unsigned long)sd.writes,(unsigned long)sd.dma_transfers,
        (unsigned long)sd.hardware_crc,(unsigned long)sd.crc_errors);
    std::printf("EXT_LAYOUT=PACKED VM_ENTRIES=%lu VM_PAYLOAD=%lu VM_USED=%lu SD_SLOTS=%lu SD_STRIDE=536\n",
        (unsigned long)external.module_entries,(unsigned long)external.module_payload,
        (unsigned long)external.module_used,(unsigned long)external.sector_slots);
    std::printf("DMA_WAIT0=%lu DMA_WAIT1=%lu DMA_US0=%lu DMA_US1=%lu DMA_TIMEOUTS=%lu CRC32_HW=%lu CRC_FALLBACK=%lu LCD_ERRORS=%lu\n",
        (unsigned long)dma.waits[0],(unsigned long)dma.waits[1],(unsigned long)dma.sleep_us[0],
        (unsigned long)dma.sleep_us[1],(unsigned long)dma.timeouts,(unsigned long)dma.crc32_calls,
        (unsigned long)dma.crc_fallbacks,(unsigned long)panel.errors());
    std::printf("SD_SINGLE_CMDS=%lu SD_MULTI_CMDS=%lu SD_MULTI_SECTORS=%lu SD_WRITE_FALLBACKS=%lu\n",
        (unsigned long)sd.write_single_commands,(unsigned long)sd.write_multi_commands,
        (unsigned long)sd.write_multi_sectors,(unsigned long)sd.write_fallbacks);
    std::printf("IDLE_WAITS=%lu IDLE_MS=%lu RTC_IRQS=%lu\n",(unsigned long)idle.waits,
        (unsigned long)(idle.wait_us/1000),(unsigned long)picocalc::clock::alarm_interrupts());
    std::printf("CORE_PARKED=%u\n",calculator.parked());
    const auto io=picocalc::io_worker::statistics();
    std::printf("IO_CORE=%u I2C_TRANSACTIONS=%lu UART_BYTES=%lu LCD_PENDING=%u LCD_FRAME_CRC=%08lX\n",
        io.running?1:0,(unsigned long)io.transactions,(unsigned long)io.uart_bytes,
        picocalc::io_worker::frame_pending(),(unsigned long)panel.frame_crc());
    std::printf("UART_WAIT_US=%lu UART_FLUSH_US=%lu UART_FLUSHES=%lu\n",
        (unsigned long)io.uart_wait_us,(unsigned long)io.uart_flush_us,(unsigned long)io.uart_flushes);
    std::printf("UART_DMA=%u IO_IDLE_US=%lu UART_EVENT_WAITS=%lu UART_SLEEP_HOLDS=%lu UART_BAUD=%lu\n",io.uart_dma,(unsigned long)io.idle_us,
        (unsigned long)io.uart_event_waits,(unsigned long)io.uart_sleep_holds,(unsigned long)io.uart_baud);
    std::printf("LCD_SCROLLS=%lu LCD_SCROLL_ROWS=%lu LCD_SCROLL_OFFSET=%u\n",
        (unsigned long)panel.scrolls(),(unsigned long)panel.scrolled_rows(),panel.scroll_offset());
    std::printf("SD=%s SECTORS=%lu USB_DISK=%u FS_ERROR=[%s]\n", picocalc::files::ready() ? "OK" : "WAIT",
        (unsigned long)picocalc::sd::sectors(), picocalc::files::usb_active(), picocalc::files::error());
    const auto& settings = ui.settings();
    std::printf("UI=%s SELECT=%u VIEW=%u LANG=%s MEMORY=%u STEPS=%u SPEED=%s RANDOM=%s FONT=%u/%u SETTINGS=%s\n",
        ui.page_name(), ui.selected(), (unsigned)ui.view(), settings.russian ? "RU" : "EN",
        settings.memory, (unsigned)core_61::program_steps(), settings.classic_speed ? "CLASSIC" : "MAXIMUM",
        settings.random ? "MK61S" : "MK61", settings.calculator_font, settings.ui_font_size, settings_status);
    std::printf("Keys: ? status; m math test; ! USB BOOTSEL; calculator keys per screen.\n");
    std::printf("SERVICE=%s SOURCE=%u DIRTY=%u PATH=[%s] RESULT=[%s]\n", services.page_name(), services.source_size(),
        services.dirty(), services.path(), services.status());
    const auto source_memory=services.source_memory_statistics();
    std::printf("SOURCE_STORAGE=shared BYTES=%u SRAM_BYTES=%u PSRAM_BYTES=%u WINDOW_BYTES=%u\n",
        source_memory.bytes,source_memory.sram_bytes,source_memory.external_bytes,source_memory.window_bytes);
    std::printf("STACK_USED=%lu STACK_BYTES=%lu\n", (unsigned long)used_stack(), (unsigned long)((__StackTop - __StackBottom) * 4));
    const auto& usb = picocalc::usb::counters();
    std::printf("MSC_READ=%lu WRITE=%lu READ_ERROR=%lu WRITE_ERROR=%lu LBA=%lu SCSI=%02X\n", (unsigned long)usb.reads,
        (unsigned long)usb.writes, (unsigned long)usb.read_errors, (unsigned long)usb.write_errors,
        (unsigned long)usb.last_lba, usb.last_scsi);
    std::printf("USB_MAX_GAP_US=%lu\n",(unsigned long)max_usb_gap);
    std::printf("POWER_MODE=%s SYS_HZ=%lu PERI_HZ=%lu PLL_MASK=%u SLEEP_ENTRIES=%lu BATTERY_SLEEPS=%lu SLEEP_CLOCK0=%08lX SLEEP_CLOCK1=%08lX\n",
        sleep_clocks.active() ? sleep_clocks.usb_available() ? "SLEEP_USB" : "SLEEP_BATTERY" : "RUN",
        (unsigned long)clock_get_hz(clk_sys), (unsigned long)clock_get_hz(clk_peri), sleep_clocks.pll_mask(),
        (unsigned long)sleep_clocks.entries(), (unsigned long)sleep_clocks.battery_entries(),
        (unsigned long)clocks_hw->sleep_en0,(unsigned long)clocks_hw->sleep_en1);
    const auto date=picocalc::clock::get();
    std::printf("RUNTIME=%s USB_SCREEN=%s SCREEN_FRAMES=%lu SCREEN_ERRORS=%lu SLEEP=%u RTC=%04d-%02d-%02dT%02d:%02d:%02d RTC_SET=%u RTC_PPM=%d\n",
        services.runtime_name(),remote_screen.attached()?"ATTACHED":remote_screen.enabled()?"OFFER":"OFF",
        (unsigned long)remote_screen.frames(),(unsigned long)remote_screen.errors(),power.asleep(),date.year,date.month,date.day,date.hour,date.minute,date.second,
        picocalc::clock::configured(),picocalc::clock::calibration());
    char script_row[65]; picocalc::script::text_row(0, script_row, sizeof(script_row));
    std::printf("M61_ACTIVE=%u SUSPENDED=%u DISPLAY=%u COLS=%u ROWS=%u FONT=%u TEXT=[%s]\n", m61_text::active(), m61_text::calculator_suspended(), m61_text::display_owned(), picocalc::script::columns(), picocalc::script::rows(), picocalc::script::font_active(), script_row);
    std::printf("MSC_SD_READ_US=%llu COMMANDS=%lu MAX_READ_US=%lu MAX_READ_BYTES=%lu MAX_READ_LBA=%lu ACTIVE_BYTES=%lu ACTIVE_LBA=%lu\n",
        (unsigned long long)usb.sd_read_us, (unsigned long)usb.read_commands, (unsigned long)usb.max_read_us,
        (unsigned long)usb.max_read_bytes, (unsigned long)usb.max_read_lba,
        (unsigned long)usb.active_read_bytes, (unsigned long)usb.active_read_lba);
}
void usb_service() {
    picocalc::diagnostics::Scope measure(picocalc::diagnostics::Point::USB);
    const u64 now=time_us_64();
    if(last_usb_service && now-last_usb_service>max_usb_gap) max_usb_gap=(u32)(now-last_usb_service);
    last_usb_service=now;
    if(sleep_clocks.usb_available()) tud_task_ext(0, false);
    picocalc::diagnostics::feed_watchdog();
    // A native frame has 80 rectangles. Sending one per MK61 microcode cycle
    // makes the idle calculator much slower to mirror than a foreground APP.
    // Drain a bounded burst, yielding immediately to incoming commands/keys.
    const u64 tx_until=time_us_64()+4000;
    for(unsigned packet=0;packet<4096;++packet) {
        remote_screen.tick((u32)(time_us_64()/1000),tud_cdc_connected() && !picocalc::files::usb_active());
        if(!remote_screen.holds_frame() || time_us_64()>=tx_until || tud_cdc_available()) break;
        if(sleep_clocks.usb_available()) tud_task_ext(0,false);
    }
    static u64 next_rtc=0;
    if(now>=next_rtc || picocalc::clock::alarm_pending()) {
        picocalc::clock::service();next_rtc=now+1000000;
        unsigned alarm;
        while(picocalc::clock::take_alarm(alarm)) { wake(now);tone(ui.settings().volume,1000);std::printf("RTC_ALARM=%c\n",'A'+alarm); }
    }
}
bool key_event(picocalc::KeyEvent& event) {
    if(keyboard.poll(event)) { physical_event=true;picocalc::controls::event(event);return true; }
    if(remote_screen.key(event)) { physical_event=false;picocalc::controls::event(event,picocalc::controls::Source::REMOTE);return true; }
    return false;
}
bool service_pump(void*, u8& key) {
    const u64 entered=time_us_64();
    static u64 next_service=0;
    // The VM offers a poll every 32 instructions. Device work needs a
    // bounded wall-clock cadence, not another full USB pass each time.
    if(entered<next_service) return false;
    next_service=entered+1000;
    picocalc::diagnostics::Scope measure(picocalc::diagnostics::Point::PUMP);
    usb_service();
    picocalc::script::service_effects();
    const u64 now = time_us_64();
    static u64 next = 0;
    if(panel_ready && !remote_screen.holds_frame() && !picocalc::io_worker::frame_pending() && now >= next) {
        screen.render(display_snapshot(), keyboard.online(), &ui, &services,keyboard.battery()); panel.flush(screen); next = time_us_64() + FRAME_INTERVAL_US;
    }
    picocalc::KeyEvent event{};
    if(key_event(event) && event.pressed()) {
        key = event.code;
        if(physical_event) { ++physical_keys;last_physical_key=key; } last_activity=now;power.activity(now);return true;
    }
    const bool exclusive=terminal.input_active();
    int c = picocalc::console::read(exclusive,sleep_clocks.usb_available());
    if(c>=0 && picocalc::console::input_usb()) c=remote_screen.receive((u8)c,(u32)(now/1000));
    if(c<0 || !picocalc::console::accept(c,exclusive)) return false;
    if(c == 5) { report(math_failures); return false; }
    terminal.input_source(picocalc::console::input_usb());
    c=terminal.receive((u8)c);
    if(c<0) return false;
    if(c != PICO_ERROR_TIMEOUT) {
        const bool skip=picocalc::console::routing.skip_lf(c);
        if(!skip) {
            key=(u8)c;picocalc::controls::pulse(key,(u32)(now/1000));power.activity(now);
            return true;
        }
    }
    return false;
}
} // namespace

int main() {
    picocalc::initialize_heap();
    picocalc::firmware::enforce();
    picocalc::diagnostics::initialize();
    mark_stack();
    watchdog_enable(8000, true);
    picocalc::diagnostics::watchdog_started(8000);
    const tusb_rhport_init_t usb_init{TUSB_ROLE_DEVICE, TUSB_SPEED_FULL};
    tusb_init(0, &usb_init);
    stdio_init_all();
    sleep_clocks.init();
    picocalc::clock::init();
    remote_screen.init({nullptr,
        [](void*) { return (unsigned)tud_cdc_write_available(); },
        [](void*,const u8* data,unsigned size) { const unsigned n=tud_cdc_write(data,size);tud_cdc_write_flush();return n; },
        [](void*,u8* frame) { screen.render(display_snapshot(),keyboard.online(),&ui,&services,keyboard.battery());screen.logical_frame(ui,services,frame); },
        [](void*) {
            screen.render(display_snapshot(),keyboard.online(),&ui,&services,keyboard.battery());
            if(panel_ready && !power.asleep()) panel.flush(screen);
        },
        [](void*,unsigned x,unsigned page,u8* out,unsigned count) {
            for(unsigned i=0;i<count;++i) {
                u8 bits=0;for(unsigned y=0;y<8;++y) if(screen.pixel(x+i,page*8+y)) bits|=(u8)(1U<<y);out[i]=bits;
            }
        }});
    // Process enumeration before the core's boot probes and the card's
    // potentially slow power-up. No USB worker runs in an interrupt: MSC
    // callbacks and FatFs must stay on the same foreground core.
    const u64 enumerate_until = time_us_64() + 500000;
    while(time_us_64() < enumerate_until) { tud_task_ext(0, false); picocalc::diagnostics::feed_watchdog(); }
    keyboard.init();
    picocalc::psram::init();picocalc::buffers::init();picocalc::external_cache::init();
    calculator.init();
    picocalc::Settings settings;
    if(picocalc::load_device_settings(settings)) settings_status = "LOADED";
    ui.init(settings);
    services.set_ui(ui);
    picocalc::clock::calibrate(settings.rtc_ppm);
    picocalc::clock::restore_alarms(settings.alarm_epoch,settings.alarm_flags);
    services.set_pump(service_pump, nullptr);
    terminal.init({nullptr,
        [](void*,const char* text,unsigned n) { picocalc::console::write(text,n); },
        [](void*) { usb_service();picocalc::script::service_effects();if(!m61_text::calculator_suspended()) calculator.tick(m61_text::active() && m61_text::display_owned(),true); },
        [](void*,u8 id,const char* args) {
            if(id==CMD_IDENTITY) {
                char uid[2*PICO_UNIQUE_BOARD_ID_SIZE_BYTES+1];pico_get_unique_board_id_string(uid,sizeof(uid));
                std::printf("MK61S PicoCalc %s CPU=RP2040 UID=%s FLASH=2097152\n",picocalc::VERSION,uid);return true;
            }
            if(id==CMD_USB_SCREEN) {
                if(*args && std::strcmp(args,"on") && std::strcmp(args,"off")) return false;
                remote_screen.enable(std::strcmp(args,"off")!=0);ui.calculator_page();return true;
            }
            if(id==CMD_DFU || id==CMD_RESET) {
                if(id==CMD_DFU && !std::strcmp(args,"status")) {
                    char text[512];const unsigned n=picocalc::firmware::report(text,sizeof(text),true);
                    std::puts("BOOTLOADER=RP2040 ROM UF2");std::printf("%.*s",(int)n,text);return true;
                }
                if((id==CMD_DFU && *args) || (id==CMD_RESET && std::strcmp(args,"now")) || services.running() || picocalc::files::usb_active()) return false;
                save_settings();picocalc::io_worker::drain();stdio_flush();picocalc::psram::prepare_reset();
                if(id==CMD_DFU) reset_usb_boot(0,0);else watchdog_reboot(0,0,10);
                for(;;) tight_loop_contents();
            }
            if(id==CMD_DISPLAY) {
                if(!std::strcmp(args,"buffers")) {
                    if(services.active() || m61_text::active() || picocalc::files::usb_active() ||
                       remote_screen.attached() || !calculator.idle() || core_61::is_RUN()) return false;
                    const auto result=picocalc::buffers::self_test(usb_service);
                    std::printf("BUFFER_TEST=%s BYTES=%lu ALLOCATED=%lu WRITE_US=%lu READ_US=%lu MODE=%s\n",
                        result.passed?"PASS":"FAIL",(unsigned long)result.bytes,(unsigned long)result.allocation,
                        (unsigned long)result.write_us,(unsigned long)result.read_us,
                        picocalc::psram::statistics().qpi?"QPI":"SPI");
                    return result.passed;
                }
                if(!std::strcmp(args,"test")) {
                    if(services.active() || m61_text::active() || picocalc::files::usb_active() ||
                       remote_screen.attached() || !calculator.idle() || core_61::is_RUN()) return false;
                    picocalc::io_worker::drain();
                    picocalc::external_cache::suspend();picocalc::language_cache::discard();
                    if(shared_memory::buffer_statistics().external_active) {
                        picocalc::external_cache::init();return false;
                    }
                    const u64 started=time_us_64();
                    const bool memory=picocalc::psram::self_test(usb_service);
                    const u32 crc=picocalc::dma_support::crc32((const u8*)"123456789",9);
                    const bool cached=picocalc::external_cache::init();
                    std::printf("HARDWARE_TEST=%s PSRAM_BYTES=%lu PSRAM_US=%lu CRC32=%08lX CACHE=%u\n",
                        memory && crc==0xCBF43926U && cached?"PASS":"FAIL",
                        (unsigned long)picocalc::psram::CAPACITY,(unsigned long)(time_us_64()-started),
                        (unsigned long)crc,cached);
                    return memory && crc==0xCBF43926U && cached;
                }
                if(!std::strcmp(args,"reinit")) { panel_ready=false;return true; }
                if(!std::strcmp(args,"on")) { wake(time_us_64());return true; }
                if(!std::strcmp(args,"off") && !services.active() && !m61_text::active() && calculator.idle() && !core_61::is_RUN()) { power.sleep();return true; }
                if(!*args || !std::strcmp(args,"status")) { report(math_failures);return true; }
                return false;
            }
            if(id==CMD_VFAT_LOG) { report(math_failures);return !*args; }
            if(id==CMD_DISASM) { if(*args) return false;ui.program_view();return true; }
            return false;
        }});
    picocalc::script::attach(calculator, services);
    picocalc::script::text_profile({settings.text_rows,settings.text_width,settings.text_height,settings.text_gap});
    picocalc::script::memory_mode(settings.memory);
    calculator.set_memory_mode(settings.memory);
    core_61::configure_random_seed(settings.random != 0, get_rand_64());
    math_failures = picocalc::math_self_test();
    report(math_failures);
    (void)picocalc::files::mount();
    (void)picocalc::diagnostics::persist_crash();
    u64 next_frame = 0;
    u64 next_classic_step = 0;
    bool foreground_was_active=false;
    u64 usb_retry = time_us_64() + 3000000;
    last_activity = time_us_64();
    power.activity(last_activity);
    u32 settings_revision = ui.settings_revision();
    u8 applied_memory = settings.memory, applied_random = settings.random;
    u8 applied_lcd = 0, applied_keys = 255;
    picocalc::Settings applied_profile=settings;
    char previous_indicator[INDICATOR_STRING_LENGTH] = {};
    bool drawn_usb = false, drawn_ejected = false;
    u64 drawn_activity = 0;
    for(;;) {
        picocalc::diagnostics::context(power.asleep()?picocalc::diagnostics::State::SLEEP:
            picocalc::files::usb_active()?picocalc::diagnostics::State::USB_DISK:
            m61_text::active()?picocalc::diagnostics::State::M61:
            ui.page()==picocalc::Page::CALCULATOR?picocalc::diagnostics::State::CALCULATOR:
            picocalc::diagnostics::State::MENU);
        if(sleep_clocks.refresh()) keyboard.clock_changed();
        usb_service();
        if(sleep_clocks.usb_available() && !tud_mounted() && time_us_64() >= usb_retry) {
            tud_disconnect();
            sleep_ms(10);
            tud_connect();
            usb_retry = time_us_64() + 5000000;
        }
        picocalc::KeyEvent event{};
        if(key_event(event) && event.pressed()) {
            input(event.code,physical_event);
        }
        if(!keyboard.online()) panel_ready = false;
        if(keyboard.online() && !panel_ready && !keyboard.transaction_pending()) {
            if(!picocalc::psram::ready() && picocalc::psram::init()) picocalc::external_cache::init();
            keyboard.backlight(ui.settings().lcd_backlight, ui.settings().key_backlight);
            applied_lcd = ui.settings().lcd_backlight;
            applied_keys = ui.settings().key_backlight;
            panel.init();
            panel_ready = true;
            next_frame = 0;
            std::puts("PICOCALC PANEL INITIALIZED KBD=OK");
        }
        // Raw keys keep the original short burst. A shell line must not need
        // thirty full emulator cycles before it can acknowledge a file chunk.
        // Both modes have a fixed bound and yield to the core every loop.
        const unsigned input_budget=terminal.raw()?8U:terminal_core::INPUT_CAPACITY;
        for(unsigned i = 0; i < input_budget; ++i) {
            const bool exclusive=terminal.input_active();
            int c = picocalc::console::read(exclusive,sleep_clocks.usb_available());
            if(c == PICO_ERROR_TIMEOUT) break;
            if(picocalc::console::input_usb()) c=remote_screen.receive((u8)c,millis());
            if(c<0 || !picocalc::console::accept(c,exclusive)) continue;
            if(c == 5 || (terminal.raw() && !services.active() && (c == '?' || c == 'm'))) {
                if(c == 'm') math_failures = picocalc::math_self_test();
                report(math_failures);
            } else if(c == '!' && terminal.raw() && !services.active()) {
                std::puts("Entering RP2040 USB BOOTSEL");
                picocalc::io_worker::drain();stdio_flush();picocalc::psram::prepare_reset();
                reset_usb_boot(0, 0);
            } else {
                terminal.input_source(picocalc::console::input_usb());
                const int key=terminal.receive((u8)c);
                const bool skip=picocalc::console::routing.skip_lf(c);
                if(key>=0 && !skip) { picocalc::controls::pulse((u8)key,millis());input((u8)key,false); }
                else if(c<0x1D || c>0x1F) { power.activity(time_us_64());if(power.asleep()) wake(time_us_64()); }
            }
            if(c>=0x1D && c<=0x1F) break;
            if(terminal.pending()) break;
        }
        terminal.tick();
        const u64 now = time_us_64();
        if(power.asleep()!=sleep_applied && panel_ready && !keyboard.transaction_pending()) {
            sleep_applied=power.asleep();
            if(sleep_applied) {
                save_settings();picocalc::script::tone(0,0);picocalc::script::led_stop();
                panel.sleep(true);keyboard.backlight(0,0);
                keyboard.idle(true);sleep_clocks.enter();keyboard.clock_changed();
            } else {
                sleep_clocks.leave();keyboard.clock_changed();keyboard.idle(false);
                panel.sleep(false);keyboard.backlight(ui.settings().lcd_backlight,ui.settings().key_backlight);next_frame=0;
            }
        }
        if(power.asleep()) {
            u64 deadline=time_us_64()+(sleep_clocks.usb_available()?1000:80000);
            if(keyboard.next_poll()>time_us_64() && keyboard.next_poll()<deadline) deadline=keyboard.next_poll();
            picocalc::idle_until(deadline);continue;
        }
        ui.sync_alarms();
        if(ui.settings_revision() != settings_revision) {
            settings_revision = ui.settings_revision();
            settings_dirty = true;
            settings_status = "PENDING";
            save_at = now + 1000000;
            picocalc::clock::calibrate(ui.settings().rtc_ppm);
        }
        const auto& current = ui.settings();
        if(current.text_rows!=applied_profile.text_rows || current.text_width!=applied_profile.text_width ||
            current.text_height!=applied_profile.text_height || current.text_gap!=applied_profile.text_gap) {
            picocalc::script::text_profile({current.text_rows,current.text_width,current.text_height,current.text_gap});
            applied_profile=current;
        }
        if(applied_memory != current.memory) {
            m61_text::cancel();
            calculator.set_memory_mode(current.memory);
            picocalc::script::memory_mode(current.memory);
            applied_memory = current.memory;
        }
        if(applied_random != current.random) {
            core_61::configure_random_seed(current.random != 0, get_rand_64());
            applied_random = current.random;
        }
        if(keyboard.online() && !keyboard.transaction_pending() &&
           (applied_lcd != current.lcd_backlight || applied_keys != current.key_backlight)) {
            keyboard.backlight(current.lcd_backlight, current.key_backlight);
            applied_lcd = current.lcd_backlight;
            applied_keys = current.key_backlight;
        }
        picocalc::script::service_effects();
        const bool foreground_active=services.active() || m61_text::active();
        if(foreground_active!=foreground_was_active) { calculator.wake_core();foreground_was_active=foreground_active; }
        if(picocalc::files::usb_active() || m61_text::calculator_suspended()) {
            // A single host READ can span thousands of sectors. Running one
            // whole MK61 microcode step between each 512-byte USB packet
            // exceeds the host's SCSI deadline on RP2040. USB owns this loop.
            next_classic_step = 0;
        } else if(current.classic_speed && core_61::is_RUN() && calculator.idle()) {
            if(!next_classic_step) next_classic_step = now + 1153846; // Shared CLASSIC cadence: 15/13 s.
            if(now >= next_classic_step) { calculator.tick(); next_classic_step = now + 1153846; }
        } else { next_classic_step = 0; calculator.tick(m61_text::active() && m61_text::display_owned(),true); }
        if(current.idle_signal && now - last_activity >= 300000000ULL) {
            tone(current.volume, 150);
            last_activity = now;
        }
        if(settings_dirty && now >= save_at && calculator.idle() && !core_61::is_RUN() && !picocalc::files::usb_active()) save_settings();
        services.tick();
        if(services.take_calculator_request()) ui.calculator_page();
        if(!picocalc::files::usb_active() && !services.active()) {
            picocalc::diagnostics::Scope measure(picocalc::diagnostics::Point::M61);
            m61_text::service();
        }
        static bool script_was_active = false;
        if(m61_text::active() && !script_was_active && !services.active()) ui.calculator_page();
        script_was_active = m61_text::active();
        const auto action = ui.take_action();
        if(action==picocalc::Action::USB_SCREEN) {
            remote_screen.enable(!remote_screen.enabled());ui.calculator_page();
        } else if(action==picocalc::Action::SLEEP) {
            if(!core_61::is_RUN() && calculator.idle() && !services.active() && !m61_text::active() && !picocalc::files::usb_active() && !remote_screen.attached()) power.sleep();
        } else if(action == picocalc::Action::RESET) {
            m61_text::cancel();
            calculator.init();
            ui.init();
            picocalc::clock::restore_alarms(ui.settings().alarm_epoch,ui.settings().alarm_flags);
            settings_revision = ui.settings_revision();
            settings_dirty = true;
            save_settings();
        } else if(action >= picocalc::Action::USB_DISK) {
            services.open(action, ui.settings().russian, calculator);
            if(picocalc::files::usb_active()) { max_usb_gap = 0; last_usb_service = time_us_64(); }
        } else if(action != picocalc::Action::NONE) {
            save_settings();
            picocalc::psram::prepare_reset();
            if(action == picocalc::Action::BOOTLOADER) reset_usb_boot(0, 0);
            else watchdog_reboot(0, 0, 10);
            for(;;) tight_loop_contents();
        }
        if(power.due(time_us_64(),current.sleep_minutes,core_61::is_RUN() || !calculator.idle() || services.active() || m61_text::active() || picocalc::files::usb_active() || remote_screen.attached())) power.sleep();
        if(now >= next_frame) {
            const bool usb = picocalc::files::usb_active(), ejected = picocalc::files::usb_ejected();
            // The USB instructions are static. Redraw only on a key or eject,
            // leaving the CPU and bus budget for mass-storage transfers.
            if(!usb || !drawn_usb || ejected != drawn_ejected || last_activity != drawn_activity) {
                const auto model = display_snapshot();
                if(calculator_visible() && std::strcmp(previous_indicator, model.indicator) != 0) {
                    std::memcpy(previous_indicator, model.indicator, sizeof(previous_indicator));
                    std::printf("X=[%s]\n", model.indicator);
                }
                if(panel_ready && !remote_screen.holds_frame() && !picocalc::io_worker::frame_pending()) {
                    screen.render(model, keyboard.online(), &ui, &services,keyboard.battery());
                    panel.flush(screen);
                }
                if(!panel_ready || !picocalc::io_worker::frame_pending()) {
                    drawn_usb = usb; drawn_ejected = ejected; drawn_activity = last_activity;
                }
            }
            next_frame = time_us_64() + FRAME_INTERVAL_US;
        }
        // Running programs, held emulated keys and foreground services retain
        // their execution cadence. A settled calculator/menu can wait for the
        // nearest keyboard/UI deadline; USB remains serviced at least each ms.
        if(calculator.idle() && !core_61::is_RUN() &&
           !services.running() && !m61_text::active() && !picocalc::files::usb_active() && !remote_screen.attached()) {
            const u64 at=time_us_64();
            u64 deadline=at+(sleep_clocks.usb_available()?1000:16000);
            if(next_frame>at && next_frame<deadline) deadline=next_frame;
            if(keyboard.next_poll()>at && keyboard.next_poll()<deadline) deadline=keyboard.next_poll();
            picocalc::idle_until(deadline);
        } else tight_loop_contents();
    }
}
