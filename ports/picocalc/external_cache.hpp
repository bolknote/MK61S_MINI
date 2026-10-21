#ifndef MK61_PICOCALC_EXTERNAL_CACHE_HPP
#define MK61_PICOCALC_EXTERNAL_CACHE_HPP
#include "rust_types.h"
namespace picocalc::external_cache {
// Two disjoint 4 MiB partitions. Metadata lives in PSRAM as well: no hidden
// SRAM allocation competes with the source editor or a loaded native APP.
constexpr unsigned MODULE_SLOTS=256,SECTOR_SLOTS=4096;
struct Statistics { bool ready;u32 module_hits,module_misses,sector_hits,sector_misses,rejected,stores; };
bool init();
void suspend();
void invalidate_modules();
void invalidate_sectors();
bool module(u64 key,void* bytes,unsigned capacity,unsigned& count,const char* owner=nullptr);
void store_module(u64 key,const void* bytes,unsigned count,const char* owner=nullptr);
bool sector(u32 lba,u8 bytes[512]);
void store_sector(u32 lba,const u8 bytes[512]);
void invalidate_sector(u32 lba);
Statistics statistics();
}
#endif
