#ifndef STORAGE_GEOMETRY_HPP
#define STORAGE_GEOMETRY_HPP

#include "rust_types.h"

namespace storage_geometry {

// Физическая геометрия SPI NOR, используемая C5. Виртуальный сектор FAT
// остаётся 512-байтовым; физические секторы стирания никогда не показываются
// хосту USB.
static constexpr u32 PHYSICAL_SECTOR_SIZE = 4096;
static constexpr u16 LOGICAL_SECTOR_SIZE = 512;
static constexpr u16 FAT12_MAX_DATA_CLUSTERS = 4084;
static constexpr u8 MIN_SECTORS_PER_CLUSTER = 4;   // 2 КиБ, один файл размером 1536 байт
static constexpr u8 MAX_SECTORS_PER_CLUSTER = 64;  // 32 КиБ, широкая совместимость

static constexpr u8 LOCATOR_SECTORS = 2;
static constexpr u8 SETTINGS_SECTORS = 1;
static constexpr u8 CATALOG_HEADER_SECTORS = 1;
static constexpr u8 CATALOG_WAL_SECTORS = 2;
static constexpr u8 CATALOG_BANKS = 2;
// Шестьдесят четыре обычных сегмента журнала содержат 448 физических записей
// не более чем для 384 актуальных изменённых блоков. Последний сегмент служит
// резервом атомарного уплотнения. Дополнительные 192 КиБ несущественны на
// распространённой микросхеме 16 МиБ и не позволяют современным настольным
// файловым системам исчерпать промежуточное хранилище до синхронизации кэша.
static constexpr u8 STAGE_TARGET_SECTORS = 65;
static constexpr u8 STAGE_SMALL_SECTORS = 17;
static constexpr u8 STAGE_MIN_SECTORS = 4;
static constexpr u16 STAGE_TARGET_MIN_PHYSICAL_SECTORS = 512; // 2 MiB

// inode C5 занимает во флеш-памяти 20 байт. Для 31-байтового базового имени
// с самым длинным создаваемым расширением нужно не более четырёх записей LFN
// и одной короткой записи.
static constexpr u8 INODE_BYTES = 20;
static constexpr u8 MAX_DIRENTS_PER_NODE = 5;
// Метка тома и три записи (две LFN и одна короткая), необходимые для маркера
// macOS .metadata_never_index нулевой длины.
static constexpr u8 ROOT_SYSTEM_DIRENTS = 4;
// Корневые каталоги FAT12/FAT16 — это массивы фиксированного размера, а не
// обычные цепочки кластеров. Размер массива для всех возможных узлов C5 давал
// корневой каталог объёмом 630 КиБ на носителе 16 МиБ; настольные драйверы FAT
// могут перезаписывать значительную его часть при создании каждой записи.
// 512 записей — общепринятая переносимая геометрия, оставляющая 508 записей
// для пользовательских объектов. Произвольные подкаталоги используют цепочки
// кластеров и предоставляют полную квоту узлов всего тома.
static constexpr u16 ROOT_ENTRY_CAPACITY = 512;

struct Geometry {
  u32 capacity_bytes;
  u32 physical_sectors;

  u32 locator_a_sector;
  u32 locator_b_sector;
  u32 catalog_a_sector;
  u32 catalog_b_sector;
  u16 catalog_table_sectors;
  u16 catalog_bank_sectors;
  u32 data_first_sector;
  u32 data_sector_count;
  u32 stage_first_sector;
  u16 stage_sector_count;
  u32 settings_sector;

  u16 max_nodes;
  u8 sectors_per_cluster;
  u16 fat_sectors;
  u16 root_entries;
  u16 root_sectors;
  u32 logical_sectors;
};

// Вычисляет самосогласованную разметку. Возвращает false для микросхем, слишком
// малых для двух атомарных банков каталога, журнала промежуточных данных,
// настроек и резерва GC.
bool compute(u32 capacity_bytes, Geometry& out);

} // пространство имён storage_geometry

#endif
