#include "calculator.hpp"
#include "math_probe.hpp"
#include "screen.hpp"
#include "ui.hpp"
#include "settings.hpp"
#include "menu_model.hpp"
#include "ui_font.hpp"
#include "mk8_codec.hpp"
#include "diagnostics.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
void require(bool value, const char* message) {
    if(!value) { std::fprintf(stderr, "PicoCalc: %s\n", message); std::exit(1); }
}
double x_value() {
    char value[15], number[32];
    read_stack_register(X, value, nullptr);
    char* out = number;
    if(value[0] == '-') *out++ = '-';
    for(unsigned i = 1; i <= 9; ++i) if(value[i] != ' ') *out++ = value[i];
    *out++ = 'e';
    *out++ = value[11] == '-' ? '-' : '+';
    *out++ = value[12]; *out++ = value[13]; *out = 0;
    return std::strtod(number, nullptr);
}
void feed(picocalc::Calculator& calc, const char* text, bool script_owns_display=false) {
    for(; *text; ++text) require(calc.input((u8)*text), "input rejected");
    for(unsigned i = 0; i < 4096; ++i) {
        calc.tick(script_owns_display);
        if(calc.idle() && !core_61::is_RUN()) return;
    }
    require(false, "calculator did not settle");
}
void equal_x(double value) {
    if(std::fabs(x_value() - value) > 1e-7) {
        std::fprintf(stderr, "X=%.12g expected %.12g\n", x_value(), value);
        require(false, "wrong calculation");
    }
}
void preview(const picocalc::Screen& screen, const char* path) {
    FILE* file = std::fopen(path, "wb");
    require(file != nullptr, "preview output");
    std::fprintf(file, "P4\n320 320\n");
    require(std::fwrite(screen.data(), 1, picocalc::Screen::BYTES, file) == picocalc::Screen::BYTES, "preview write");
    std::fclose(file);
}
void ui_test(picocalc::Calculator& calc, const char* preview_path) {
    using namespace picocalc;
    for(unsigned count = 1; count < 15; ++count) for(unsigned active = 0; active < count; ++active) {
        require(menu_model::step(active, count, 1) == (active + 1 < count ? active + 1 : active), "menu forward clamp");
        require(menu_model::step(active, count, -1) == (active ? active - 1 : 0), "menu backward clamp");
        for(unsigned rows = 1; rows < 12; ++rows) {
            const auto first = menu_model::firstVisible(active, count, rows);
            require(first <= active && active < first + rows, "active menu row is visible");
            require(first == 0 || first + rows <= count, "menu window bounds");
        }
    }
    Settings settings;
    u8 encoded[SETTINGS_PAGE_BYTES];
    encode_settings(settings, 0xFEDCBA98, encoded);
    Settings decoded;
    u32 sequence = 0;
    require(decode_settings(encoded, decoded, sequence) && sequence == 0xFEDCBA98, "settings roundtrip");
    require(std::memcmp(&settings, &decoded, sizeof(settings)) == 0, "settings payload");
    for(unsigned at = 0; at < 36; ++at) {
        encoded[at] ^= 1;
        require(!decode_settings(encoded, decoded, sequence), "torn or corrupt settings accepted");
        encoded[at] ^= 1;
    }
    settings.volume = 11;
    encode_settings(settings, 1, encoded);
    require(!decode_settings(encoded, decoded, sequence), "out-of-range settings accepted");

    Ui ui;
    ui.init();
    calc.init();
    feed(calc, "42");
    require(ui.input('\t', calc) && ui.page() == Page::MAIN, "Tab opens main menu");
    for(unsigned i = 0; i < 20; ++i) ui.input(0xB5, calc);
    require(ui.selected() == 0, "main up clamp");
    for(unsigned i = 0; i < 20; ++i) ui.input(0xB6, calc);
    require(ui.selected() == 5, "all six main menu items");
    ui.input(0xB1, calc);
    equal_x(42);
    require(ui.page() == Page::CALCULATOR && calc.idle(), "menu exit preserves X and input queue");
    ui.init();
    ui.input('\t', calc);
    char label[64];
    for(unsigned item = 0; item < menu_model::MAIN_COUNT; ++item) {
        ui.row(item, label);
        require(label[0] != 0, "empty shared main menu label");
        for(const char* p = label; *p; ++p) {
            require(ui_font::supports({ui_font::Family::PIXEL, ui_font::Size::PX14}, mk8::codepoint((u8)*p)), "missing menu glyph");
        }
    }
    if(preview_path) {
        Screen menu;
        menu.render(calc.snapshot(), true, &ui);
        char path[512]; std::snprintf(path, sizeof(path), "%s.menu.pbm", preview_path);
        preview(menu, path);
    }
    ui.input(0xB6, calc); ui.input(0xB6, calc); ui.input('\n', calc);
    require(ui.page() == Page::SETTINGS, "Settings action");
    ui.input(0xB7, calc);
    require(ui.settings().volume == 10, "right clamps maximum volume");
    ui.input('\n', calc);
    require(ui.settings().volume == 0, "Enter cycles volume");
    ui.input(0xB4, calc);
    require(ui.settings().volume == 0, "left clamps minimum volume");
    for(unsigned i = 0; i < 5; ++i) ui.input(0xB6, calc);
    ui.input(0xB7, calc);
    require(ui.settings().russian == 0, "language changed to English");
    ui.row(5, label);
    require(std::strcmp(label, "Language EN") == 0, "live English menu text");
    ui.input(0xB7, calc);
    ui.input(0xB5, calc); ui.input(0xB5, calc); // Memory.
    const u8 memory = ui.settings().memory;
    calc.input('1');
    ui.input(0xB7, calc);
    require(ui.page() == Page::NOTICE && ui.settings().memory == memory, "busy core memory change blocked");
    feed(calc, "");
    ui.input(0xB1, calc);
    ui.input(0xB7, calc); // AUTO -> 105.
    ui.input(0xB7, calc); // 105 -> 112.
    calc.set_memory_mode(ui.settings().memory);
    require(core_61::program_steps() == 112, "112-step setting applies to actual core");
    ui.input(0xB7, calc); // AUTO retains active memory layout.
    calc.set_memory_mode(ui.settings().memory);
    require(core_61::program_steps() == 112, "AUTO preserves memory layout");
    for(unsigned i = 0; i < 3; ++i) ui.input(0xB6, calc);
    ui.input('\n', calc);
    require(ui.page() == Page::FONTS, "font submenu");
    ui.input(0xB7, calc);
    ui.input(0xB6, calc); ui.input(0xB7, calc);
    require(ui.settings().calculator_font == 1 && ui.settings().ui_font_size == 16, "independent calculator and UI fonts");
    if(preview_path) {
        Screen menu;
        menu.render(calc.snapshot(), true, &ui);
        char path[512]; std::snprintf(path, sizeof(path), "%s.fonts.pbm", preview_path);
        preview(menu, path);
    }
    ui.input('\t', calc);
    require(ui.page() == Page::CALCULATOR, "Tab exits nested menu");
    ui.init(); ui.input('\t', calc); ui.input('\n', calc);
    require(ui.page() == Page::CONFIRM && ui.take_action() == Action::NONE, "bootloader requires confirmation");
    ui.input(0xB1, calc);
    require(ui.page() == Page::MAIN && ui.take_action() == Action::NONE, "bootloader cancel");
    ui.input(0xB6, calc); ui.input('\n', calc);
    require(ui.page() == Page::MAIN && ui.take_action() == Action::USB_DISK, "USB menu opens storage service");
    ui.input(0xB5, calc); ui.input('\n', calc); ui.input('\n', calc);
    require(ui.take_action() == Action::BOOTLOADER && ui.take_action() == Action::NONE, "confirmed action consumed once");
    calc.init();
}
} // namespace

