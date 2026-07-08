#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../code/program_store.hpp"
#include "../code/language_workspace.hpp"

namespace {

struct StoredProgram {
  bool used;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
  u8 data[1536];
  u16 data_len;
};

static StoredProgram programs[16];

struct StagedSector {
  bool used;
  u16 cluster;
  u8 data[512];
};

static StagedSector staged_sectors[64];

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

static u32 read_le32(const u8* data, u16 offset) {
  return (u32) data[offset] |
         ((u32) data[offset + 1] << 8) |
         ((u32) data[offset + 2] << 16) |
         ((u32) data[offset + 3] << 24);
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

bool vfat_stage_write(u16 cluster, const u8* data) {
  if(data == NULL) return false;

  StagedSector* free_slot = NULL;
  for(StagedSector& staged : staged_sectors) {
    if(staged.used && staged.cluster == cluster) {
      memcpy(staged.data, data, sizeof(staged.data));
      return true;
    }
    if(!staged.used && free_slot == NULL) free_slot = &staged;
  }

  if(free_slot == NULL) return false;
  free_slot->used = true;
  free_slot->cluster = cluster;
  memcpy(free_slot->data, data, sizeof(free_slot->data));
  return true;
}

bool vfat_stage_read(u16 cluster, u8* data) {
  if(data == NULL) return false;
  for(StagedSector& staged : staged_sectors) {
    if(!staged.used || staged.cluster != cluster) continue;
    memcpy(data, staged.data, sizeof(staged.data));
    return true;
  }
  return false;
}

bool vfat_stage_exists(u16 cluster) {
  for(StagedSector& staged : staged_sectors) {
    if(staged.used && staged.cluster == cluster) return true;
  }
  return false;
}

void vfat_stage_forget(u16 start_cluster, u16 clusters) {
  for(StagedSector& staged : staged_sectors) {
    if(!staged.used) continue;
    if(staged.cluster >= start_cluster && staged.cluster < (u16) (start_cluster + clusters)) staged.used = false;
  }
}

void vfat_stage_clear(void) {
  memset(staged_sectors, 0, sizeof(staged_sectors));
}

} // namespace program_store

namespace language_workspace {

alignas(8) static u8 workspace[SIZE];
static Owner owner = Owner::NONE;

void* acquire(Owner next_owner, usize required) {
  if(required > sizeof(workspace)) return NULL;
  if(owner != next_owner) {
    memset(workspace, 0, sizeof(workspace));
    owner = next_owner;
  }
  return workspace;
}

Owner current_owner(void) {
  return owner;
}

} // namespace language_workspace

#include "../code/virtual_fat.cpp"

namespace {

static void reset_virtual_fat_state(void) {
  program_store::format();
  virtual_fat::reset_session();
}

static u32 root_lba(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  return read_le16(boot, 14) + (u32) boot[16] * read_le16(boot, 22);
}

static u32 fat_lba(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  return read_le16(boot, 14);
}

static u32 data_lba(void) {
  u8 boot[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(0, boot));
  const u16 root_entries = read_le16(boot, 17);
  const u32 root_sectors = ((u32) root_entries * 32 + virtual_fat::SECTOR_SIZE - 1) / virtual_fat::SECTOR_SIZE;
  return root_lba() + root_sectors;
}

static u16 fat12_entry(u16 cluster) {
  u8 fat[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(fat_lba(), fat));
  const u16 offset = (u16) (cluster + cluster / 2);
  u16 value = (u16) (fat[offset] | ((u16) fat[offset + 1] << 8));
  if((cluster & 1) != 0) value >>= 4;
  return (u16) (value & 0x0FFF);
}

static void fill_short_dir_entry(u8* entry, const char* short_name, u16 cluster, u32 len) {
  memset(entry, 0, 32);
  memcpy(entry, short_name, 11);
  entry[11] = 0x20;
  write_le16(entry, 26, cluster);
  write_le32(entry, 28, len);
}

static u16 utf16_len(const u16* text) {
  u16 len = 0;
  while(text[len] != 0) len++;
  return len;
}

static void fill_lfn_entry_utf16(u8* entry, const u16* full_name, u8 sequence, u8 total, u8 checksum) {
  static const u8 offsets[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
  memset(entry, 0xFF, 32);
  entry[0] = sequence;
  if(sequence == total) entry[0] |= 0x40;
  entry[11] = 0x0F;
  entry[12] = 0;
  entry[13] = checksum;
  entry[26] = 0;
  entry[27] = 0;

  const u16 full_len = utf16_len(full_name);
  for(u8 i = 0; i < 13; i++) {
    const u16 index = (u16) ((sequence - 1) * 13 + i);
    const u16 value = (index < full_len) ? full_name[index] : (index == full_len ? 0x0000 : 0xFFFF);
    write_le16(entry, offsets[i], value);
  }
}

static void fill_lfn_entries_utf16(u8* first_entry, const u16* full_name, const u8* short_name) {
  const u8 total = (u8) ((utf16_len(full_name) + 12) / 13);
  const u8 checksum = virtual_fat::short_name_checksum(short_name);
  for(u8 i = 0; i < total; i++) {
    const u8 sequence = (u8) (total - i);
    fill_lfn_entry_utf16(first_entry + (u16) i * 32, full_name, sequence, total, checksum);
  }
}

static bool lfn_equals_ascii(const u16* lfn_name, const char* expected) {
  if(lfn_name == NULL) return false;
  u16 i = 0;
  while(expected[i] != 0) {
    if(lfn_name[i] != (u8) expected[i]) return false;
    i++;
  }
  return lfn_name[i] == 0;
}

static bool root_has_lfn_name(const u8* root, const char* expected) {
  virtual_fat::LfnState lfn;
  memset(&lfn, 0, sizeof(lfn));
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root + (u16) i * 32;
    if(entry[0] == 0) {
      memset(&lfn, 0, sizeof(lfn));
      continue;
    }
    if((entry[11] & 0x3F) == 0x0F) {
      virtual_fat::parse_lfn_entry(entry, lfn);
      continue;
    }
    if(entry[11] == 0x20 && lfn_equals_ascii(virtual_fat::accepted_lfn_name(lfn, entry), expected)) return true;
    memset(&lfn, 0, sizeof(lfn));
  }
  return false;
}

static const u8* first_archive_entry(const u8* root) {
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root + (u16) i * 32;
    if(entry[0] != 0 && entry[11] == 0x20) return entry;
  }
  return NULL;
}

static u8 archive_entry_count(const u8* root) {
  u8 count = 0;
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root + (u16) i * 32;
    if(entry[0] != 0 && entry[11] == 0x20) count++;
  }
  return count;
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

static void test_incomplete_pending_flush_keeps_waiting_for_data(void) {
  reset_virtual_fat_state();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "NEW     M61", 2, 100);

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());
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

