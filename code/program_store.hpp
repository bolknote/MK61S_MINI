#ifndef PROGRAM_STORE_HPP
#define PROGRAM_STORE_HPP

#include "rust_types.h"
#include "mk61emu_core.h"

namespace program_store {

static constexpr usize NAME_SIZE = 16;
static constexpr usize MAX_ENTRIES = 64;

enum class ProgramType : u8 {
  MK61,
  BASIC,
  FOCAL
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
bool remove(ProgramType type, const char* name);
bool rename(ProgramType type, const char* old_name, const char* new_name);

bool write_mk61(const char* name, const u8* code, u8 code_len);
bool read_mk61(const char* name, u8* code, u8 capacity, u8* out_len);

} // namespace program_store

#endif
