#if defined(MK61_BUILD_USBDISK_MODULE)

#include "system_compat.hpp"

#include "device_identity.hpp"
#include "loadable_module_runtime.hpp"

#include <string.h>

namespace {

static constexpr u16 STAGE_CACHE_CAPACITY = 384;
// Preparing MSC runs synchronously while CDC is deliberately kept alive. A
// corrupt legacy journal must not monopolize that foreground forever: after
// this bound every following resident primitive fails and the normal unwind
// releases the stage lock and returns an actionable diagnostic to CDC.
static constexpr u32 STARTUP_RECOVERY_BUDGET_MS = 4000U;
static bool startup_recovery_active;
static bool startup_recovery_expired;
static u32 startup_recovery_started_ms;
static u32 stage_keys[STAGE_CACHE_CAPACITY];
static u16 stage_key_count;
static bool stage_keys_valid;
static program_store::WriteFailure last_write_failure_value =
    program_store::WriteFailure::NONE;
static program_store::WriteFailureDetail last_write_failure_detail_value =
    program_store::WriteFailureDetail::NONE;

static u32 call(u32 operation, u32 a = 0, u32 b = 0, u32 c = 0,
                void* data = nullptr) {
  if(startup_recovery_active && operation == MK61_SYS_USBDISK &&
     a != MK61_USBDISK_STARTUP_STAGE && a != MK61_USBDISK_STAGE_UNLOCK &&
     (u32) (millis() - startup_recovery_started_ms) >=
         STARTUP_RECOVERY_BUDGET_MS) {
    if(!startup_recovery_expired) {
      startup_recovery_expired = true;
      // 990 is a retained breadcrumb, not a public diagnostic code.
      (void) portable_system::call(
          MK61_SYS_USBDISK, MK61_USBDISK_STARTUP_STAGE, 690U);
    }
    return 0;
  }
  return portable_system::call(operation, a, b, c, data);
}

static u16 stage_lower_bound(u32 key) {
  u16 first = 0;
  u16 count = stage_key_count;
  while(count != 0) {
    const u16 step = (u16) (count / 2U);
    const u16 middle = (u16) (first + step);
    if(stage_keys[middle] < key) {
      first = (u16) (middle + 1U);
      count = (u16) (count - step - 1U);
    } else {
      count = step;
    }
  }
  return first;
}

static bool stage_cache_contains(u32 key) {
  const u16 index = stage_lower_bound(key);
  return index < stage_key_count && stage_keys[index] == key;
}

static bool stage_cache_add(u32 key) {
  const u16 index = stage_lower_bound(key);
  if(index < stage_key_count && stage_keys[index] == key) return true;
  if(stage_key_count == STAGE_CACHE_CAPACITY) return false;
  memmove(stage_keys + index + 1U, stage_keys + index,
          (usize) (stage_key_count - index) * sizeof(stage_keys[0]));
  stage_keys[index] = key;
  ++stage_key_count;
  return true;
}

static void stage_cache_remove(u32 key) {
  const u16 index = stage_lower_bound(key);
  if(index >= stage_key_count || stage_keys[index] != key) return;
  memmove(stage_keys + index, stage_keys + index + 1U,
          (usize) (stage_key_count - index - 1U) * sizeof(stage_keys[0]));
  --stage_key_count;
}

static bool refresh_stage_cache() {
  mk61_service_usbdisk_stage_snapshot request = {
      stage_keys, STAGE_CACHE_CAPACITY, 0};
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_SNAPSHOT,
           0, 0, &request) || request.count > STAGE_CACHE_CAPACITY) {
    stage_key_count = 0;
    stage_keys_valid = false;
    return false;
  }
  stage_key_count = (u16) request.count;
  // The persistent index is append-ordered. Sort its public keys once so all
  // sector-presence checks in both recovery passes become local binary search.
  for(u16 index = 1; index < stage_key_count; ++index) {
    const u32 key = stage_keys[index];
    u16 position = index;
    while(position != 0 && stage_keys[position - 1U] > key) {
      stage_keys[position] = stage_keys[position - 1U];
      --position;
    }
    stage_keys[position] = key;
  }
  stage_keys_valid = true;
  return true;
}

static void import_file(const mk61_system_file& source,
                        program_store::Entry& output) {
  output = {};
  output.type = (program_store::ProgramType) source.type;
  output.kind = (program_store::NodeKind) source.kind;
  output.id = (u16) source.id;
  output.parent_id = (u16) source.parent;
  output.data_len = (u16) source.size;
  memcpy(output.name, source.name, sizeof(output.name));
}

