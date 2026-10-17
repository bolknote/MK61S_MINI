#include "storage.hpp"
#include "usb_diagnostics.hpp"
#include "tusb.h"
#include "pico/unique_id.h"
#include "pico/time.h"
#include <cstring>

namespace {
picocalc::usb::Counters counters{};
constexpr unsigned CONFIG_BYTES = TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN + TUD_MSC_DESC_LEN;
const tusb_desc_device_t device = {
    sizeof(tusb_desc_device_t), TUSB_DESC_DEVICE, 0x0200,
    TUSB_CLASS_MISC, MISC_SUBCLASS_COMMON, MISC_PROTOCOL_IAD,
    // TinyUSB's development VID/PID for the CDC+MSC combination. Reusing
    // the SDK CDC-only identity makes hosts cache the wrong interface set.
    CFG_TUD_ENDPOINT0_SIZE, 0xCAFE, 0x4003, 0x0300, 1, 2, 3, 1
};
const u8 configuration[] = {
    TUD_CONFIG_DESCRIPTOR(1, 3, 0, CONFIG_BYTES, 0, 250),
    TUD_CDC_DESCRIPTOR(0, 4, 0x81, 8, 0x02, 0x82, 64),
    TUD_MSC_DESCRIPTOR(2, 5, 0x03, 0x83, 64)
};
}
namespace picocalc { namespace usb { const Counters& counters() { return ::counters; } } }
extern "C" {
const uint8_t* tud_descriptor_device_cb() { return (const uint8_t*)&device; }
const uint8_t* tud_descriptor_configuration_cb(uint8_t) { return configuration; }
const uint16_t* tud_descriptor_string_cb(uint8_t index, uint16_t) {
    static uint16_t descriptor[64];
    static char serial[2 * PICO_UNIQUE_BOARD_ID_SIZE_BYTES + 1];
    if(index == 0) { descriptor[0] = (TUSB_DESC_STRING << 8) | 4; descriptor[1] = 0x0409; return descriptor; }
    pico_get_unique_board_id_string(serial, sizeof(serial));
    const char* strings[] = {"", "MK61S", "MK61S PicoCalc", serial, "MK61S terminal", "PicoCalc microSD"};
    if(index >= sizeof(strings) / sizeof(strings[0])) return nullptr;
    const unsigned n = std::strlen(strings[index]) < 63 ? std::strlen(strings[index]) : 63;
    for(unsigned i = 0; i < n; ++i) descriptor[i + 1] = (u8)strings[index][i];
    descriptor[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * n + 2));
    return descriptor;
}
void tud_msc_inquiry_cb(uint8_t, uint8_t vendor[8], uint8_t product[16], uint8_t revision[4]) {
    std::memcpy(vendor, "MK61S   ", 8); std::memcpy(product, "PicoCalc microSD ", 16); std::memcpy(revision, "0300", 4);
}
bool tud_msc_test_unit_ready_cb(uint8_t lun) {
    if(picocalc::files::usb_active() && !picocalc::files::usb_ejected() && picocalc::sd::ready()) return true;
    tud_msc_set_sense(lun, SCSI_SENSE_NOT_READY, 0x3A, 0);
    return false;
}
void tud_msc_capacity_cb(uint8_t, uint32_t* blocks, uint16_t* size) {
    *size = 512; *blocks = picocalc::sd::sectors();
}
bool tud_msc_is_writable_cb(uint8_t lun) { return tud_msc_test_unit_ready_cb(lun); }
bool tud_msc_start_stop_cb(uint8_t, uint8_t, bool start, bool load_eject) {
    if(load_eject && !start) picocalc::files::usb_eject();
    return true;
}
int32_t tud_msc_read10_cb(uint8_t lun, uint32_t lba, uint32_t offset, void* buffer, uint32_t count) {
    counters.reads += (offset + count + 511) / 512; counters.last_lba = lba;
    if(!tud_msc_test_unit_ready_cb(lun)) return -1;
    const u64 start = time_us_64();
    if(!counters.active_read_bytes) { counters.read_started_us = start; counters.active_read_lba = lba; }
    counters.active_read_bytes += count;
    const bool ok = picocalc::sd::read_bytes(lba, offset, (u8*)buffer, count);
    counters.sd_read_us += time_us_64() - start;
    if(!ok) { ++counters.read_errors; tud_msc_set_sense(lun, SCSI_SENSE_MEDIUM_ERROR, 0x11, 0); return -1; }
    return (int32_t)count;
}
void tud_msc_read10_complete_cb(uint8_t) {
    const u32 elapsed = (u32)(time_us_64() - counters.read_started_us);
    ++counters.read_commands;
    if(elapsed > counters.max_read_us) {
        counters.max_read_us = elapsed; counters.max_read_bytes = counters.active_read_bytes;
        counters.max_read_lba = counters.active_read_lba;
    }
    counters.active_read_bytes = 0;
}
int32_t tud_msc_write10_cb(uint8_t lun, uint32_t lba, uint32_t offset, uint8_t* buffer, uint32_t count) {
    counters.writes += (offset + count + 511) / 512; counters.last_lba = lba;
    if(!tud_msc_test_unit_ready_cb(lun)) return -1;
    if(!picocalc::sd::write_bytes(lba, offset, buffer, count)) { ++counters.write_errors; tud_msc_set_sense(lun, SCSI_SENSE_MEDIUM_ERROR, 0x0C, 0); return -1; }
    return (int32_t)count;
}
int32_t tud_msc_scsi_cb(uint8_t lun, const uint8_t command[16], void*, uint16_t) {
    counters.last_scsi = command[0];
    if(command[0] == SCSI_CMD_PREVENT_ALLOW_MEDIUM_REMOVAL) return 0;
    if(command[0] == 0x35) return picocalc::sd::sync() ? 0 : -1; // SYNCHRONIZE CACHE.
    tud_msc_set_sense(lun, SCSI_SENSE_ILLEGAL_REQUEST, 0x20, 0);
    return -1;
}
}
