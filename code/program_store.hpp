#ifndef PROGRAM_STORE_HPP
#define PROGRAM_STORE_HPP

#include "rust_types.h"
#include "mk61emu_core.h"

namespace program_store {

static constexpr usize NAME_SIZE = 16;
static constexpr usize MAX_ENTRIES = 64;
static constexpr u16 MAX_MK61_TEXT_SIZE = 1536;

enum class ProgramType : u8 {
  MK61,
  BASIC,
  FOCAL,
  TINYBASIC,
  TEXT,
  MK61_STATE
};

struct Entry {
  ProgramType type;
  char name[NAME_SIZE];
  u16 data_len;
};

void init(void);
bool format(void);
bool refresh(void);

int count(ProgramType type);
bool entry(ProgramType type, int index, Entry& out);
bool exists(ProgramType type, const char* name);

bool write(ProgramType type, const char* name, const u8* data, u16 data_len);
bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len);
bool read_range(ProgramType type, const char* name, u16 offset, u8* data, u16 len, u16* out_len);
bool remove(ProgramType type, const char* name);
u16 purge_empty(void);
bool rename(ProgramType type, const char* old_name, const char* new_name);

bool vfat_stage_write(u16 cluster, const u8* data);
bool vfat_stage_read(u16 cluster, u8* data);
bool vfat_stage_exists(u16 cluster);
void vfat_stage_forget(u16 start_cluster, u16 clusters);
void vfat_stage_clear(void);

bool write_mk61(const char* name, const u8* code, u16 code_len);
bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len);

} // namespace program_store

#endif
