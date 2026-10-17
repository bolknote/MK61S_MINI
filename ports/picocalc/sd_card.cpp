#include "storage.hpp"
#include "sd_crc.hpp"
#include "hardware/spi.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
extern "C" {
#include "ff.h"
#include "diskio.h"
}

namespace picocalc { namespace sd {
namespace {
constexpr unsigned CS = 17;
bool initialized = false, block_address = false;
u32 sector_count = 0;
u8 transfer(u8 byte = 0xFF) { u8 in; spi_write_read_blocking(spi0, &byte, &in, 1); return in; }
void deselect() { gpio_put(CS, 1); transfer(); }
bool wait_ready(u32 ms = 500) {
    const u64 end = time_us_64() + ms * 1000ULL;
    do { if(transfer() == 0xFF) return true; } while(time_us_64() < end);
    return false;
}
bool select() { gpio_put(CS, 0); transfer(); if(wait_ready()) return true; deselect(); return false; }
u8 command(u8 op, u32 argument) {
    // CMD12 terminates an active CMD18 stream, with CS still asserted.
    // Its response has one stuff byte before R1b (SD SPI protocol).
    if(op != 12) { deselect(); if(!select()) return 0xFF; }
    u8 packet[] = {(u8)(0x40 | op), (u8)(argument >> 24), (u8)(argument >> 16),
        (u8)(argument >> 8), (u8)argument, (u8)(op == 0 ? 0x95 : op == 8 ? 0x87 : 0x01)};
    spi_write_blocking(spi0, packet, sizeof(packet));
    if(op == 12) transfer();
    for(unsigned i = 0; i < 10; ++i) { const u8 response = transfer(); if(!(response & 0x80)) return response; }
    return 0xFF;
}
bool receive(u8* data, unsigned size) {
    const u64 end = time_us_64() + 500000;
    u8 token;
    do { token = transfer(); } while(token == 0xFF && time_us_64() < end);
    if(token != 0xFE) return false;
    spi_read_blocking(spi0, 0xFF, data, size);
    const u8 high = transfer(), low = transfer();
    const u16 expected = (u16)high << 8 | low;
    return crc16(data, size) == expected;
}
}
bool init() {
    initialized = false; sector_count = 0;
    spi_init(spi0, 400000);
    gpio_set_function(18, GPIO_FUNC_SPI);
    gpio_set_function(19, GPIO_FUNC_SPI);
    gpio_set_function(16, GPIO_FUNC_SPI);
    gpio_pull_up(16);
    gpio_init(CS); gpio_set_dir(CS, GPIO_OUT); gpio_put(CS, 1);
    sleep_ms(10);
    for(unsigned i = 0; i < 10; ++i) transfer();
    const u64 reset_deadline = time_us_64() + 500000;
    while(command(0, 0) != 1) { if(time_us_64() >= reset_deadline) { deselect(); return false; } }
    const u8 response = command(8, 0x1AA);
    bool version2 = response == 1;
    if(version2) {
        u8 voltage[4]; for(u8& byte : voltage) byte = transfer();
        if(voltage[2] != 1 || voltage[3] != 0xAA) { deselect(); return false; }
    } else if(response != 5) { deselect(); return false; }
    const u64 ready_deadline = time_us_64() + 2000000;
    do {
        if(command(55, 0) <= 1 && command(41, version2 ? 0x40000000 : 0) == 0) break;
        sleep_ms(5);
    } while(time_us_64() < ready_deadline);
    if(time_us_64() >= ready_deadline || command(58, 0) != 0) { deselect(); return false; }
    u8 ocr[4]; for(u8& byte : ocr) byte = transfer();
    block_address = version2 && (ocr[0] & 0x40);
    if(!block_address && command(16, 512) != 0) { deselect(); return false; }
    u8 csd[16];
    if(command(9, 0) != 0 || !receive(csd, sizeof(csd))) { deselect(); return false; }
    if((csd[0] >> 6) == 1) {
        const u32 c_size = (u32)(csd[7] & 63) << 16 | (u32)csd[8] << 8 | csd[9];
        const u64 sectors64 = ((u64)c_size + 1) * 1024;
        if(sectors64 > UINT32_MAX) { deselect(); return false; }
        sector_count = (u32)sectors64;
    } else if((csd[0] >> 6) == 0) {
        const u32 c_size = (u32)(csd[6] & 3) << 10 | (u32)csd[7] << 2 | csd[8] >> 6;
        const unsigned shift = ((csd[9] & 3) << 1 | csd[10] >> 7) + 2 + (csd[5] & 15);
        sector_count = (u32)(((u64)c_size + 1) << shift >> 9);
    }
    deselect();
    spi_set_baudrate(spi0, 12500000);
    initialized = sector_count != 0;
    return initialized;
}
bool ready() { return initialized; }
u32 sectors() { return sector_count; }
bool read(u32 sector, u8 out[512]) {
    if(!initialized || sector >= sector_count) return false;
    const bool ok = command(17, block_address ? sector : sector * 512) == 0 && receive(out, 512);
    deselect(); return ok;
}
bool read_sectors(u32 sector, u8* out, u32 count) {
    if(!initialized || !count || sector >= sector_count || count > sector_count - sector) return false;
    if(count == 1) return read(sector, out);
    if(command(18, block_address ? sector : sector * 512) != 0) { deselect(); return false; }
    bool ok = true;
    for(u32 i = 0; i < count; ++i) {
        watchdog_update();
        if(!receive(out + i * 512, 512)) { ok = false; break; }
    }
    // Stop even after CRC/token failure, so the next request starts cleanly.
    const bool stopped = command(12, 0) == 0 && wait_ready();
    deselect(); return ok && stopped;
}
bool write(u32 sector, const u8 data[512]) {
    if(!initialized || sector >= sector_count) return false;
    bool ok = command(24, block_address ? sector : sector * 512) == 0;
    if(ok) {
        transfer(); transfer(0xFE);
        spi_write_blocking(spi0, data, 512);
        const u16 crc = crc16(data, 512);
        transfer((u8)(crc >> 8)); transfer((u8)crc);
        ok = (transfer() & 0x1F) == 5 && wait_ready(1000);
    }
    deselect(); return ok;
}
bool sync() { if(!initialized || !select()) return false; const bool ok = wait_ready(1000); deselect(); return ok; }
} } // namespace picocalc::sd

