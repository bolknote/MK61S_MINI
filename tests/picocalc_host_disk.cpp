// RAM-backed SD for the *real* FatFs adapter. Never opens a host disk/device.
#include "storage.hpp"
#include "storage_journal.hpp"
#include <vector>
#include <cstring>
extern "C" {
#include "ff.h"
#include "diskio.h"
}
// The weak embedded USB transport hook has no host implementation.
void storage_io_process() {}
namespace {
std::vector<u8> disk(16 * 1024 * 1024);
bool initialized = false;
int fail_after = -1;
}
namespace picocalc { namespace sd {
bool init() { initialized = true; return true; }
bool ready() { return initialized; }
u32 sectors() { return (u32)disk.size() / 512; }
bool read(u32 sector, u8 out[512]) {
    if(!initialized || sector >= sectors()) return false;
    std::memcpy(out, disk.data() + sector * 512, 512); return true;
}
bool read_sectors(u32 sector, u8* out, u32 count) {
    if(!initialized || !count || sector >= sectors() || count > sectors() - sector) return false;
    std::memcpy(out, disk.data() + sector * 512, count * 512); return true;
}
bool write(u32 sector, const u8 data[512]) {
    if(!initialized || sector >= sectors()) return false;
    if(fail_after == 0) { fail_after = -1; return false; }
    if(fail_after > 0) --fail_after;
    std::memcpy(disk.data() + sector * 512, data, 512); return true;
}
bool sync() { return initialized; }
bool write_sectors(u32 sector,const u8* data,u32 count) {
    if(!data || !count || sector>=sectors() || count>sectors()-sector) return false;
    for(u32 i=0;i<count;++i) if(!write(sector+i,data+i*512)) return false;
    return true;
}
} }
void picocalc_host_fail_write(int after) { fail_after = after; }
bool picocalc_host_make_exfat() {
    f_mount(nullptr, "", 0);
    MKFS_PARM options{}; options.fmt = FM_EXFAT;
    u8 work[4096];
    return f_mkfs("", &options, work, sizeof(work)) == FR_OK;
}
extern "C" {
DSTATUS disk_initialize(BYTE drive) { return drive || !picocalc::sd::init() ? STA_NOINIT : 0; }
DSTATUS disk_status(BYTE drive) { return drive || !picocalc::sd::ready() ? STA_NOINIT : 0; }
DRESULT disk_read(BYTE drive, BYTE* out, LBA_t sector, UINT count) {
    if(drive || !count || sector + count > picocalc::sd::sectors()) return RES_PARERR;
    for(UINT i = 0; i < count; ++i) if(!picocalc::sd::read((u32)sector + i, out + i * 512)) return RES_ERROR;
    return RES_OK;
}
DRESULT disk_write(BYTE drive, const BYTE* data, LBA_t sector, UINT count) {
    if(drive || !count || sector + count > picocalc::sd::sectors()) return RES_PARERR;
    return picocalc::storage_journal::write_sectors((u32)sector,data,count)?RES_OK:RES_ERROR;
}
DRESULT disk_ioctl(BYTE drive, BYTE op, void* out) {
    if(drive || !picocalc::sd::ready()) return RES_NOTRDY;
    if(op == CTRL_SYNC) return picocalc::storage_journal::sync() ? RES_OK : RES_ERROR;
    if(op == GET_SECTOR_COUNT) *(LBA_t*)out = picocalc::sd::sectors();
    else if(op == GET_SECTOR_SIZE) *(WORD*)out = 512;
    else if(op == GET_BLOCK_SIZE) *(DWORD*)out = 1;
    else return RES_PARERR;
    return RES_OK;
}
}
