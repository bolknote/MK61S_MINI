#ifndef STORAGE_GEOMETRY_HPP
#define STORAGE_GEOMETRY_HPP

#include "rust_types.h"

namespace storage_geometry {

// Физическая геометрия SPI NOR для C5. Сектор виртуальной FAT остаётся
// 512-байтовым; физические секторы стирания никогда не видны USB-хосту.
static constexpr u32 PHYSICAL_SECTOR_SIZE = 4096;
static constexpr u16 LOGICAL_SECTOR_SIZE = 512;
static constexpr u16 FAT12_MAX_DATA_CLUSTERS = 4084;
static constexpr u8 MIN_SECTORS_PER_CLUSTER = 4;   // 2 КиБ, любой допустимый файл
static constexpr u8 MAX_SECTORS_PER_CLUSTER = 64;  // 32 КиБ, широкая совместимость

static constexpr u8 LOCATOR_SECTORS = 2;
static constexpr u8 SETTINGS_SECTORS = 1;
static constexpr u8 CATALOG_HEADER_SECTORS = 1;
static constexpr u8 CATALOG_WAL_SECTORS = 2;
static constexpr u8 CATALOG_BANKS = 2;
// Шестьдесят четыре обычных сегмента журнала содержат 448 физических записей
// максимум для 384 активных грязных блоков. Последний сегмент — резерв атомарного
// уплотнения. Дополнительные 192 КиБ несущественны на типичной микросхеме 16 МиБ
// и не дают современным настольным ФС исчерпать staging до синхронизации кеша.
static constexpr u8 STAGE_TARGET_SECTORS = 65;
static constexpr u8 STAGE_SMALL_SECTORS = 17;
static constexpr u8 STAGE_MIN_SECTORS = 4;
static constexpr u16 STAGE_TARGET_MIN_PHYSICAL_SECTORS = 512; // 2 МиБ

// Inode C5 занимает во flash 20 байт. Для 31-байтового базового имени с самым
// длинным создаваемым расширением нужно не более четырёх LFN и одной короткой записи.
static constexpr u8 INODE_BYTES = 20;
static constexpr u8 MAX_DIRENTS_PER_NODE = 5;
// Метка тома и три записи (две LFN и одна короткая), необходимые для пустого
// маркера macOS .metadata_never_index.
static constexpr u8 ROOT_SYSTEM_DIRENTS = 4;
// Корни FAT12/FAT16 — массивы фиксированного размера, а не обычные цепочки
// кластеров. Размер на каждый возможный узел C5 давал на томе 16 МиБ корень
// объёмом 630 КиБ; настольные драйверы FAT могут перезаписывать значительную его
// часть при создании каждой записи. 512 записей — общепринятая переносимая
// геометрия, оставляющая 508 записей пользовательским объектам. Произвольные
// подкаталоги используют цепочки кластеров и дают полную общую квоту узлов тома.
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

// Вычисляет самосогласованную разметку. Возвращает false для микросхем, где не
// помещаются два атомарных банка каталога, журнал staging, настройки и резерв GC.
bool compute(u32 capacity_bytes, Geometry& out);

} // пространство имён storage_geometry

#endif