extern "C" {
DSTATUS disk_initialize(BYTE drive) { return drive == 0 && picocalc::sd::init() ? 0 : STA_NOINIT; }
DSTATUS disk_status(BYTE drive) { return drive == 0 && picocalc::sd::ready() ? 0 : STA_NOINIT; }
DRESULT disk_read(BYTE drive, BYTE* out, LBA_t sector, UINT count) {
    if(drive || !count || sector > UINT32_MAX || sector + count > picocalc::sd::sectors()) return RES_PARERR;
    return picocalc::sd::read_sectors((u32)sector, out, count) ? RES_OK : RES_ERROR;
}
DRESULT disk_write(BYTE drive, const BYTE* in, LBA_t sector, UINT count) {
    if(drive || !count || sector > UINT32_MAX || sector + count > picocalc::sd::sectors()) return RES_PARERR;
    for(UINT i = 0; i < count; ++i) { watchdog_update(); if(!picocalc::sd::write((u32)sector + i, in + i * 512)) return RES_ERROR; }
    return RES_OK;
}
DRESULT disk_ioctl(BYTE drive, BYTE op, void* out) {
    if(drive || !picocalc::sd::ready()) return RES_NOTRDY;
    switch(op) {
        case CTRL_SYNC: return picocalc::sd::sync() ? RES_OK : RES_ERROR;
        case GET_SECTOR_COUNT: *(LBA_t*)out = picocalc::sd::sectors(); return RES_OK;
        case GET_SECTOR_SIZE: *(WORD*)out = 512; return RES_OK;
        case GET_BLOCK_SIZE: *(DWORD*)out = 1; return RES_OK;
        default: return RES_PARERR;
    }
}
}