static void test_short_txt_import_stores_text_type(void) {
  reset_virtual_fat_state();

  const char payload[] = "plain text\n";
  u8 data[virtual_fat::SECTOR_SIZE];
  memset(data, 0, sizeof(data));
  memcpy(data, payload, sizeof(payload) - 1);
  assert(virtual_fat::write_sector(data_lba(), data));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "README  TXT", 2, sizeof(payload) - 1);
  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 stored[32];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::TEXT, "README", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(payload) - 1);
  assert(memcmp(stored, payload, stored_len) == 0);
}

static void test_m61_lfn_import_normalizes_cyrillic_name(void) {
  reset_virtual_fat_state();

  const u16 full_name[] = {
    0x043A, 0x043B, 0x0430, 0x0434, 0x043E, 0x0438, 0x0441, 0x043A, 0x0430, 0x0442, 0x0435, 0x043B, 0x044C,
    '.', 'm', '6', '1',
    0
  };
  const u8 short_name[11] = {'K', 'L', 'A', 'D', 'O', 'I', '~', '1', 'M', '6', '1'};
  const u8 payload[] = {0x01, 0x02, 0x03};

  u8 data[virtual_fat::SECTOR_SIZE];
  memset(data, 0, sizeof(data));
  memcpy(data, payload, sizeof(payload));
  assert(virtual_fat::write_sector(data_lba(), data));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_lfn_entries_utf16(root + 32, full_name, short_name);
  fill_short_dir_entry(root + 32 * 3, (const char*) short_name, 2, sizeof(payload));
  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 stored[8];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "KLADO", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(payload));
  assert(memcmp(stored, payload, stored_len) == 0);
}