void picocalc_services_test(const char* preview);
void picocalc_m61_test();
void picocalc_runtime_test();
void picocalc_parity_test();
void picocalc_software_test(const char* preview_path);
void picocalc_contract_test();
void picocalc_firmware_test();
int main(int argc, char** argv) {
    picocalc::Calculator calc;
    calc.init();
    picocalc::diagnostics::profile_reset();
    picocalc::diagnostics::profile_start();
    for(unsigned i=0;i<128;++i) calc.tick(true);
    require(picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls==0,
        "M61 foreground must not perform idle MK61 ROM scans");
    calc.tick();
    require(picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls==1,
        "calculator foreground must still scan the ROM");
    // A burst of FIFO key presses must neither repeat nor lose a digit.
    feed(calc, "12\n34+",true);
    equal_x(46);
    for(unsigned i=0;i<1024 && !calc.parked();++i) calc.tick(false,true);
    require(calc.parked(),"settled manual calculator can park its ROM scanner");
    const auto parked_calls=picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls;
    for(unsigned i=0;i<128;++i) calc.tick(false,true);
    require(picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls==parked_calls,
        "parked calculator does not burn cycles rescanning a stable ROM display");
    calc.wake_core();calc.tick(false,true);
    require(picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls==parked_calls+1,
        "direct terminal/VM mutation wakes the ROM scanner");
    require(picocalc::diagnostics::sample(picocalc::diagnostics::Point::CORE).calls>1,
        "M61 foreground must service queued keys and their release");
    picocalc::diagnostics::profile_stop();
    require(write_stack_register(X,'+',"12345000",4),"direct register update");
    calc.wake_core();
    for(unsigned i=0;i<1024 && !calc.parked();++i) calc.tick(false,true);
    require(calc.parked(),"direct update settles before parking");
    char parked_indicator[32];std::strcpy(parked_indicator,calc.snapshot().indicator);
    for(unsigned i=0;i<128;++i) calc.tick(false,false);
    require(!std::strcmp(parked_indicator,calc.snapshot().indicator),
        "parking preserves the same display latch as continued legacy scans after direct writes");
    feed(calc, "\x08" "9f-"); // F minus = the original MK-61 square root.
    equal_x(3);
    feed(calc, "\x08" "90f7"); // DEG sin(90).
    equal_x(1);
    feed(calc, "a");
    require(calc.snapshot().angle == RADIAN, "radian selector");
    feed(calc, "t");
    require(calc.snapshot().angle == GRADE, "grad selector");
    feed(calc, "d");
    feed(calc, "\x08" "42s0\x08" "l0");
    equal_x(42);

    calc.init();
    feed(calc, "fe");
    require(calc.snapshot().programming, "F EXP enters program mode");
    feed(calc, "1\n2+r");
    require(core_61::get_code(core_61::get_ring_address(0)) == 1, "program entry");
    feed(calc, "fng00r",true);
    require(!calc.snapshot().programming, "F +/- returns to AUTO");
    equal_x(3);

    // Function keys come from the STM32 BIOS, not ASCII escape sequences.
    require(picocalc::map_key(0x81).x == 11 && picocalc::map_key(0x81).y == 9, "F1 mapping");
    require(picocalc::map_key(0x90).x == 9, "BIOS F10 is 0x90, not 0x8A");
    require(picocalc::map_key(0xB1).x == 10, "BIOS Escape mapping");
    require(!picocalc::map_key(0xA2).valid(), "modifier must not become a calculator key");
    require((picocalc::KeyEvent{1, '5'}).pressed(), "initial press");
    require(!(picocalc::KeyEvent{2, '5'}).pressed(), "hold must not repeat digits");
    require(!(picocalc::KeyEvent{3, '5'}).pressed(), "release must not repeat digits");

    require(picocalc::math_self_test() == 0, "portable binary64 math smoke test");
    const auto before = calc.snapshot();
    picocalc::Screen screen;
    screen.render(before, true);
    require(std::strcmp(before.indicator, calc.snapshot().indicator) == 0, "render changed calculator");
    require(!screen.pixel(320, 320), "pixel bounds");
    unsigned lit = 0;
    for(unsigned y = 0; y < 320; ++y) for(unsigned x = 0; x < 320; ++x) lit += screen.pixel(x, y);
    require(lit > 3000 && lit < 320 * 320 / 2, "screen is empty or overfilled");
    if(argc == 2) {
        preview(screen, argv[1]);
    }

    ui_test(calc, argc == 2 ? argv[1] : nullptr);
    picocalc_services_test(argc == 2 ? argv[1] : nullptr);
    picocalc_m61_test();
    extern void picocalc_language_cache_test();
    picocalc_language_cache_test();
    picocalc_runtime_test();
    picocalc_parity_test();
    picocalc_software_test(argc == 2 ? argv[1] : nullptr);
    picocalc_contract_test();
    picocalc_firmware_test();
    extern void picocalc_io_test();
    picocalc_io_test();

    calc.init();
    for(unsigned i = 0; i < 32; ++i) require(calc.input('1'), "queue capacity");
    require(!calc.input('2') && calc.snapshot().dropped_keys == 1, "queue overflow diagnostics");
    std::puts("PicoCalc core/key/program/math/screen tests passed");
}
