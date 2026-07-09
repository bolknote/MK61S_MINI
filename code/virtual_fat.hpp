#ifndef MK61_VIRTUAL_FAT_HPP
#define MK61_VIRTUAL_FAT_HPP

#include "rust_types.h"

namespace virtual_fat {

static constexpr u16 SECTOR_SIZE = 512;

u32 sector_count(void);
bool read_sector(u32 lba, u8* out);
bool read_sectors(u32 lba, u8* out, u16 count);
bool write_sector(u32 lba, const u8* data);
bool write_sectors(u32 lba, const u8* data, u16 count);
bool flush_pending(void);
void reset_session(void);

// Diagnostic trace access (non-NULL lines only with MK61_VFAT_TRACE builds).
const char* trace_line_at(u16 index);

} // namespace virtual_fat

extern "C" u8 MK61_VirtualFatSync(void);

#endif