static void test_state_txt_lfn_import_normalizes_cyrillic(void) {
  reset_virtual_fat_state();

  const u16 full_name[] = {
    0x043A, 0x043E, 0x043E, 0x043F, 0x0435, 0x0440, 0x0430, 0x0442, 0x0438, 0x0432, 0x043D, 0x043E, 0x0435,
    ' ',
    0x043A, 0x0430, 0x0444, 0x0435,
    ' ', '2',
    '.', 's', 't', 'a', 't', 'e', '.', 't', 'x', 't',
    0
  };
  const u8 short_name[11] = {'K', 'O', 'O', 'P', 'E', 'R', '~', '1', 'T', 'X', 'T'};
  const char payload[] = "{\"pc\":0,\"stack\":[1,2,3]}\n";

  u8 data[virtual_fat::SECTOR_SIZE];
  memset(data, 0, sizeof(data));
  memcpy(data, payload, sizeof(payload) - 1);
  assert(virtual_fat::write_sector(data_lba(), data));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_lfn_entries_utf16(root + 32, full_name, short_name);
  fill_short_dir_entry(root + 32 * 4, (const char*) short_name, 2, sizeof(payload) - 1);
  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 stored[64];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61_STATE, "KOOPEKAFE2", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(payload) - 1);
  assert(memcmp(stored, payload, stored_len) == 0);

  u8 generated_root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), generated_root));
  assert(root_has_lfn_name(generated_root, "KOOPEKAFE2.state.txt"));
}

static void test_staging_does_not_shadow_committed_file_data(void) {
  reset_virtual_fat_state();

  u8 committed[100];
  memset(committed, 0x31, sizeof(committed));
  assert(program_store::write(program_store::ProgramType::MK61, "OLD", committed, sizeof(committed)));

  u8 staged[virtual_fat::SECTOR_SIZE];
  memset(staged, 0x62, sizeof(staged));
  assert(program_store::vfat_stage_write(2, staged));

  u8 readback[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba(), readback));
  assert(readback[0] == 0x31);
  assert(readback[99] == 0x31);
  assert(readback[100] == 0);
}

static void test_staged_cluster_is_not_advertised_as_free(void) {
  reset_virtual_fat_state();

  u8 staged[virtual_fat::SECTOR_SIZE];
  memset(staged, 0x72, sizeof(staged));
  assert(program_store::vfat_stage_write(2, staged));

  assert(fat12_entry(2) == 0x0FFF);
}

static void test_staging_survives_mass_copy_before_directory_update(void) {
  reset_virtual_fat_state();

  static const u8 FILES = 12;
  u8 sector[virtual_fat::SECTOR_SIZE];
  for(u8 i = 0; i < FILES; i++) {
    memset(sector, (int) (0x40 + i), sizeof(sector));
    assert(virtual_fat::write_sector(data_lba() + i, sector));
  }

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  for(u8 i = 0; i < FILES; i++) {
    char short_name[12] = "F00     M61";
    short_name[1] = (char) ('0' + i / 10);
    short_name[2] = (char) ('0' + i % 10);
    fill_short_dir_entry(root + (u16) (i + 1) * 32, short_name, (u16) (2 + i), (u32) (100 + i));
  }

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  for(u8 i = 0; i < FILES; i++) {
    char name[program_store::NAME_SIZE];
    snprintf(name, sizeof(name), "F%02u", (unsigned) i);
    u8 stored[128];
    u16 stored_len = 0;
    assert(program_store::read(program_store::ProgramType::MK61, name, stored, sizeof(stored), &stored_len));
    assert(stored_len == (u16) (100 + i));
    assert(stored[0] == (u8) (0x40 + i));
    assert(stored[stored_len - 1] == (u8) (0x40 + i));
  }
}

