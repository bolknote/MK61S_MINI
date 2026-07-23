#ifndef PROGRAM_STORE_HPP
#define PROGRAM_STORE_HPP

#include "rust_types.h"
#include "mk61emu_core.h"
#include "storage_geometry.hpp"

namespace program_store {

static constexpr usize NAME_SIZE = 32;
// Логический размер файла, предоставляемый хранилищем и виртуальной FAT.
static constexpr u16 MAX_MK61_TEXT_SIZE = 1536;
static constexpr u16 MAX_FONT_SIZE = 1536;
// 1600 байт вмещают полный WBMP Type 0 192x64 с заголовком и по-прежнему
// гарантированно помещаются в минимальный 2-КиБ FAT-кластер C5.
static constexpr u16 MAX_IMAGE1_SIZE = 1600;
// Контейнер APP: 64-байтовый заголовок и не более 20 КиБ образа SRAM.
// Хранилище читает его блоками и не требует такого же буфера в ОЗУ.
static constexpr u16 MAX_APP_FILE_SIZE = 20U * 1024U + 64U;
// Верхняя граница служебных продолжений FAT у одного максимального APP
// вычисляется для минимального допустимого 2-КиБ кластера. На штатной W25Q128
// с кластером 4 КиБ реально используются только пять. Это не лимит количества
// APP: файлов может быть столько, сколько помещается в C5 и каталогах.
static constexpr u16 MIN_FAT_CLUSTER_SIZE =
    (u16) storage_geometry::MIN_SECTORS_PER_CLUSTER *
    storage_geometry::LOGICAL_SECTOR_SIZE;
static constexpr u8 MAX_FAT_EXTENTS_PER_FILE =
    (u8) ((MAX_APP_FILE_SIZE + MIN_FAT_CLUSTER_SIZE - 1U) /
          MIN_FAT_CLUSTER_SIZE - 1U);

enum class ProgramType : u8 {
  MK61 = 0,
  FOCAL = 2,
  TINYBASIC = 3,
  TEXT = 4,
  MK61_STATE = 5,
  FONT = 6,
  IMAGE1 = 7,
  APP = 8
};

enum class NodeKind : u8 {
  FILE = 0,
  DIRECTORY = 1,
  DIRECTORY_EXTENT = 2,
  FILE_EXTENT = 3
};

static constexpr u16 ROOT_ID = 0xFFFF;
static constexpr u16 INVALID_ID = 0xFFFF;
// Синхронизировано с обходчиком виртуальной FAT. Это ограничивает обход
// предков без стека и не позволяет создать дерево, непредставимое через USB.
static constexpr u8 MAX_DIRECTORY_DEPTH = 32;

struct Entry {
  ProgramType type;
  char name[NAME_SIZE];
  u16 data_len;
  u16 id;
  u16 parent_id;
  NodeKind kind;
};

struct FileSource {
  void* context;
  bool (*read)(void* context, u32 offset, u8* output, usize size);
};

enum class MountStatus : u8 {
  UNAVAILABLE = 0,
  READY,
  REPAIR_REQUIRED
};

void init(void);
bool format(void);
bool refresh(void);
bool ready(void);
MountStatus mount_status(void);
const storage_geometry::Geometry& geometry(void);
u16 max_nodes(void);
u16 used_nodes(void);
bool basename_valid(const char* name);
u32 settings_address(void);
u16 settings_size(void);
bool erase_settings(void);
const char* file_extension(ProgramType type);

int count(ProgramType type);
bool entry(ProgramType type, int index, Entry& out);
int total_count(void);
bool entry_at(int index, Entry& out);
bool entry_by_id(u16 id, Entry& out);
int child_count(u16 parent_id);
bool child(u16 parent_id, int index, Entry& out);
bool exists(ProgramType type, const char* name);

bool write(ProgramType type, const char* name, const u8* data, u16 data_len);
// Импорт через USB не тратит время на сжатие, пока исходные данные помещаются в хранилище.
bool write_from_usb(ProgramType type, const char* name, const u8* data, u16 data_len);
bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len);
bool read_range(ProgramType type, const char* name, u16 offset, u8* data, u16 len, u16* out_len);
bool remove(ProgramType type, const char* name);
u16 purge_empty(void);
bool rename(ProgramType type, const char* old_name, const char* new_name);

bool create_directory(u16 parent_id, const char* name, u16 preferred_id,
                      u16* out_id = nullptr);
bool write_file(u16 parent_id, u16 preferred_id, ProgramType type,
                const char* name, const u8* data, u16 data_len,
                u16* out_id = nullptr);
// Потоковый вариант не держит файл целиком в SRAM. Для большого файла
// fat_extents задаёт идентификаторы последующих FAT-кластеров; при NULL C5
// выбирает свободные узлы самостоятельно.
bool write_file_from_source(u16 parent_id, u16 preferred_id, ProgramType type,
                            const char* name, u16 data_len,
                            const FileSource& source,
                            const u16* fat_extents = nullptr,
                            u8 fat_extent_count = 0,
                            u16* out_id = nullptr);
bool read_id(u16 id, u8* data, u16 capacity, u16* out_len);
bool read_range_id(u16 id, u16 offset, u8* data, u16 len, u16* out_len);
bool remove_id(u16 id);
bool remove_tree(u16 id, u16* removed = nullptr);
bool move_rename(u16 id, u16 new_parent_id, const char* new_name);
bool allocate_directory_extent(u16 directory_id, u16 preferred_id);
bool release_directory_extent(u16 extent_id);
bool first_extent(u16 directory_id, u16& out_id);
bool next_extent(u16 id, u16& out_id);
bool extent_info(u16 extent_id, u16& directory_id, u16& next_id);
bool first_file_extent(u16 file_id, u16& out_id);
bool next_file_extent(u16 id, u16& out_id);
bool file_extent_info(u16 extent_id, u16& file_id, u8& cluster_index,
                      u16& next_id);
// Атомарно отделяет служебный FAT-extent от большого файла и перенумеровывает
// оставшуюся цепочку. Используется VFAT после полного read-only preflight,
// когда host повторно выделил этот кластер другому узлу.
bool release_file_extent(u16 extent_id);

static constexpr u16 VFAT_STAGE_BLOCK_SIZE = 512;
static constexpr u32 VFAT_STAGE_KEY_MAX = 0x007FFFFFUL;

bool vfat_stage_write(u32 block, const u8* data);
bool vfat_stage_read(u32 block, u8* data);
bool vfat_stage_exists(u32 block);
u16 vfat_stage_count(void);
void vfat_stage_forget(u32 start_block, u16 blocks);
bool vfat_stage_discard_all(void);
void vfat_stage_clear(void);

#if defined(PROGRAM_STORE_HOST_TEST)
// Создаёт на томе настоящий каталог/локаторы C5 v5 для проверки миграции v6.
bool test_rewrite_catalog_as_v5(void);
#endif

bool write_mk61(const char* name, const u8* code, u16 code_len);
bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len);

} // пространство имён program_store

#endif
