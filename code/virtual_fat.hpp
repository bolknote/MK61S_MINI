#ifndef MK61_VIRTUAL_FAT_HPP
#define MK61_VIRTUAL_FAT_HPP

#include "rust_types.h"

namespace virtual_fat {

static constexpr u16 SECTOR_SIZE = 512;

u32 sector_count(void);
bool read_sector(u32 lba, u8* out);
bool read_sectors(u32 lba, u8* out, u16 count);
// Подключает дополнительную ОЗУ только на время сеанса до reset_session().
// Базовый кеш всегда размещён в language_workspace; сборки UC1609 одалживают
// сюда свободный буфер шрифта, пока устройство принадлежит USB-накопителю.
bool set_external_cache(u8* data, usize size);
u8 write_cache_capacity(void);
u8 dirty_cache_sectors(void);
// Атомарно принимает целый USB-пакет в уже занятую ОЗУ без обмена по SPI.
// Если чистых или свободных слотов не хватает, возвращает false без изменения
// кеша, позволяя вызывающему коду отложить пакет до основного цикла.
bool try_write_cached_sectors(u32 lba, const u8* data, u16 count);
bool write_cached_sectors(u32 lba, const u8* data, u16 count);
bool flush_write_cache(void);
bool write_sector(u32 lba, const u8* data);
bool write_sectors(u32 lba, const u8* data, u16 count);
bool flush_pending(void);
bool reset_session(void);
void end_session(void);

// Доступ к диагностической трассировке (строки не NULL только в сборках MK61_VFAT_TRACE).
const char* trace_line_at(u16 index);

} // пространство имён virtual_fat

extern "C" u8 MK61_VirtualFatSync(void);

#endif