static void test_many_pending_directory_entries_wait_for_late_data(void) {
  reset_virtual_fat_state();

  static const u8 FILES = 12;
  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  for(u8 i = 0; i < FILES; i++) {
    char short_name[12] = "L00     M61";
    short_name[1] = (char) ('0' + i / 10);
    short_name[2] = (char) ('0' + i % 10);
    fill_short_dir_entry(root + (u16) (i + 1) * 32, short_name, (u16) (2 + i), (u32) (100 + i));
  }

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());
  for(u8 i = 0; i < FILES; i++) {
    char name[program_store::NAME_SIZE];
    snprintf(name, sizeof(name), "L%02u", (unsigned) i);
    assert(!program_store::exists(program_store::ProgramType::MK61, name));
  }

  u8 sector[virtual_fat::SECTOR_SIZE];
  for(u8 i = 0; i < FILES; i++) {
    memset(sector, (int) (0x60 + i), sizeof(sector));
    assert(virtual_fat::write_sector(data_lba() + i, sector));
  }
  assert(virtual_fat::flush_pending());

  for(u8 i = 0; i < FILES; i++) {
    char name[program_store::NAME_SIZE];
    snprintf(name, sizeof(name), "L%02u", (unsigned) i);
    u8 stored[128];
    u16 stored_len = 0;
    assert(program_store::read(program_store::ProgramType::MK61, name, stored, sizeof(stored), &stored_len));
    assert(stored_len == (u16) (100 + i));
    assert(stored[0] == (u8) (0x60 + i));
    assert(stored[stored_len - 1] == (u8) (0x60 + i));
  }
}

static void test_hidden_stored_entries_do_not_shift_visible_files(void) {
  reset_virtual_fat_state();

  u8 hidden[512];
  memset(hidden, 0xA7, sizeof(hidden));
  assert(program_store::write(program_store::ProgramType::FOCAL, "_PI", hidden, sizeof(hidden)));

  u8 visible[169];
  memset(visible, 0x51, sizeof(visible));
  assert(program_store::write(program_store::ProgramType::FOCAL, "PI", visible, sizeof(visible)));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  assert(archive_entry_count(root) == 1);

  const u8* pi_entry = first_archive_entry(root);
  assert(pi_entry != NULL);
  assert(memcmp(pi_entry, "PI      FOC", 11) == 0);
  assert(read_le16(pi_entry, 26) == 2);
  assert(read_le32(pi_entry, 28) == sizeof(visible));

  u8 readback[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba(), readback));
  assert(readback[0] == 0x51);
  assert(readback[168] == 0x51);
  assert(readback[169] == 0);
}

static void test_appledouble_entry_does_not_relocate_visible_file(void) {
  reset_virtual_fat_state();

  const u16 sidecar_cluster = 2;
  const u16 real_cluster = 10;

  u8 sidecar[virtual_fat::SECTOR_SIZE];
  memset(sidecar, 0xA5, sizeof(sidecar));
  for(u8 i = 0; i < 8; i++) {
    assert(virtual_fat::write_sector(data_lba() + i, sidecar));
  }

  u8 real[virtual_fat::SECTOR_SIZE];
  memset(real, 0x51, sizeof(real));
  assert(virtual_fat::write_sector(data_lba() + real_cluster - 2, real));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  const u8 hidden_short[11] = {'_', 'P', 'I', ' ', ' ', ' ', ' ', ' ', 'F', 'O', 'C'};
  virtual_fat::fill_lfn_entry(root + 32, "._PI.FOC", 1, 1, virtual_fat::short_name_checksum(hidden_short));
  fill_short_dir_entry(root + 64, "_PI     FOC", sidecar_cluster, 4096);
  fill_short_dir_entry(root + 96, "PI      FOC", real_cluster, 169);

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());
  assert(!program_store::exists(program_store::ProgramType::FOCAL, "_PI"));

  u8 stored[169];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::FOCAL, "PI", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(stored));
  assert(stored[0] == 0x51);
  assert(stored[168] == 0x51);

  u8 generated_root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), generated_root));
  assert(archive_entry_count(generated_root) == 1);
  const u8* pi_entry = first_archive_entry(generated_root);
  assert(pi_entry != NULL);
  assert(memcmp(pi_entry, "PI      FOC", 11) == 0);
  assert(read_le16(pi_entry, 26) == real_cluster);
  assert(read_le32(pi_entry, 28) == sizeof(stored));

  assert(fat12_entry(sidecar_cluster) == 0x000);
  assert(fat12_entry(real_cluster) == 0x0FFF);

  u8 readback[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba() + real_cluster - 2, readback));
  assert(readback[0] == 0x51);
  assert(readback[168] == 0x51);
  assert(readback[169] == 0);

  u8 free_read[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba(), free_read));
  assert(free_read[0] == 0);
}

