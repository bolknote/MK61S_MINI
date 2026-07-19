#ifndef PROGRAM_STORE_HPP
#define PROGRAM_STORE_HPP

#include "rust_types.h"
#include "mk61emu_core.h"
#include "storage_geometry.hpp"

namespace program_store {

static constexpr usize NAME_SIZE = 32;
// Logical file size exposed by the store and virtual FAT.
static constexpr u16 MAX_MK61_TEXT_SIZE = 1536;
static constexpr u16 MAX_FONT_SIZE = 1536;

enum class ProgramType : u8 {
  MK61 = 0,
  FOCAL = 2,
  TINYBASIC = 3,
  TEXT = 4,
  MK61_STATE = 5,
  FONT = 6
};

enum class NodeKind : u8 {
  FILE = 0,
  DIRECTORY = 1,
  DIRECTORY_EXTENT = 2
};

static constexpr u16 ROOT_ID = 0xFFFF;
static constexpr u16 INVALID_ID = 0xFFFF;
// Kept in lockstep with the virtual FAT walker.  This bounds stack-free
// ancestor walks and prevents a tree that cannot be represented over USB.
static constexpr u8 MAX_DIRECTORY_DEPTH = 32;

struct Entry {
  ProgramType type;
  char name[NAME_SIZE];
  u16 data_len;
  u16 id;
  u16 parent_id;
  NodeKind kind;
};

void init(void);
bool format(void);
bool refresh(void);
bool ready(void);
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
// USB imports avoid compression latency while the raw payload fits the store.
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

bool vfat_stage_write(u32 block, const u8* data);
bool vfat_stage_read(u32 block, u8* data);
bool vfat_stage_exists(u32 block);
u8 vfat_stage_count(void);
void vfat_stage_forget(u32 start_block, u16 blocks);
bool vfat_stage_discard_all(void);
void vfat_stage_clear(void);

bool write_mk61(const char* name, const u8* code, u16 code_len);
bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len);

} // namespace program_store

#endif
