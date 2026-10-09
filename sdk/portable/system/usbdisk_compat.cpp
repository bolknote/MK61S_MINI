#if defined(MK61_BUILD_USBDISK_MODULE)

#include "system_compat.hpp"

#include "device_identity.hpp"
#include "loadable_module_runtime.hpp"

#include <string.h>

namespace {

// Preparing MSC runs synchronously while CDC is deliberately kept alive. A
// corrupt journal must not monopolize that foreground forever: after
// this bound every following resident primitive fails and the normal unwind
// releases the stage lock and returns an actionable diagnostic to CDC.
static constexpr u32 STARTUP_RECOVERY_BUDGET_MS = 4000U;
static bool startup_recovery_active;
static bool startup_recovery_expired;
static u32 startup_recovery_started_ms;
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

static void import_geometry(const mk61_system_usbdisk_geometry& source,
                            storage_geometry::Geometry& output) {
  // Every member is assigned below; the sole caller's static object already
  // has zero-initialized padding.
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

namespace program_store {

u32 catalog_revision() { return call(MK61_SYS_USBDISK, MK61_USBDISK_CATALOG_REVISION); }
u32 media_revision() {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_MEDIA_REVISION);
}

bool ready() {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_C9_READY) == 9U;
}

const storage_geometry::Geometry& geometry() {
  static storage_geometry::Geometry value = {};
  static bool loaded = false;
  if(loaded) return value;
  // Used only while populating the persistent native geometry. A bounded
  // 76-byte wire frame avoids retaining a second geometry for the whole MSC
  // session; the ARM stack qualification covers this cold path.
  mk61_system_usbdisk_geometry wire = {};
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

bool node_id_available(u16 id) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_NODE_AVAILABLE, id) != 0;
}
u8 format_version() { return ready() ? 9U : 0U; }
u16 max_fat_clusters() {
  const auto& value = geometry();
  const u32 overhead = 1U + 2U * value.fat_sectors + value.root_sectors;
  return value.sectors_per_cluster != 0 && value.logical_sectors >= overhead
      ? (u16) ((value.logical_sectors - overhead) / value.sectors_per_cluster) : 0;
}
static bool read_chain_fact(u32 operation, u16 id, u16 index, u16& value) {
  mk61_system_usbdisk_extent request = {};
  const bool ok = call(MK61_SYS_USBDISK, operation, id, index, &request) != 0;
  value = (u16) request.id;
  return ok;
}
bool fat_first_cluster(u16 id, u16& cluster) {
  return read_chain_fact(MK61_USBDISK_FAT_FIRST_CLUSTER, id, 0, cluster);
}
bool fat_chain_count(u16 id, u16& count) {
  return read_chain_fact(MK61_USBDISK_FAT_CHAIN_COUNT, id, 0, count);
}
bool fat_chain_cluster(u16 id, u16 index, u16& cluster) {
  return read_chain_fact(MK61_USBDISK_FAT_CHAIN_CLUSTER, id, index, cluster);
}
FatClusterStatus fat_cluster_info(u16 cluster, FatClusterInfo& output) {
  mk61_system_usbdisk_extent request = {};
  const u32 status = call(MK61_SYS_USBDISK, MK61_USBDISK_FAT_CLUSTER_INFO, cluster, 0, &request);
  output = {(u16) request.owner, (u16) request.cluster_index, (u16) request.next};
  return !startup_recovery_expired && status <= 2
      ? (FatClusterStatus) status : FatClusterStatus::ERROR;
}
bool fat_projection_begin() { return call(MK61_SYS_USBDISK, MK61_USBDISK_FAT_PROJECTION_BEGIN) != 0; }
bool import_plan_begin() { return call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_PLAN_BEGIN) != 0; }
void import_plan_end() { (void) call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_PLAN_END); }
bool import_plan_put(u16 cluster, u16 empty_index, u16 target, u16 source) {
  mk61_system_usbdisk_extent request = {};
  request.id = cluster; request.owner = target;
  request.cluster_index = empty_index; request.next = source;
  return call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_PLAN_PUT, 0, 0, &request) != 0;
}
bool import_plan_get(u16 cluster, u16 empty_index, u16& target, u16& source) {
  mk61_system_usbdisk_extent request = {};
  request.id = cluster; request.owner = request.next = INVALID_ID;
  request.cluster_index = empty_index;
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_PLAN_GET, 0, 0, &request) != 0;
  target = (u16) request.owner; source = (u16) request.next;
  return ok;
}
bool prepare_import_mapping(u16 id) { return call(MK61_SYS_USBDISK, MK61_USBDISK_PREPARE_IMPORT_MAPPING, id) != 0; }
bool import_name_get(u16 slot, u16& hash, u32& location) {
  mk61_system_usbdisk_extent request = {};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_NAME_GET, slot, 0, &request) != 0;
  hash = (u16) request.owner; location = request.next;
  return ok;
}
bool import_name_put(u16 slot, u16 hash, u32 location) {
  mk61_system_usbdisk_extent request = {};
  request.owner = hash; request.next = location;
  return call(MK61_SYS_USBDISK, MK61_USBDISK_IMPORT_NAME_PUT, slot, 0, &request) != 0;
}
bool fat_find_child(u16 parent, bool directory, ProgramType type, const char* name, u16& output) {
  mk61_system_usbdisk_name request = {(u32) type, parent, directory ? 1U : 0U, INVALID_ID, name};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_FAT_FIND_CHILD, 0, 0, &request) != 0;
  output = (u16) request.out_id;
  return ok;
}
bool create_directory_from_fat(u16 parent, const char* name, u16 preferred, u16 first, u16* output) {
  mk61_system_usbdisk_name request = {first, parent, preferred, INVALID_ID, name};
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_CREATE_DIRECTORY_FROM_FAT, 0, 0, &request) != 0;
  if(output != nullptr) *output = (u16) request.out_id;
  return ok;
}
bool set_directory_chain(u16 id, u16 count, const FileSource& source) {
  SourceBridge bridge = {&source};
  mk61_system_usbdisk_source request = {};
  request.preferred = id; request.size = count;
  request.context = &bridge; request.read = read_source;
  return call(MK61_SYS_USBDISK, MK61_USBDISK_SET_DIRECTORY_CHAIN, 0, 0, &request) != 0;
}
bool ensure_directory_chain(u16 id) { return call(MK61_SYS_USBDISK, MK61_USBDISK_ENSURE_DIRECTORY_CHAIN, id) != 0; }