static void import_geometry(const mk61_system_usbdisk_geometry& source,
                            storage_geometry::Geometry& output) {
  output = {};
  output.capacity_bytes = source.capacity_bytes;
  output.physical_sectors = source.physical_sectors;
  output.locator_a_sector = source.locator_a_sector;
  output.locator_b_sector = source.locator_b_sector;
  output.catalog_a_sector = source.catalog_a_sector;
  output.catalog_b_sector = source.catalog_b_sector;
  output.catalog_table_sectors = source.catalog_table_sectors;
  output.catalog_bank_sectors = source.catalog_bank_sectors;
  output.data_first_sector = source.data_first_sector;
  output.data_sector_count = source.data_sector_count;
  output.stage_first_sector = source.stage_first_sector;
  output.stage_sector_count = source.stage_sector_count;
  output.settings_sector = source.settings_sector;
  output.max_nodes = source.max_nodes;
  output.sectors_per_cluster = source.sectors_per_cluster;
  output.fat_sectors = source.fat_sectors;
  output.root_entries = source.root_entries;
  output.root_sectors = source.root_sectors;
  output.logical_sectors = source.logical_sectors;
}

struct SourceBridge { const program_store::FileSource* source; };

static int read_source(void* context, u32 offset, u8* output, u32 size) {
  const SourceBridge& bridge = *(const SourceBridge*) context;
  return bridge.source != nullptr && bridge.source->read != nullptr &&
      bridge.source->read(bridge.source->context, offset, output, size);
}

struct FilterBridge {
  program_store::VfatStageKeyFilter include;
  void* context;
};

static int include_key(void* context, u32 key) {
  const FilterBridge& bridge = *(const FilterBridge*) context;
  return bridge.include != nullptr && bridge.include(bridge.context, key);
}

struct ValidationBridge { const loadable_module::ModuleSource* source; };

static int read_validation(void* context, u32 offset,
                           u8* output, u32 size) {
  const ValidationBridge& bridge = *(const ValidationBridge*) context;
  return bridge.source != nullptr && bridge.source->read != nullptr &&
      bridge.source->read(bridge.source->context, offset, output, size);
}

} // namespace

extern "C" void mk61_usbdisk_startup_stage(u32 stage) {
  if(stage == 1U) {
    startup_recovery_active = true;
    startup_recovery_expired = false;
    startup_recovery_started_ms = millis();
  }
  (void) portable_system::call(
      MK61_SYS_USBDISK, MK61_USBDISK_STARTUP_STAGE, stage);
  if(stage == 7U) startup_recovery_active = false;
}

extern "C" bool mk61_usbdisk_startup_timed_out(void) {
  return startup_recovery_expired;
}

extern "C" u32 mk61_usbdisk_startup_timeout_elapsed(void) {
  return startup_recovery_expired
      ? (u32) (millis() - startup_recovery_started_ms) : 0U;
}

extern "C" u32 mk61_usbdisk_startup_timeout_limit(void) {
  return STARTUP_RECOVERY_BUDGET_MS;
}

extern "C" void mk61_usbdisk_restart_startup_budget(void) {
  if(!startup_recovery_active) return;
  startup_recovery_started_ms = millis();
  startup_recovery_expired = false;
}

extern "C" u8* mk61_usbdisk_empty_stage_scratch(u32 size) {
  if(!stage_keys_valid || stage_key_count != 0 || size > sizeof(stage_keys)) {
    return nullptr;
  }
  return reinterpret_cast<u8*>(stage_keys);
}

namespace program_store {

u32 media_revision() {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_MEDIA_REVISION);
}

bool ready() {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_READY) != 0;
}

const storage_geometry::Geometry& geometry() {
  static storage_geometry::Geometry value = {};
  static bool loaded = false;
  if(loaded) return value;
  // This service runs synchronously and cannot be re-entered. Keep the large
  // wire object out of the APP call stack: resident code fills it across the
  // ABI boundary while the portable caller is still executing from SRAM.
  static mk61_system_usbdisk_geometry wire = {};
  wire = {};
  const bool available =
      call(MK61_SYS_USBDISK, MK61_USBDISK_GEOMETRY, 0, 0, &wire) != 0;
  mk61_usbdisk_startup_stage(210);
  if(available) {
    import_geometry(wire, value);
    loaded = true;
  } else {
    value = {};
  }
  mk61_usbdisk_startup_stage(211);
  return value;
}

u16 max_nodes() {
  return (u16) call(MK61_SYS_USBDISK, MK61_USBDISK_MAX_NODES);
}

