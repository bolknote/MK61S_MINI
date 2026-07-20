#ifndef MK61_VIRTUAL_FAT_HPP
#define MK61_VIRTUAL_FAT_HPP

#include "rust_types.h"

namespace virtual_fat {

static constexpr u16 SECTOR_SIZE = 512;

u32 sector_count(void);
bool read_sector(u32 lba, u8* out);
bool read_sectors(u32 lba, u8* out, u16 count);
// Подключает необязательное ОЗУ только на время сеанса перед reset_session().
// Основной кэш всегда размещён в language_workspace; сборки UC1609 одалживают
// сюда неиспользуемый буфер шрифта, пока устройством владеет USB-накопитель.
bool set_external_cache(u8* data, usize size);
u8 write_cache_capacity(void);
u8 dirty_cache_sectors(void);
// Атомарно принимает весь пакет USB в уже занятую ОЗУ без операций ввода-вывода
// SPI. Если чистых или свободных слотов недостаточно, возвращает false без
// изменения кэша, позволяя вызывающему коду отложить пакет до основного цикла.
bool try_write_cached_sectors(u32 lba, const u8* data, u16 count);
bool write_cached_sectors(u32 lba, const u8* data, u16 count);
bool flush_write_cache(void);
bool write_sector(u32 lba, const u8* data);
bool write_sectors(u32 lba, const u8* data, u16 count);
bool flush_pending(void);
bool reset_session(void);
void end_session(void);

// Доступ к диагностической трассировке (строки не равны NULL только в сборках
// с MK61_VFAT_TRACE).
const char* trace_line_at(u16 index);

} // пространство имён virtual_fat

extern "C" u8 MK61_VirtualFatSync(void);

#endif