static void test_ignored_directory_does_not_relocate_visible_file(void) {
  reset_virtual_fat_state();

  const u16 dir_cluster = 2;
  const u16 real_cluster = 3;

  u8 dir_data[virtual_fat::SECTOR_SIZE];
  memset(dir_data, 0xD1, sizeof(dir_data));
  assert(virtual_fat::write_sector(data_lba() + dir_cluster - 2, dir_data));

  u8 real[virtual_fat::SECTOR_SIZE];
  memset(real, 0x52, sizeof(real));
  assert(virtual_fat::write_sector(data_lba() + real_cluster - 2, real));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "FSEVENTS   ", dir_cluster, 0);
  root[32 + 11] = 0x10;
  fill_short_dir_entry(root + 64, "PI      FOC", real_cluster, 169);

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 generated_root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), generated_root));
  assert(archive_entry_count(generated_root) == 1);
  const u8* pi_entry = first_archive_entry(generated_root);
  assert(pi_entry != NULL);
  assert(memcmp(pi_entry, "PI      FOC", 11) == 0);
  assert(read_le16(pi_entry, 26) == real_cluster);

  assert(fat12_entry(dir_cluster) == 0x000);
  assert(fat12_entry(real_cluster) == 0x0FFF);

  u8 readback[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba() + real_cluster - 2, readback));
  assert(readback[0] == 0x52);
  assert(readback[168] == 0x52);
  assert(readback[169] == 0);
}

static void test_recreated_generated_entry_cancels_pending_delete(void) {
  reset_virtual_fat_state();

  u8 old_data[100];
  memset(old_data, 0x31, sizeof(old_data));
  assert(program_store::write(program_store::ProgramType::MK61, "WUMPUS", old_data, sizeof(old_data)));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  u8 deleted_root[virtual_fat::SECTOR_SIZE];
  memcpy(deleted_root, root, sizeof(deleted_root));
  deleted_root[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), deleted_root));

  u8 new_data[virtual_fat::SECTOR_SIZE];
  memset(new_data, 0x77, sizeof(new_data));
  assert(virtual_fat::write_sector(data_lba(), new_data));

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 stored[100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "WUMPUS", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(stored));
  assert(stored[0] == 0x77);
  assert(stored[99] == 0x77);
}

static void test_rewrite_after_delete_cancels_pending_delete(void) {
  reset_virtual_fat_state();

  u8 old_data[100];
  memset(old_data, 0x41, sizeof(old_data));
  assert(program_store::write(program_store::ProgramType::MK61, "F00", old_data, sizeof(old_data)));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  root[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), root));

  u8 new_sector[virtual_fat::SECTOR_SIZE];
  memset(new_sector, 0x62, sizeof(new_sector));
  assert(virtual_fat::write_sector(data_lba() + 1, new_sector));

  u8 new_root[virtual_fat::SECTOR_SIZE];
  memset(new_root, 0, sizeof(new_root));
  assert(virtual_fat::read_sector(root_lba(), new_root));
  fill_short_dir_entry(new_root + 32, "F00     M61", 3, sizeof(old_data));
  assert(virtual_fat::write_sector(root_lba(), new_root));
  assert(virtual_fat::flush_pending());

  u8 stored[100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "F00", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(stored));
  assert(stored[0] == 0x62);
  assert(stored[99] == 0x62);
}

