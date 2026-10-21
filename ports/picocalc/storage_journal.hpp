#ifndef MK61_PICOCALC_STORAGE_JOURNAL_HPP
#define MK61_PICOCALC_STORAGE_JOURNAL_HPP
#include "rust_types.h"
namespace picocalc { namespace storage_journal {
// Only FatFs disk_write goes through this adapter; USB MSC owns the card
// exclusively and uses the raw SD driver instead.
bool write(u32 sector,const u8 data[512]);
bool write_sectors(u32 sector,const u8* data,u32 count);
bool sync();
bool recover();
bool begin();
bool commit();
bool rollback();
void reset();
bool active();
bool reserved(const char* path);
const char* error();
constexpr const char* FILE_NAME="/MK61JRN.SYS";
constexpr unsigned CAPACITY=512;
constexpr unsigned FILE_SECTORS=2+2*CAPACITY;
constexpr unsigned FILE_BYTES=FILE_SECTORS*512;
} }
#endif
