#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../code/program_store.hpp"

namespace {

struct StoredProgram {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u8 data[700];
  u16 data_len;
};

static StoredProgram programs[16];

static StoredProgram* find_program(program_store::ProgramType type, const char* name) {
  for(StoredProgram& program : programs) {
    if(!program.used || program.type != type) continue;
    if(strncmp(program.name, name, program_store::NAME_SIZE) == 0) return &program;
  }
  return NULL;
}

static StoredProgram* allocate_program(void) {
  for(StoredProgram& program : programs) {
    if(!program.used) return &program;
  }
  return NULL;
}

static u16 read_le16(const u8* data, u16 offset) {
  return (u16) (data[offset] | ((u16) data[offset + 1] << 8));
}

static void write_le16(u8* data, u16 offset, u16 value) {
  data[offset] = (u8) (value & 0xFF);
  data[offset + 1] = (u8) (value >> 8);
}

static void write_le32(u8* data, u16 offset, u32 value) {
  data[offset] = (u8) (value & 0xFF);
  data[offset + 1] = (u8) ((value >> 8) & 0xFF);
  data[offset + 2] = (u8) ((value >> 16) & 0xFF);
  data[offset + 3] = (u8) ((value >> 24) & 0xFF);
}

} // namespace

namespace program_store {

void init(void) {}

bool format(void) {
  memset(programs, 0, sizeof(programs));
  return true;
}

bool refresh(void) {
  return true;
}

int count(ProgramType type) {
  int result = 0;
  for(const StoredProgram& program : programs) {
    if(program.used && program.type == type) result++;
  }
  return result;
}

bool entry(ProgramType type, int index, Entry& out) {
  int seen = 0;
  for(const StoredProgram& program : programs) {
    if(!program.used || program.type != type) continue;
    if(seen++ != index) continue;
    out.type = program.type;
    strncpy(out.name, program.name, NAME_SIZE - 1);
    out.name[NAME_SIZE - 1] = 0;
    out.data_len = program.data_len;
    return true;
  }
  return false;
}

bool exists(ProgramType type, const char* name) {
  return find_program(type, name) != NULL;
}

bool write(ProgramType type, const char* name, const u8* data, u16 data_len) {
  if(name == NULL || name[0] == 0 || data_len > sizeof(programs[0].data)) return false;
  StoredProgram* program = find_program(type, name);
  if(program == NULL) program = allocate_program();
  if(program == NULL) return false;

  memset(program, 0, sizeof(*program));
  program->used = true;
  program->type = type;
  strncpy(program->name, name, NAME_SIZE - 1);
  program->name[NAME_SIZE - 1] = 0;
  if(data_len != 0) memcpy(program->data, data, data_len);
  program->data_len = data_len;
  return true;
}

bool read(ProgramType type, const char* name, u8* data, u16 capacity, u16* out_len) {
  StoredProgram* program = find_program(type, name);
  if(program == NULL || data == NULL || capacity < program->data_len) return false;
  if(program->data_len != 0) memcpy(data, program->data, program->data_len);
  if(out_len != NULL) *out_len = program->data_len;
  return true;
}

bool read_range(ProgramType type, const char* name, u16 offset, u8* data, u16 len, u16* out_len) {
  StoredProgram* program = find_program(type, name);
  if(program == NULL || data == NULL || offset > program->data_len) return false;
  const u16 available = (u16) (program->data_len - offset);
  const u16 copied = (available < len) ? available : len;
  if(copied != 0) memcpy(data, program->data + offset, copied);
  if(out_len != NULL) *out_len = copied;
  return true;
}

bool remove(ProgramType type, const char* name) {
  StoredProgram* program = find_program(type, name);
  if(program == NULL) return false;
  memset(program, 0, sizeof(*program));
  return true;
}

bool rename(ProgramType type, const char* old_name, const char* new_name) {
  StoredProgram* program = find_program(type, old_name);
  if(program == NULL || new_name == NULL || new_name[0] == 0) return false;
  strncpy(program->name, new_name, NAME_SIZE - 1);
  program->name[NAME_SIZE - 1] = 0;
  return true;
}

bool write_mk61(const char* name, const u8* code, u16 code_len) {
  return write(ProgramType::MK61, name, code, code_len);
}

bool read_mk61(const char* name, u8* code, u16 capacity, u16* out_len) {
  u16 len = 0;
  if(!read(ProgramType::MK61, name, code, capacity, &len)) return false;
  if(out_len != NULL) *out_len = len;
  return true;
}

} // namespace program_store