const char* file_extension(ProgramType type) {
  switch(type) {
    case ProgramType::MK61: return "m61";
    case ProgramType::FOCAL: return "foc";
    case ProgramType::TINYBASIC: return "tbi";
    case ProgramType::TEXT: return "txt";
    case ProgramType::MK61_STATE: return "state.txt";
    case ProgramType::FONT: return "fmk";
    case ProgramType::IMAGE1: return "wbmp";
    case ProgramType::APP: return "app";
    case ProgramType::CHIP8: return "ch8";
    case ProgramType::MARKDOWN: return "md";
    case ProgramType::MK61_BINARY: return "bin";
  }
  return "bin";
}

int child_count(u16 parent) {
  return (int) call(MK61_SYS_USBDISK, MK61_USBDISK_CHILD_COUNT, parent);
}

bool child(u16 parent, int index, Entry& output) {
  if(index < 0) return false;
  mk61_system_file wire = {};
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_CHILD, parent,
           (u32) index, &wire)) return false;
  import_file(wire, output);
  return true;
}

bool create_directory(u16 parent, const char* name, u16 preferred, u16* id) {
  mk61_system_usbdisk_name request = {
      0, parent, preferred, INVALID_ID, name};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_CREATE_DIRECTORY,
                       0, 0, &request) != 0;
  if(id != nullptr) *id = (u16) request.out_id;
  return ok;
}

bool move_rename(u16 id, u16 parent, const char* name) {
  mk61_system_usbdisk_name request = {
      id, parent, INVALID_ID, INVALID_ID, name};
  return call(MK61_SYS_USBDISK, MK61_USBDISK_MOVE_RENAME,
              0, 0, &request) != 0;
}

bool allocate_directory_extent(u16 directory, u16 preferred) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_ALLOCATE_DIRECTORY_EXTENT,
              directory, preferred) != 0;
}

bool release_directory_extent(u16 extent) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_RELEASE_DIRECTORY_EXTENT,
              extent) != 0;
}

bool trim_directory_extents(u16 directory, u16 keep_count) {
  const u16 limit = max_nodes();
  for(u16 guard = 0; guard <= limit; ++guard) {
    const u32 result = call(MK61_SYS_USBDISK,
                            MK61_USBDISK_TRIM_DIRECTORY_EXTENTS,
                            directory, keep_count);
    if(result == MK61_USBDISK_TRIM_COMPLETE) return true;
    if(result != MK61_USBDISK_TRIM_MORE) return false;
    // The resident operation deliberately performs only one WAL transaction.
    // Return to the foreground before the next one so the watchdog, power
    // monitor and display continue to make progress during legacy recovery.
    idle_main_process();
  }
  return false;
}

static bool extent_id(u32 operation, u16 source, u16& output) {
  mk61_system_usbdisk_extent value = {};
  const bool ok = call(MK61_SYS_USBDISK, operation, source,
                       0, &value) != 0;
  output = (u16) value.id;
  return ok;
}

bool first_extent(u16 directory, u16& id) {
  return extent_id(MK61_USBDISK_FIRST_DIRECTORY_EXTENT, directory, id);
}
bool next_extent(u16 extent, u16& id) {
  return extent_id(MK61_USBDISK_NEXT_DIRECTORY_EXTENT, extent, id);
}
bool first_file_extent(u16 file, u16& id) {
  return extent_id(MK61_USBDISK_FIRST_FILE_EXTENT, file, id);
}
bool next_file_extent(u16 extent, u16& id) {
  return extent_id(MK61_USBDISK_NEXT_FILE_EXTENT, extent, id);
}

bool extent_info(u16 extent, u16& directory, u16& next) {
  mk61_system_usbdisk_extent value = {};
  const bool ok = call(MK61_SYS_USBDISK,
      MK61_USBDISK_DIRECTORY_EXTENT_INFO, extent, 0, &value) != 0;
  directory = (u16) value.owner;
  next = (u16) value.next;
  return ok;
}

bool file_extent_info(u16 extent, u16& file, u8& cluster, u16& next) {
  mk61_system_usbdisk_extent value = {};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_FILE_EXTENT_INFO,
                       extent, 0, &value) != 0;
  file = (u16) value.owner;
  cluster = (u8) value.cluster_index;
  next = (u16) value.next;
  return ok;
}

bool release_file_extent(u16 extent) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_RELEASE_FILE_EXTENT,
              extent) != 0;
}