static void test_ignored_range_data_can_be_reclassified(void) {
  reset_virtual_fat_state();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "_TMP    M61", 2, 4096);
  assert(virtual_fat::write_sector(root_lba(), root));

  u8 data[virtual_fat::SECTOR_SIZE];
  memset(data, 0x73, sizeof(data));
  assert(virtual_fat::write_sector(data_lba(), data));

  u8 real_root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), real_root));
  fill_short_dir_entry(real_root + 32, "REAL    M61", 2, 100);
  assert(virtual_fat::write_sector(root_lba(), real_root));
  assert(virtual_fat::flush_pending());

  u8 stored[100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "REAL", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(stored));
  assert(stored[0] == 0x73);
  assert(stored[99] == 0x73);
}

static void test_stale_directory_entries_do_not_cancel_deletes(void) {
  reset_virtual_fat_state();

  const u8 byte = 0x55;
  assert(program_store::write(program_store::ProgramType::MK61, "WUMPUS", &byte, 1));
  assert(program_store::write(program_store::ProgramType::FOCAL, "PI", &byte, 1));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  u8 delete_pi[virtual_fat::SECTOR_SIZE];
  memcpy(delete_pi, root, sizeof(delete_pi));
  delete_pi[64] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), delete_pi));

  u8 delete_wumpus_with_stale_pi[virtual_fat::SECTOR_SIZE];
  memcpy(delete_wumpus_with_stale_pi, root, sizeof(delete_wumpus_with_stale_pi));
  delete_wumpus_with_stale_pi[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), delete_wumpus_with_stale_pi));

  assert(virtual_fat::flush_pending());
  assert(!program_store::exists(program_store::ProgramType::MK61, "WUMPUS"));
  assert(!program_store::exists(program_store::ProgramType::FOCAL, "PI"));
}

static void test_mass_delete_queues_whole_directory_sector(void) {
  reset_virtual_fat_state();

  static const u8 FILES = 12;
  const u8 byte = 0x24;
  for(u8 i = 0; i < FILES; i++) {
    char name[program_store::NAME_SIZE];
    snprintf(name, sizeof(name), "P%02u", (unsigned) i);
    assert(program_store::write(program_store::ProgramType::MK61, name, &byte, 1));
  }

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  for(u8 i = 1; i <= FILES; i++) root[(u16) i * 32] = 0xE5;

  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  for(u8 i = 0; i < FILES; i++) {
    char name[program_store::NAME_SIZE];
    snprintf(name, sizeof(name), "P%02u", (unsigned) i);
    assert(!program_store::exists(program_store::ProgramType::MK61, name));
  }
}

// rm + copy of a new file into the clusters the host just freed must not
// resurrect the deleted file or corrupt the new one.
static void test_delete_then_reuse_clusters_keeps_delete_and_new_file(void) {
  reset_virtual_fat_state();

  u8 old_data[600];
  memset(old_data, 0x11, sizeof(old_data));
  assert(program_store::write(program_store::ProgramType::MK61, "OLDGAME", old_data, sizeof(old_data)));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  const u8* old_entry = first_archive_entry(root);
  assert(old_entry != NULL);
  const u16 old_cluster = read_le16(old_entry, 26);

  u8 deleted_root[virtual_fat::SECTOR_SIZE];
  memcpy(deleted_root, root, sizeof(deleted_root));
  deleted_root[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), deleted_root));

  // Host reuses the freed clusters for a different file.
  u8 sector[virtual_fat::SECTOR_SIZE];
  memset(sector, 0x22, sizeof(sector));
  assert(virtual_fat::write_sector(data_lba() + (old_cluster - 2), sector));

  u8 new_root[virtual_fat::SECTOR_SIZE];
  memcpy(new_root, deleted_root, sizeof(new_root));
  fill_short_dir_entry(new_root + 64, "NEWGAME M61", old_cluster, 300);
  assert(virtual_fat::write_sector(root_lba(), new_root));
  assert(virtual_fat::flush_pending());

  assert(!program_store::exists(program_store::ProgramType::MK61, "OLDGAME"));

  u8 stored[300];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "NEWGAME", stored, sizeof(stored), &stored_len));
  assert(stored_len == 300);
  assert(stored[0] == 0x22);
  assert(stored[299] == 0x22);
}

