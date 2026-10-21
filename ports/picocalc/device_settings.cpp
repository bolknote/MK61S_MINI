#include "settings.hpp"
#include "io_worker.hpp"
#include "hardware/flash.h"
#include "pico/flash.h"
#include "pico/stdlib.h"
#include <cstring>

namespace picocalc {
namespace {
constexpr u32 START = 2 * 1024 * 1024 - 2 * FLASH_SECTOR_SIZE;
constexpr unsigned PAGES = 2 * FLASH_SECTOR_SIZE / FLASH_PAGE_SIZE;
SettingsStorageStatistics statistics{};
static_assert(SETTINGS_PAGE_BYTES == FLASH_PAGE_SIZE, "settings record is one flash page");
const u8* page(unsigned index) { return (const u8*)(XIP_BASE + START + index * FLASH_PAGE_SIZE); }
bool erased(unsigned index) {
    for(unsigned i = 0; i < FLASH_PAGE_SIZE; ++i) if(page(index)[i] != 0xFF) return false;
    return true;
}
int latest(Settings& value, u32& sequence) {
    int result = -1;
    for(unsigned i = 0; i < PAGES; ++i) {
        Settings candidate;
        u32 serial;
        if(decode_settings(page(i), candidate, serial) &&
            (result < 0 || (i32)(serial - sequence) > 0)) {
            value = candidate; sequence = serial; result = (int)i;
        }
    }
    return result;
}
struct Write {
    unsigned index;
    bool erase;
    alignas(4) u8 data[FLASH_PAGE_SIZE];
};
void write(void* arg) {
    const auto& operation = *(const Write*)arg;
    const u32 offset = START + operation.index * FLASH_PAGE_SIZE;
    if(operation.erase) flash_range_erase(offset, FLASH_SECTOR_SIZE);
    flash_range_program(offset, operation.data, FLASH_PAGE_SIZE);
}
}
bool load_device_settings(Settings& value) {
    u32 sequence = 0;
    const bool valid=latest(value, sequence)>=0;
    statistics.sequence=sequence;return valid;
}
SettingsStorageStatistics settings_storage_statistics() { return statistics; }
bool save_device_settings(const Settings& value) {
    if(!valid_settings(value)) return false;
    Settings previous;
    u32 sequence = 0;
    const int current = latest(previous, sequence);
    Write operation{};
    // Append within the active sector. A rollover erases only the OTHER
    // sector, retaining the last valid record through power loss.
    const unsigned sector_pages = FLASH_SECTOR_SIZE / FLASH_PAGE_SIZE;
    operation.index = current < 0 ? 0 : (unsigned)current + 1;
    if(current >= 0 && operation.index % sector_pages == 0) {
        operation.index %= PAGES;
        operation.erase = true;
    } else if(!erased(operation.index)) {
        operation.index = current < 0 ? 0 : ((unsigned)current / sector_pages ^ 1U) * sector_pages;
        operation.erase = true;
    }
    encode_settings(value, sequence + 1, operation.data);
    // flash_safe_execute parks core 1. Never suspend its blocking I2C in
    // the middle of a transaction: a sector erase outlasts that timeout.
    // Core 0 is the sole producer of keyboard/LCD requests, so no new one
    // can be queued between this drain and the flash operation.
    io_worker::drain();
    if(flash_safe_execute(write, &operation, 1000) != PICO_OK) return false;
    if(std::memcmp(page(operation.index), operation.data, FLASH_PAGE_SIZE)) return false;
    ++statistics.writes;if(operation.erase) ++statistics.erases;
    statistics.sequence=sequence+1;return true;
}
} // namespace picocalc