#include "../code/virtual_fat.cpp"

namespace {

static void reset_virtual_fat_state(void) {
  program_store::format();
  memset(virtual_fat::pending_writes, 0, sizeof(virtual_fat::pending_writes));
  memset(virtual_fat::pending_deletes, 0, sizeof(virtual_fat::pending_deletes));
  memset(virtual_fat::write_cache, 0, sizeof(virtual_fat::write_cache));
  memset(virtual_fat::ignored_ranges, 0, sizeof(virtual_fat::ignored_ranges));
  memset(&virtual_fat::root_lfn_state, 0, sizeof(virtual_fat::root_lfn_state));
  virtual_fat::root_lfn_next_sector = 0;
  virtual_fat::next_cache_slot = 0;
  virtual_fat::next_ignored_slot = 0;
}

static u32 root_lba(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  return read_le16(boot, 14) + (u32) boot[16] * read_le16(boot, 22);
}

static u32 data_lba(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  const u16 root_entries = read_le16(boot, 17);
  const u32 root_sectors = ((u32) root_entries * 32 + virtual_fat::SECTOR_SIZE - 1) / virtual_fat::SECTOR_SIZE;
  return root_lba() + root_sectors;
}

static void fill_short_dir_entry(u8* entry, const char* short_name, u16 cluster, u32 len) {
  memset(entry, 0, 32);
  memcpy(entry, short_name, 11);
  entry[11] = 0x20;
  write_le16(entry, 26, cluster);
  write_le32(entry, 28, len);
}

static void test_lfn_aliases_are_unique(void) {
  reset_virtual_fat_state();

  const u8 byte = 0x42;
  assert(program_store::write(program_store::ProgramType::MK61, "ALPHA-BETA", &byte, 1));
  assert(program_store::write(program_store::ProgramType::MK61, "ALPHA_BETA", &byte, 1));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  u8 short_names[2][11];
  int short_count = 0;
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root + (u16) i * 32;
    if(entry[0] == 0 || entry[11] != 0x20) continue;
    assert(short_count < 2);
    memcpy(short_names[short_count++], entry, 11);
  }

  assert(short_count == 2);
  assert(memcmp(short_names[0], short_names[1], 11) != 0);
  assert(short_names[0][5] == '~');
  assert(short_names[1][5] == '~');
}

static void test_incomplete_pending_flush_fails_until_data_arrives(void) {
  reset_virtual_fat_state();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "NEW     M61", 2, 100);

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(!virtual_fat::flush_pending());
  assert(!program_store::exists(program_store::ProgramType::MK61, "NEW"));

  u8 data[virtual_fat::SECTOR_SIZE];
  memset(data, 0x5A, sizeof(data));
  assert(virtual_fat::write_sector(data_lba(), data));
  assert(virtual_fat::flush_pending());

  u8 stored[100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "NEW", stored, sizeof(stored), &stored_len));
  assert(stored_len == 100);
  assert(stored[0] == 0x5A);
  assert(stored[99] == 0x5A);
}

static void test_pending_delete_queue_overflow_fails(void) {
  reset_virtual_fat_state();

  const u8 byte = 0x24;
  assert(program_store::write(program_store::ProgramType::MK61, "P0", &byte, 1));
  assert(program_store::write(program_store::ProgramType::MK61, "P1", &byte, 1));
  assert(program_store::write(program_store::ProgramType::MK61, "P2", &byte, 1));
  assert(program_store::write(program_store::ProgramType::MK61, "P3", &byte, 1));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  for(u8 i = 1; i <= 4; i++) root[(u16) i * 32] = 0xE5;

  assert(!virtual_fat::write_sector(root_lba(), root));
}

} // namespace

int main(void) {
  test_lfn_aliases_are_unique();
  test_incomplete_pending_flush_fails_until_data_arrives();
  test_pending_delete_queue_overflow_fails();
  printf("virtual_fat_self_test: ok\n");
  return 0;
}