// Deleting one file must not move the clusters of the remaining files while
// the host stays mounted (the host caches FAT and directory).
static void test_delete_does_not_shift_other_files_clusters(void) {
  reset_virtual_fat_state();

  u8 data_a[400];
  memset(data_a, 0xAA, sizeof(data_a));
  u8 data_b[400];
  memset(data_b, 0xBB, sizeof(data_b));
  assert(program_store::write(program_store::ProgramType::MK61, "AAA", data_a, sizeof(data_a)));
  assert(program_store::write(program_store::ProgramType::MK61, "BBB", data_b, sizeof(data_b)));
  virtual_fat::reset_session();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  u16 cluster_b_before = 0;
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root + (u16) i * 32;
    if(entry[0] != 0 && entry[11] == 0x20 && memcmp(entry, "BBB     M61", 11) == 0) {
      cluster_b_before = read_le16(entry, 26);
    }
  }
  assert(cluster_b_before != 0);

  u8 deleted_root[virtual_fat::SECTOR_SIZE];
  memcpy(deleted_root, root, sizeof(deleted_root));
  deleted_root[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), deleted_root));
  assert(virtual_fat::flush_pending());
  assert(!program_store::exists(program_store::ProgramType::MK61, "AAA"));

  u8 root_after[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root_after));
  u16 cluster_b_after = 0;
  for(u8 i = 0; i < 16; i++) {
    const u8* entry = root_after + (u16) i * 32;
    if(entry[0] != 0 && entry[0] != 0xE5 && entry[11] == 0x20 && memcmp(entry, "BBB     M61", 11) == 0) {
      cluster_b_after = read_le16(entry, 26);
    }
  }
  assert(cluster_b_after == cluster_b_before);

  // Data must still be readable from the same clusters.
  u8 readback[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(data_lba() + (cluster_b_after - 2), readback));
  assert(readback[0] == 0xBB);
}

// A fragmented file: the host writes its FAT chain, and the device must
// assemble the data in chain order rather than assuming contiguity.
static void test_fragmented_file_follows_host_fat_chain(void) {
  reset_virtual_fat_state();

  // Chain: 5 -> 9 -> 3, 1100 bytes (3 sectors).
  u8 fat[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(fat_lba(), fat));
  auto set_fat12 = [&fat](u16 cluster, u16 value) {
    const u16 offset = (u16) (cluster + cluster / 2);
    if((cluster & 1) == 0) {
      fat[offset] = (u8) (value & 0xFF);
      fat[offset + 1] = (u8) ((fat[offset + 1] & 0xF0) | ((value >> 8) & 0x0F));
    } else {
      fat[offset] = (u8) ((fat[offset] & 0x0F) | ((value << 4) & 0xF0));
      fat[offset + 1] = (u8) (value >> 4);
    }
  };
  set_fat12(5, 9);
  set_fat12(9, 3);
  set_fat12(3, 0xFFF);
  assert(virtual_fat::write_sector(fat_lba(), fat));

  u8 part1[virtual_fat::SECTOR_SIZE];
  u8 part2[virtual_fat::SECTOR_SIZE];
  u8 part3[virtual_fat::SECTOR_SIZE];
  memset(part1, 0x51, sizeof(part1));
  memset(part2, 0x52, sizeof(part2));
  memset(part3, 0x53, sizeof(part3));
  assert(virtual_fat::write_sector(data_lba() + (5 - 2), part1));
  assert(virtual_fat::write_sector(data_lba() + (9 - 2), part2));
  assert(virtual_fat::write_sector(data_lba() + (3 - 2), part3));

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));
  fill_short_dir_entry(root + 32, "FRAG    M61", 5, 1100);
  assert(virtual_fat::write_sector(root_lba(), root));
  assert(virtual_fat::flush_pending());

  u8 stored[1100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "FRAG", stored, sizeof(stored), &stored_len));
  assert(stored_len == 1100);
  assert(stored[0] == 0x51);
  assert(stored[511] == 0x51);
  assert(stored[512] == 0x52);
  assert(stored[1023] == 0x52);
  assert(stored[1024] == 0x53);
  assert(stored[1099] == 0x53);
}

