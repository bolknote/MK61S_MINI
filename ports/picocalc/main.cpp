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
#include "usb_screen.hpp"
#include "terminal.hpp"
#include "terminal_command_ids.hpp"
#include "version.hpp"
#include "diagnostics.hpp"
#include "firmware.hpp"
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
bool serial_cr = false;
u32 physical_keys = 0;
u8 last_physical_key = 0;
bool settings_dirty = false;
const char* settings_status = "DEFAULT";
u64 save_at = 0, last_activity = 0;
u64 last_usb_service = 0;
u32 max_usb_gap = 0;
unsigned math_failures = 0;
constexpr u32 STACK_PATTERN = 0xD52AC37E;
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
    const auto model = calculator.snapshot();
    std::printf("MK61S PICOCALC PICO-H %s RP2040 %lu MHz\n",
                picocalc::VERSION,(unsigned long)(clock_get_hz(clk_sys) / 1000000));
    std::printf("TERMINAL=%s\n",terminal.raw()?"RAW":"COMMAND");
    std::printf("CORE=shared MATH=compact-binary64/GCC-IEEE-softfloat MATH_TEST=%s failures=%u\n",
                math_failures ? "FAIL" : "OK", math_failures);
    std::printf("KBD=%s errors=%lu dropped=%lu X=[%s] IP=%02u RUN=%u BUSY=%u\n",
                keyboard.online() ? "OK" : "WAIT", (unsigned long)keyboard.errors(),
                (unsigned long)model.dropped_keys, model.indicator, model.ip, model.running,
                !calculator.idle());
    char raw[INDICATOR_STRING_LENGTH];
    read_stack_register(X, raw, nullptr);
    std::printf("X_RAW=[%s] PANEL_INIT=%u PHYSICAL_KEYS=%lu LAST_PHYSICAL=0x%02X\n",
                raw, panel_ready, (unsigned long)physical_keys, last_physical_key);
    std::printf("LCD_BKL=%d KBD_BKL=%d\n", keyboard.lcd_backlight(), keyboard.key_backlight());
    std::printf("LCD=ST7365P RGB565 SPI_HZ=%lu FRAMES=%lu\n",
                (unsigned long)panel.spi_hz(), (unsigned long)panel.frames());
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
    std::printf("STACK_USED=%lu STACK_BYTES=%lu\n", (unsigned long)used_stack(), (unsigned long)((__StackTop - __StackBottom) * 4));
    const auto& usb = picocalc::usb::counters();
    std::printf("MSC_READ=%lu WRITE=%lu READ_ERROR=%lu WRITE_ERROR=%lu LBA=%lu SCSI=%02X\n", (unsigned long)usb.reads,
        (unsigned long)usb.writes, (unsigned long)usb.read_errors, (unsigned long)usb.write_errors,
        (unsigned long)usb.last_lba, usb.last_scsi);
    std::printf("USB_MAX_GAP_US=%lu\n",(unsigned long)max_usb_gap);
    std::printf("POWER_MODE=%s SYS_HZ=%lu PERI_HZ=%lu PLL_MASK=%u SLEEP_ENTRIES=%lu BATTERY_SLEEPS=%lu\n",
        sleep_clocks.active() ? sleep_clocks.usb_available() ? "SLEEP_USB" : "SLEEP_BATTERY" : "RUN",
        (unsigned long)clock_get_hz(clk_sys), (unsigned long)clock_get_hz(clk_peri), sleep_clocks.pll_mask(),
        (unsigned long)sleep_clocks.entries(), (unsigned long)sleep_clocks.battery_entries());
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
    if(now>=next_rtc) {
        picocalc::clock::service();next_rtc=now+100000;
        unsigned alarm;
        if(picocalc::clock::take_alarm(alarm)) { wake(now);tone(ui.settings().volume,1000);std::printf("RTC_ALARM=%c\n",'A'+alarm); }
    }
}
bool key_event(picocalc::KeyEvent& event) {
    if(keyboard.poll(event)) { physical_event=true;picocalc::controls::event(event);return true; }
    if(remote_screen.key(event)) { physical_event=false;picocalc::controls::event(event,picocalc::controls::Source::REMOTE);return true; }
    return false;
}
bool service_pump(void*, u8& key) {
    usb_service();
    picocalc::script::service_effects();
    const u64 now = time_us_64();
    static u64 next = 0;
    if(panel_ready && !remote_screen.holds_frame() && now >= next) {
        screen.render(calculator.snapshot(), keyboard.online(), &ui, &services); panel.flush(screen); next = time_us_64() + 80000;
    }
    picocalc::KeyEvent event{};
    if(key_event(event) && event.pressed()) {
        key = event.code;
        if(physical_event) { ++physical_keys;last_physical_key=key; } last_activity=now;power.activity(now);return true;
    }
    int c = getchar_timeout_us(0);
    if(c!=PICO_ERROR_TIMEOUT) c=remote_screen.receive((u8)c,(u32)(now/1000));
    if(c<0) return false;
    if(c == 5) { report(math_failures); return false; }
    c=terminal.receive((u8)c);
    if(c<0) return false;
    if(c != PICO_ERROR_TIMEOUT) {
        const bool skip = c == '\n' && serial_cr;
        serial_cr = c == '\r';
        if(!skip) {
            key=(u8)c;picocalc::controls::pulse(key,(u32)(now/1000));power.activity(now);
            return true;
        }
    }
    return false;
}
} // namespace

