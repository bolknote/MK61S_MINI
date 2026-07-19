#ifndef MK61_VIRTUAL_FAT_HPP
#define MK61_VIRTUAL_FAT_HPP

#include "rust_types.h"

namespace virtual_fat {

static constexpr u16 SECTOR_SIZE = 512;

u32 sector_count(void);
bool read_sector(u32 lba, u8* out);
bool read_sectors(u32 lba, u8* out, u16 count);
// Attach optional session-only RAM before reset_session(). The base cache is
// always backed by language_workspace; UC1609 builds lend their idle font
// buffer here while USB mass-storage owns the device.
bool set_external_cache(u8* data, usize size);
u8 write_cache_capacity(void);
u8 dirty_cache_sectors(void);
// Atomically accept a whole USB packet into already-owned RAM without SPI I/O.
// Returns false without modifying the cache when clean/free slots are
// insufficient, allowing the caller to defer the packet to the main loop.
bool try_write_cached_sectors(u32 lba, const u8* data, u16 count);
bool write_cached_sectors(u32 lba, const u8* data, u16 count);
bool flush_write_cache(void);
bool write_sector(u32 lba, const u8* data);
bool write_sectors(u32 lba, const u8* data, u16 count);
bool flush_pending(void);
bool reset_session(void);
void end_session(void);

// Diagnostic trace access (non-NULL lines only with MK61_VFAT_TRACE builds).
const char* trace_line_at(u16 index);

} // namespace virtual_fat

extern "C" u8 MK61_VirtualFatSync(void);

#endif