bool vfat_stage_write(u32 block, const u8* data) {
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_WRITE,
                       block, 0, (void*) data) != 0;
  if(ok && stage_keys_valid && !stage_cache_add(block)) {
    stage_keys_valid = false;
  }
  return ok;
}
bool vfat_stage_read(u32 block, u8* data) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_READ,
              block, 0, data) != 0;
}
bool vfat_stage_exists(u32 block) {
  if(stage_keys_valid) return stage_cache_contains(block);
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_EXISTS, block) != 0;
}
u16 vfat_stage_count() {
  if(stage_keys_valid) return stage_key_count;
  return (u16) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_COUNT);
}
void vfat_stage_forget(u32 start_block, u16 blocks) {
  if(blocks == 0) return;
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_FORGET,
           start_block, blocks)) {
    stage_keys_valid = false;
    return;
  }
  if(stage_keys_valid) {
    for(u16 offset = 0; offset < blocks; ++offset) {
      stage_cache_remove(start_block + offset);
    }
  }
}
bool vfat_stage_discard_all() {
  const bool ok = call(MK61_SYS_USBDISK,
                       MK61_USBDISK_STAGE_DISCARD_ALL) != 0;
  if(ok) {
    stage_key_count = 0;
    stage_keys_valid = true;
  }
  return ok;
}
void vfat_stage_clear() {
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_CLEAR)) {
    stage_keys_valid = false;
    return;
  }
  (void) refresh_stage_cache();
}
bool vfat_stage_lock() {
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_LOCK)) {
    stage_key_count = 0;
    stage_keys_valid = false;
    return false;
  }
  // The resident lock has already ensured and frozen the authoritative
  // staging index.  Snapshot that index once for APP-side binary searches;
  // asking the resident to rebuild it from Flash again made every USB-disk
  // startup pay for two complete journal scans.
  if(refresh_stage_cache()) return true;
  (void) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_UNLOCK);
  return false;
}
bool vfat_stage_narrow_matching(VfatStageKeyFilter include, void* context,
                                u32* storage, u16 capacity) {
  FilterBridge bridge = {include, context};
  mk61_system_usbdisk_stage_filter request = {
      &bridge, include_key, storage, capacity};
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_NARROW_MATCHING,
              0, 0, &request) != 0;
}
bool vfat_stage_restore_full() {
  const bool ok = call(MK61_SYS_USBDISK,
                       MK61_USBDISK_STAGE_RESTORE_FULL) != 0;
  if(ok) (void) refresh_stage_cache();
  else stage_keys_valid = false;
  return ok;
}
void vfat_stage_unlock() {
  (void) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_UNLOCK);
  startup_recovery_active = false;
  stage_key_count = 0;
  stage_keys_valid = false;
}

bool write_file_from_source(u16 parent, u16 preferred, ProgramType type,
                            const char* name, u16 size,
                            const FileSource& source, const u16* extents,
                            u8 extent_count, u16* id,
                            u8* compression_buffer,
                            usize compression_buffer_size,
                            const u8* contiguous_data) {
  SourceBridge bridge = {&source};
  mk61_system_usbdisk_source request = {
      parent, preferred, (u32) type, size, INVALID_ID, extent_count,
      name, &bridge, read_source, extents, compression_buffer,
      (u32) compression_buffer_size, contiguous_data};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_WRITE_FILE_SOURCE,
                       0, 0, &request) != 0;
  last_write_failure_value = ok
      ? WriteFailure::NONE
      : (request.out_id & 0x80000000UL) != 0
          ? (WriteFailure) (request.out_id & 0xFFU)
          : WriteFailure::COMMIT;
  last_write_failure_detail_value = ok
      ? WriteFailureDetail::NONE
      : (request.out_id & 0x80000000UL) != 0
          ? (WriteFailureDetail) ((request.out_id >> 8) & 0xFFU)
          : WriteFailureDetail::NONE;
  if(id != nullptr) *id = (u16) request.out_id;
  return ok;
}

WriteFailure last_write_failure(void) { return last_write_failure_value; }
WriteFailureDetail last_write_failure_detail(void) {
  return last_write_failure_detail_value;
}

} // namespace program_store

namespace device_identity {
Uid96 read() { return {}; }
u32 fat_volume_serial(const Uid96&, u32 fallback) {
  mk61_usbdisk_startup_stage(212);
  const u32 value = call(MK61_SYS_USBDISK, MK61_USBDISK_VOLUME_SERIAL);
  mk61_usbdisk_startup_stage(213);
  return value != 0 ? value : fallback;
}
} // namespace device_identity

namespace loadable_module {
StoreStatus validate_app(const ModuleSource& source, Header& header) {
  memset(&header, 0, sizeof(header));
  ValidationBridge bridge = {&source};
  mk61_system_usbdisk_app_validation request = {
      &bridge, read_validation, source.size, (u32) StoreStatus::UNAVAILABLE};
  if(!call(MK61_SYS_USBDISK, MK61_USBDISK_VALIDATE_APP,
           0, 0, &request)) return StoreStatus::UNAVAILABLE;
  return (StoreStatus) request.status;
}
} // namespace loadable_module

#endif