int main() {
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
        [](void*,u8* frame) { screen.render(calculator.snapshot(),keyboard.online(),&ui,&services);screen.logical_frame(ui,services,frame); },
        [](void*) {
            screen.render(calculator.snapshot(),keyboard.online(),&ui,&services);
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
    calculator.init();
    picocalc::Settings settings;
    if(picocalc::load_device_settings(settings)) settings_status = "LOADED";
    ui.init(settings);
    services.set_ui(ui);
    picocalc::clock::calibrate(settings.rtc_ppm);
    picocalc::clock::restore_alarms(settings.alarm_epoch,settings.alarm_flags);
    services.set_pump(service_pump, nullptr);
    terminal.init({nullptr,
        [](void*,const char* text,unsigned n) { std::printf("%.*s",(int)n,text); },
        [](void*) { usb_service();picocalc::script::service_effects();if(!m61_text::calculator_suspended()) calculator.tick(); },
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
                save_settings();stdio_flush();
                if(id==CMD_DFU) reset_usb_boot(0,0);else watchdog_reboot(0,0,10);
                for(;;) tight_loop_contents();
            }
            if(id==CMD_DISPLAY) {
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
        if(keyboard.online() && !panel_ready) {
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
            int c = sleep_clocks.usb_available() ? getchar_timeout_us(0) : PICO_ERROR_TIMEOUT;
            if(c == PICO_ERROR_TIMEOUT) break;
            c=remote_screen.receive((u8)c,millis());
            if(c<0) continue;
            if(c == 5 || (terminal.raw() && !services.active() && (c == '?' || c == 'm'))) {
                if(c == 'm') math_failures = picocalc::math_self_test();
                report(math_failures);
            } else if(c == '!' && terminal.raw() && !services.active()) {
                std::puts("Entering RP2040 USB BOOTSEL");
                stdio_flush();
                reset_usb_boot(0, 0);
            } else {
                const int key=terminal.receive((u8)c);
                if(key>=0 && (key!='\n' || !serial_cr)) { picocalc::controls::pulse((u8)key,millis());input((u8)key,false); }
                else if(c<0x1D || c>0x1F) { power.activity(time_us_64());if(power.asleep()) wake(time_us_64()); }
            }
            serial_cr = c == '\r';
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
        if(power.asleep()) { sleep_ms(sleep_clocks.usb_available() ? 4 : 16);continue; }
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
        if(picocalc::files::usb_active() || m61_text::calculator_suspended()) {
            // A single host READ can span thousands of sectors. Running one
            // whole MK61 microcode step between each 512-byte USB packet
            // exceeds the host's SCSI deadline on RP2040. USB owns this loop.
            next_classic_step = 0;
        } else if(current.classic_speed && core_61::is_RUN() && calculator.idle()) {
            if(!next_classic_step) next_classic_step = now + 1153846; // Shared CLASSIC cadence: 15/13 s.
            if(now >= next_classic_step) { calculator.tick(); next_classic_step = now + 1153846; }
        } else { next_classic_step = 0; calculator.tick(); }
        if(current.idle_signal && now - last_activity >= 300000000ULL) {
            tone(current.volume, 150);
            last_activity = now;
        }
        if(settings_dirty && now >= save_at && calculator.idle() && !core_61::is_RUN() && !picocalc::files::usb_active()) save_settings();
        services.tick();
        if(services.take_calculator_request()) ui.calculator_page();
        if(!picocalc::files::usb_active() && !services.active()) m61_text::service();
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
                const auto model = calculator.snapshot();
                if(std::strcmp(previous_indicator, model.indicator) != 0) {
                    std::memcpy(previous_indicator, model.indicator, sizeof(previous_indicator));
                    std::printf("X=[%s]\n", model.indicator);
                }
                if(panel_ready && !remote_screen.holds_frame()) {
                    screen.render(model, keyboard.online(), &ui, &services);
                    panel.flush(screen);
                }
                drawn_usb = usb; drawn_ejected = ejected; drawn_activity = last_activity;
            }
            next_frame = time_us_64() + 80000;
        }
        tight_loop_contents();
    }
}