bool vfat_stage_write(u32 block, const u8* data) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_WRITE, block, 0, (void*) data) != 0;
}

bool exported_size_id(u16 id, u32& size) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_EXPORTED_SIZE,
              id, 0, &size) != 0;
}

static int consume_file_byte(void* context, u8 value) {
  const auto& sink = *(const FileSink*) context;
  return sink.next(sink.context, value);
}

bool stream_file_id(u16 id, const FileSink& sink) {
  if(sink.next == nullptr) return false;
  mk61_service_usbdisk_sink request = {
      (void*) &sink, consume_file_byte};
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STREAM_FILE,
               id, 0, &request) != 0;
}
bool vfat_stage_read(u32 block, u8* data) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_READ,
              block, 0, data) != 0;
}
bool vfat_stage_exists(u32 block) {
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_EXISTS, block) != 0;
}
u16 vfat_stage_count() { return (u16) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_COUNT); }
void vfat_stage_forget(u32 start, u16 count) {
  if(count != 0) (void) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_FORGET, start, count);
}
bool vfat_stage_discard_all() { return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_DISCARD_ALL) != 0; }
void vfat_stage_clear() { (void) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_CLEAR); }
bool vfat_stage_lock() { return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_LOCK) != 0; }
bool vfat_stage_discard_unmatched(VfatStageKeyFilter include, void* context) {
  FilterBridge bridge = {include, context};
  mk61_system_usbdisk_stage_filter request = {&bridge, include_key, nullptr, 0};
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_DISCARD_UNMATCHED, 0, 0, &request) != 0;
}

bool vfat_stage_narrow_matching(VfatStageKeyFilter include, void* context,
                                u32* storage, u16 capacity) {
  FilterBridge bridge = {include, context};
  mk61_system_usbdisk_stage_filter request = {
      &bridge, include_key, storage, capacity};
  return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_NARROW_MATCHING,
              0, 0, &request) != 0;
}
bool vfat_stage_restore_full() { return call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_RESTORE_FULL) != 0; }
void vfat_stage_unlock() {
  (void) call(MK61_SYS_USBDISK, MK61_USBDISK_STAGE_UNLOCK);
  startup_recovery_active = false;
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
  const bool ok = call(MK61_SYS_USBDISK, MK61_USBDISK_C9_WRITE_FILE_SOURCE,
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
