#include "hardware.hpp"
#include "diagnostics.hpp"
#include "io_worker.hpp"
#include "crc32.hpp"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include <cstring>

namespace picocalc {
namespace {
constexpr unsigned DC = MK61_PICOCALC_LCD_DC_PIN;
constexpr unsigned RESET = MK61_PICOCALC_LCD_RESET_PIN;
constexpr unsigned CS = PICO_DEFAULT_SPI_CSN_PIN;

void command(u8 op, const u8* data = nullptr, unsigned size = 0) {
    gpio_put(DC, 0);
    gpio_put(CS, 0);
    busy_wait_us(1);
    spi_write_blocking(spi1, &op, 1);
    if(size) {
        busy_wait_us(1);
        gpio_put(DC, 1);
        busy_wait_us(1);
        spi_write_blocking(spi1, data, size);
    }
    busy_wait_us(1);
    gpio_put(CS, 1);
    busy_wait_us(1);
}

struct InitCommand { u8 op, count, data[1]; };
// ST7365P native setup. Leave power, VCOM, gamma and scan timing at the
// panel's reset/NVM values: ILI9488 parameters at the same addresses differ.
// RGB565/MADCTL/INVON/entry mode match the working PicOS PicoCalc driver.
constexpr InitCommand PANEL_INIT[] = {
    {0x3A, 1, {0x55}}, {0x36, 1, {0x48}}, {0x21, 0, {}},
    {0xB7, 1, {0xC6}}, {0x55, 1, {0x00}}, // Content-adaptive brightness off.
    {0x38, 0, {}}, {0x13, 0, {}} // Idle off, normal display mode.
};

int write_backlight(u8 reg, u8 value) {
    u8 message[] = {(u8)(reg | 0x80U), value};
    if(io_worker::blocking_i2c(false,message,2) != 2) return -1;
    sleep_ms(16);
    u8 response[2] = {};
    if(io_worker::blocking_i2c(true,response,2) != 2 ||
       response[0] != reg) return -1;
    return response[1];
}
} // namespace

void Keyboard::init() {
    i2c_init(i2c1, 10000);
    gpio_set_function(PICO_DEFAULT_I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(PICO_DEFAULT_I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(PICO_DEFAULT_I2C_SDA_PIN);
    gpio_pull_up(PICO_DEFAULT_I2C_SCL_PIN);
    online_ = pending_ = false;io_phase_=0;
    due_ = 0;
    io_worker::start();
}

bool Keyboard::poll(KeyEvent& event) {
    const u64 now = time_us_64();
    if(io_phase_) {
        int count;u8 response[2]{};
        if(!io_worker::take_i2c(count,response)) return false;
        const u8 phase=io_phase_;io_phase_=0;
        if(phase==1) {
            if(count==1) { pending_=true;due_=now+16000; }
            else { online_=false;++errors_;due_=now+100000; }
            return false;
        }
        pending_=false;online_=count==2;
        if(!online_) { ++errors_;due_=now+100000;return false; }
        event={response[0],response[1]};
        if(idle_ && !event.state) due_=now+64000;
        return event.state!=0;
    }
    if(now < due_) return false;
    diagnostics::Scope measure(diagnostics::Point::KEYBOARD);
    if(!pending_) {
        const u8 reg = 0x09;
        if(io_worker::request_i2c(false,&reg,1)) io_phase_=1;
        return false;
    }
    if(io_worker::request_i2c(true,nullptr,2)) io_phase_=2;
    return false;
}

void Keyboard::clock_changed() { io_worker::drain();i2c_set_baudrate(i2c1, 10000); }

void Keyboard::backlight(u8 lcd, u8 keys) {
    // Do not touch PMU shutdown, reset, SD or PSRAM registers.
    // The stock BIOS quantizes LCD PWM in steps of 16 and caps it at 240.
    lcd_backlight_ = write_backlight(0x05, lcd);
    key_backlight_ = write_backlight(0x0A, keys);
}

void Panel::init() {
    io_worker::drain();
    // ST7365P specifies >=66 ns per write clock (<=15.15 MHz). Request
    // 10 MHz, leaving margin for the board/ribbon; retain the actual divider.
    spi_hz_ = spi_init(spi1, 10000000);
    gpio_set_function(PICO_DEFAULT_SPI_SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_TX_PIN, GPIO_FUNC_SPI);
    gpio_set_function(PICO_DEFAULT_SPI_RX_PIN, GPIO_FUNC_SPI);
    const unsigned control_pins[] = {CS, DC, RESET};
    for(unsigned pin : control_pins) {
        gpio_init(pin);
        gpio_set_dir(pin, GPIO_OUT);
        gpio_put(pin, 1);
    }
    gpio_put(RESET, 0);
    sleep_ms(10);
    gpio_put(RESET, 1);
    sleep_ms(200);
    command(0x01);
    sleep_ms(150);
    for(const auto& c : PANEL_INIT) command(c.op, c.data, c.count);
    command(0x11);
    sleep_ms(120);
    command(0x29);
    sleep_ms(120);
    valid_ = false;
    frames_ = 0;
}

void Panel::sleep(bool enabled) {
    io_worker::drain();
    if(enabled) { command(0x28);command(0x10); }
    else { command(0x11);sleep_ms(120);command(0x29);valid_=false; }
}
void Panel::flush(const Screen& screen) {
    if(io_worker::frame_pending()) return;
    if(valid_ && std::memcmp(previous_, screen.data(), Screen::BYTES) == 0) return;
    diagnostics::Scope measure(diagnostics::Point::LCD);
    std::memcpy(previous_,screen.data(),Screen::BYTES);
    valid_=io_worker::submit_frame(this,[](void* context) { ((Panel*)context)->transfer(); });
}
void Panel::transfer() {
    const u8 columns[] = {0, 0, 1, 0x3F}; // Inclusive x=0..319.
    const u8 rows[] = {0, 0, 1, 0x3F};
    u8 scanline[Screen::WIDTH * 2];
    // A single RAM write also covers unchanged pixels. Partial row windows on
    // the first physical panel produced static bands of different luminance.
    // Keep the small monochrome buffer; convert only one scanline at a time.
    command(0x2A, columns, sizeof(columns));
    command(0x2B, rows, sizeof(rows));
    // Keep RAMWR and its pixel payload in one CS transaction.
    gpio_put(DC, 0);
    gpio_put(CS, 0);
    busy_wait_us(1);
    const u8 ram_write = 0x2C;
    spi_write_blocking(spi1, &ram_write, 1);
    busy_wait_us(1);
    gpio_put(DC, 1);
    busy_wait_us(1);
    for(unsigned y = 0; y < Screen::HEIGHT; ++y) {
        for(unsigned x = 0; x < Screen::WIDTH; ++x) {
            const bool lit = previous_[y*Screen::STRIDE+x/8]&(0x80U>>(x%8));
            // RGB565, big-endian: full white (FFFF) on black (0000).
            const u8 level = lit ? 0xFF : 0x00;
            scanline[x * 2] = level;
            scanline[x * 2 + 1] = level;
        }
        spi_write_blocking(spi1, scanline, sizeof(scanline));
        io_worker::service();
    }
    busy_wait_us(1);
    gpio_put(CS, 1);
    busy_wait_us(1);
    frame_crc_.store(mk61_crc32::calculate(previous_,sizeof(previous_)),std::memory_order_relaxed);
    frames_.fetch_add(1,std::memory_order_relaxed);
}

} // namespace picocalc
