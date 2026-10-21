#include "storage.hpp"
#include <cstring>
namespace picocalc { namespace sd {
namespace {
bool valid(u32 lba, u32 offset, u32 count) {
    return ready() && offset < 512 && lba < sectors() && (u64)count <= ((u64)sectors() - lba) * 512 - offset;
}
}
bool read_bytes(u32 lba, u32 offset, u8* out, u32 count) {
    if(!valid(lba, offset, count)) return false;
    while(count) {
        if(offset == 0 && count >= 512) {
            const u32 sectors = count / 512;
            if(!read_sectors(lba, out, sectors)) return false;
            out += sectors * 512; count -= sectors * 512; lba += sectors;
            continue;
        }
        const unsigned n = count < 512 - offset ? count : 512 - offset;
        u8 sector[512]; if(!read(lba, sector)) return false; std::memcpy(out, sector + offset, n);
        out += n; count -= n; ++lba; offset = 0;
    }
    return true;
}
bool write_bytes(u32 lba, u32 offset, const u8* data, u32 count) {
    if(!valid(lba, offset, count)) return false;
    while(count) {
        if(offset==0 && count>=512) {
            const u32 blocks=count/512;
            if(!write_sectors(lba,data,blocks)) return false;
            data+=blocks*512;count-=blocks*512;lba+=blocks;continue;
        }
        const unsigned n = count < 512 - offset ? count : 512 - offset;
        if(offset == 0 && n == 512) { if(!write(lba, data)) return false; }
        else {
            u8 sector[512]; if(!read(lba, sector)) return false;
            std::memcpy(sector + offset, data, n); if(!write(lba, sector)) return false;
        }
        data += n; count -= n; ++lba; offset = 0;
    }
    return true;
}
} }
