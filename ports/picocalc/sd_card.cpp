#include "storage.hpp"
#include "storage_journal.hpp"
#include "sd_crc.hpp"
#include "diagnostics.hpp"
#include "dma_support.hpp"
#include "external_cache.hpp"
#include "hardware/dma.h"
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
int dma_tx=-1,dma_rx=-1;
Statistics counters{};
bool data_transfer(const u8* source,u8* target,unsigned count,u16& crc) {
    const bool reading=target!=nullptr;
    if(dma_tx<0 || dma_rx<0) {
        if(reading) spi_read_blocking(spi0,0xFF,target,count);
        else spi_write_blocking(spi0,source,count);
        crc=crc16(reading?target:source,count);return true;
    }
    u8 filler=0xFF,discard=0;
    auto tx=dma_channel_get_default_config((unsigned)dma_tx);
    channel_config_set_transfer_data_size(&tx,DMA_SIZE_8);
    channel_config_set_dreq(&tx,spi_get_dreq(spi0,true));
    channel_config_set_read_increment(&tx,source!=nullptr);
    channel_config_set_write_increment(&tx,false);
    auto rx=dma_channel_get_default_config((unsigned)dma_rx);
    channel_config_set_transfer_data_size(&rx,DMA_SIZE_8);
    channel_config_set_dreq(&rx,spi_get_dreq(spi0,false));
    channel_config_set_read_increment(&rx,false);
    channel_config_set_write_increment(&rx,target!=nullptr);
    const bool sniff=dma_support::begin_crc((unsigned)(reading?dma_rx:dma_tx),false);
    channel_config_set_sniff_enable(reading?&rx:&tx,sniff);
    dma_channel_configure((unsigned)dma_rx,&rx,target?target:&discard,&spi_get_hw(spi0)->dr,count,false);
    dma_channel_configure((unsigned)dma_tx,&tx,&spi_get_hw(spi0)->dr,source?source:&filler,count,false);
    dma_start_channel_mask((1U<<dma_tx)|(1U<<dma_rx));
    const bool ok=dma_support::wait((unsigned)dma_tx,dma_rx);
    if(sniff) { crc=(u16)dma_support::end_crc();++counters.hardware_crc; }
    else crc=crc16(reading?target:source,count);
    ++counters.dma_transfers;
    while(spi_is_busy(spi0)) tight_loop_contents();
    return ok;
}
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
    u16 actual=0;
    if(!data_transfer(nullptr,data,size,actual)) return false;
    const u8 high = transfer(), low = transfer();
    const u16 expected = (u16)high << 8 | low;
    if(actual!=expected) { ++counters.crc_errors;return false; }
    return true;
}
}
bool init() {
    initialized = false; sector_count = 0;
    external_cache::invalidate_sectors();
    if(dma_tx<0) {
        dma_tx=dma_claim_unused_channel(false);dma_rx=dma_claim_unused_channel(false);
        if(dma_tx<0 || dma_rx<0) {
            if(dma_tx>=0) dma_channel_unclaim((unsigned)dma_tx);
            if(dma_rx>=0) dma_channel_unclaim((unsigned)dma_rx);
            dma_tx=dma_rx=-1;
        } else {
            dma_support::enable_irq((unsigned)dma_tx);dma_support::enable_irq((unsigned)dma_rx);
        }
    }
    counters.dma=dma_tx>=0 && dma_rx>=0;
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
    // The USB host already caches its filesystem. Do not copy a bulk MSC
    // scan through narrow SPI PSRAM as well; reserve that cache for local
    // repeated file/VM reads. All writes still invalidate cached sectors.
    const bool cached=!files::usb_active();
    if(cached && external_cache::sector(sector,out)) return true;
    ++counters.reads;
    const bool ok = command(17, block_address ? sector : sector * 512) == 0 && receive(out, 512);
    deselect();if(ok && cached) external_cache::store_sector(sector,out);return ok;
}
bool read_sectors(u32 sector, u8* out, u32 count) {
    if(!initialized || !count || sector >= sector_count || count > sector_count - sector) return false;
    if(count == 1) return read(sector, out);
    // Consume a cached prefix, then retain the existing CMD18 stream for the
    // remaining physical reads. A warm contiguous request needs no SD command.
    const bool cached=!files::usb_active();
    while(cached && count && external_cache::sector(sector,out)) { ++sector;out+=512;--count; }
    if(!count) return true;
    if(count==1) return read(sector,out);
    if(command(18, block_address ? sector : sector * 512) != 0) { deselect(); return false; }
    bool ok = true;
    for(u32 i = 0; i < count; ++i) {
        picocalc::diagnostics::feed_watchdog();
        if(!receive(out + i * 512, 512)) { ok = false; break; }
        ++counters.reads;if(cached) external_cache::store_sector(sector+i,out+i*512);
    }
    // Stop even after CRC/token failure, so the next request starts cleanly.
    const bool stopped = command(12, 0) == 0 && wait_ready();
    deselect(); return ok && stopped;
}
bool write(u32 sector, const u8 data[512]) {
    if(!initialized || sector >= sector_count) return false;
    // Invalidate before issuing the command, including rejected/partially
    // completed writes. Journal replay and raw MSC writes use this same path.
    external_cache::invalidate_sector(sector);
    ++counters.writes;
    bool ok = command(24, block_address ? sector : sector * 512) == 0;
    if(ok) {
        transfer(); transfer(0xFE);
        u16 crc=0;
        if(!data_transfer(data,nullptr,512,crc)) { deselect();return false; }
        transfer((u8)(crc >> 8)); transfer((u8)crc);
        ok = (transfer() & 0x1F) == 5 && wait_ready(1000);
    }
    deselect(); return ok;
}
bool sync() { if(!initialized || !select()) return false; const bool ok = wait_ready(1000); deselect(); return ok; }
Statistics statistics() { return counters; }
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
    for(UINT i = 0; i < count; ++i) { picocalc::diagnostics::feed_watchdog(); if(!picocalc::storage_journal::write((u32)sector + i, in + i * 512)) return RES_ERROR; }
    return RES_OK;
}
DRESULT disk_ioctl(BYTE drive, BYTE op, void* out) {
    if(drive || !picocalc::sd::ready()) return RES_NOTRDY;
    switch(op) {
        case CTRL_SYNC: return picocalc::storage_journal::sync() ? RES_OK : RES_ERROR;
        case GET_SECTOR_COUNT: *(LBA_t*)out = picocalc::sd::sectors(); return RES_OK;
        case GET_SECTOR_SIZE: *(WORD*)out = 512; return RES_OK;
        case GET_BLOCK_SIZE: *(DWORD*)out = 1; return RES_OK;
        default: return RES_PARERR;
    }
}
}