// Directory echo with stale (shifted) indexes must not spawn ghost files or
// delete the wrong entry.
static void test_stale_echo_after_flush_does_not_create_ghosts(void) {
  reset_virtual_fat_state();

  u8 data_a[100];
  memset(data_a, 0xA1, sizeof(data_a));
  u8 data_b[100];
  memset(data_b, 0xB1, sizeof(data_b));
  assert(program_store::write(program_store::ProgramType::MK61, "AAA", data_a, sizeof(data_a)));
  assert(program_store::write(program_store::ProgramType::MK61, "BBB", data_b, sizeof(data_b)));
  virtual_fat::reset_session();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  // Delete AAA and flush (macOS sends SYNCHRONIZE CACHE mid-session).
  u8 deleted_root[virtual_fat::SECTOR_SIZE];
  memcpy(deleted_root, root, sizeof(deleted_root));
  deleted_root[32] = 0xE5;
  assert(virtual_fat::write_sector(root_lba(), deleted_root));
  assert(virtual_fat::flush_pending());

  // Host later rewrites the same sector from its stale cache.
  assert(virtual_fat::write_sector(root_lba(), deleted_root));
  assert(virtual_fat::flush_pending());

  assert(!program_store::exists(program_store::ProgramType::MK61, "AAA"));
  u8 stored[100];
  u16 stored_len = 0;
  assert(program_store::read(program_store::ProgramType::MK61, "BBB", stored, sizeof(stored), &stored_len));
  assert(stored_len == sizeof(stored));
  assert(stored[0] == 0xB1);
}

// Deleting a file must never remove a different file that happens to sit at
// the same directory index after layout changes.
static void test_tombstone_identity_check_protects_other_files(void) {
  reset_virtual_fat_state();

  u8 data_a[100];
  memset(data_a, 0xA2, sizeof(data_a));
  u8 data_b[200];
  memset(data_b, 0xB2, sizeof(data_b));
  assert(program_store::write(program_store::ProgramType::MK61, "AAA", data_a, sizeof(data_a)));
  assert(program_store::write(program_store::ProgramType::MK61, "BBB", data_b, sizeof(data_b)));
  virtual_fat::reset_session();

  u8 root[virtual_fat::SECTOR_SIZE];
  assert(virtual_fat::read_sector(root_lba(), root));

  // Tombstone at AAA's slot but carrying BBB's identity (stale cache after
  // the host saw a different layout): must delete BBB, not AAA.
  u8 fake_root[virtual_fat::SECTOR_SIZE];
  memcpy(fake_root, root, sizeof(fake_root));
  memcpy(fake_root + 32, root + 64, 32);
  fake_root[32] = 0xE5;
  memset(fake_root + 64, 0, 32);
  assert(virtual_fat::write_sector(root_lba(), fake_root));
  assert(virtual_fat::flush_pending());

  assert(program_store::exists(program_store::ProgramType::MK61, "AAA"));
  assert(!program_store::exists(program_store::ProgramType::MK61, "BBB"));
}

} // namespace

int main(void) {
  test_lfn_aliases_are_unique();
  test_incomplete_pending_flush_keeps_waiting_for_data();
  test_short_txt_import_stores_text_type();
  test_m61_lfn_import_normalizes_cyrillic_name();
  test_state_txt_lfn_import_normalizes_cyrillic();
  test_staging_does_not_shadow_committed_file_data();
  test_staged_cluster_is_not_advertised_as_free();
  test_staging_survives_mass_copy_before_directory_update();
  test_many_pending_directory_entries_wait_for_late_data();
  test_hidden_stored_entries_do_not_shift_visible_files();
  test_appledouble_entry_does_not_relocate_visible_file();
  test_ignored_directory_does_not_relocate_visible_file();
  test_recreated_generated_entry_cancels_pending_delete();
  test_rewrite_after_delete_cancels_pending_delete();
  test_ignored_range_data_can_be_reclassified();
  test_stale_directory_entries_do_not_cancel_deletes();
  test_mass_delete_queues_whole_directory_sector();
  test_delete_then_reuse_clusters_keeps_delete_and_new_file();
  test_delete_does_not_shift_other_files_clusters();
  test_fragmented_file_follows_host_fat_chain();
  test_stale_echo_after_flush_does_not_create_ghosts();
  test_tombstone_identity_check_protects_other_files();
  printf("virtual_fat_self_test: ok\n");
  return 0;
}
