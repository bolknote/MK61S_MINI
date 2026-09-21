#include "config.h"

#if MK61_ANY_LOADABLE_MODULE
#include "usbdisk_backend.hpp"

#include "device_identity.hpp"
#include "independent_watchdog.hpp"
#include "loadable_module_runtime.hpp"
#include "loadable_system_api.hpp"
#include "program_store.hpp"
#include "usb_mass_storage.hpp"

#include <string.h>

namespace usbdisk_backend {
namespace {

static u16 diagnostic_operation_counts[
    MK61_USBDISK_STAGE_FORGET + 1U];

static void export_file(const program_store::Entry& entry,
                        mk61_system_file& output) {
  output = {};
  output.id = entry.id;
  output.parent = entry.parent_id;
  output.size = entry.data_len;
  output.type = (u8) entry.type;
  output.kind = (u8) entry.kind;
  memcpy(output.name, entry.name, sizeof(output.name));
}

static void export_geometry(const storage_geometry::Geometry& source,
                            mk61_system_usbdisk_geometry& output) {
  usb_mass_storage::note_startup_stage(500U);
  output = {};
  usb_mass_storage::note_startup_stage(501U);
  output.capacity_bytes = source.capacity_bytes;
  output.physical_sectors = source.physical_sectors;
  output.locator_a_sector = source.locator_a_sector;
  output.locator_b_sector = source.locator_b_sector;
  usb_mass_storage::note_startup_stage(502U);
  output.catalog_a_sector = source.catalog_a_sector;
  output.catalog_b_sector = source.catalog_b_sector;
  output.catalog_table_sectors = source.catalog_table_sectors;
  output.catalog_bank_sectors = source.catalog_bank_sectors;
  usb_mass_storage::note_startup_stage(503U);
  output.data_first_sector = source.data_first_sector;
  output.data_sector_count = source.data_sector_count;
  output.stage_first_sector = source.stage_first_sector;
  output.stage_sector_count = source.stage_sector_count;
  usb_mass_storage::note_startup_stage(504U);
  output.settings_sector = source.settings_sector;
  output.max_nodes = source.max_nodes;
  output.sectors_per_cluster = source.sectors_per_cluster;
  output.fat_sectors = source.fat_sectors;
  usb_mass_storage::note_startup_stage(505U);
  output.root_entries = source.root_entries;
  output.root_sectors = source.root_sectors;
  output.logical_sectors = source.logical_sectors;
  usb_mass_storage::note_startup_stage(506U);
}

struct SourceBridge { mk61_system_usbdisk_source* request; };

static bool read_source(void* context, u32 offset, u8* output, usize size) {
  SourceBridge& bridge = *(SourceBridge*) context;
  return bridge.request != nullptr && bridge.request->read != nullptr &&
         size <= UINT32_MAX &&
         bridge.request->read(bridge.request->context, offset, output,
                              (u32) size) != 0;
}

struct FilterBridge { mk61_system_usbdisk_stage_filter* request; };

static bool include_stage_key(void* context, u32 key) {
  FilterBridge& bridge = *(FilterBridge*) context;
  return bridge.request != nullptr && bridge.request->include != nullptr &&
         bridge.request->include(bridge.request->context, key) != 0;
}

struct ValidationSource { mk61_system_usbdisk_app_validation* request; };

static bool read_validation(void* context, u32 offset,
                            u8* output, usize size) {
  ValidationSource& source = *(ValidationSource*) context;
  return source.request != nullptr && source.request->read != nullptr &&
         size <= UINT32_MAX &&
         source.request->read(source.request->context, offset, output,
                              (u32) size) != 0;
}

// USBDISK.APP itself occupies the executable arena. Verify the complete
// container/header/ABI and stored-stream CRC here; the ordinary loader still
// verifies decompression, relocation and image CRC before imported code runs.
static loadable_module::StoreStatus validate_stored_app(
    mk61_system_usbdisk_app_validation& request) {
  using namespace loadable_module;
  if(request.read == nullptr || request.size < HEADER_SIZE ||
     request.size > MAX_CONTAINER_SIZE) return StoreStatus::WRONG_FILE_SIZE;
  ValidationSource source = {&request};
  u8 encoded[HEADER_SIZE];
  if(!read_validation(&source, 0, encoded, sizeof(encoded))) {
    return StoreStatus::IO_ERROR;
  }
  Header header = {};
  if(decode_header(encoded, MAX_CONTAINER_SIZE, header) != HeaderStatus::OK) {
    return StoreStatus::INVALID_HEADER;
  }
  if(request.size != HEADER_SIZE + header.stored_size) {
    return StoreStatus::WRONG_FILE_SIZE;
  }
  u32 state = crc32_begin();
  u8 buffer[64];
  u32 offset = 0;
  while(offset < header.stored_size) {
    const u32 remaining = header.stored_size - offset;
    const usize size = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    if(!read_validation(&source, HEADER_SIZE + offset, buffer, size)) {
      return StoreStatus::IO_ERROR;
    }
    state = crc32_extend(state, buffer, size);
    offset += (u32) size;
  }
  return crc32_finish(state) == header.stored_crc32
      ? StoreStatus::OK : StoreStatus::BAD_STORED_CRC;
}

} // namespace

u32 call(u32 operation, u32 a, u32 b, u32 c, void* payload) {
  if(operation == MK61_USBDISK_STARTUP_STAGE) {
    usb_mass_storage::note_startup_stage(300U + a);
    return 1;
  }
  // Temporary qualification telemetry: distinguish one blocked primitive
  // from a hot path that repeatedly crosses the APP/resident boundary. READY
  // is the first primitive in a fresh USBDISK session and resets the counters.
  if(operation == MK61_USBDISK_READY) {
    memset(diagnostic_operation_counts, 0,
           sizeof(diagnostic_operation_counts));
  }
  const u32 count = operation <= MK61_USBDISK_STAGE_FORGET
      ? ++diagnostic_operation_counts[operation] : 0;
  // Unlock is cleanup after either success or failure.  Recording it as the
  // last operation used to erase the only evidence of the primitive that
  // actually failed during startup recovery.
  if(operation != MK61_USBDISK_STAGE_UNLOCK) {
    usb_mass_storage::note_startup_stage(
        100000U + operation * 1000U + (count < 1000U ? count : 999U));
  }
  (void) c;
  switch(operation) {
    case MK61_USBDISK_READY:
      return program_store::ready();
    case MK61_USBDISK_GEOMETRY:
      if(payload == nullptr || !program_store::ready()) return 0;
      export_geometry(program_store::geometry(),
                      *(mk61_system_usbdisk_geometry*) payload);
      return 1;
    case MK61_USBDISK_MAX_NODES:
      return program_store::max_nodes();
    case MK61_USBDISK_CHILD_COUNT:
      return a <= 0xFFFFU ? (u32) program_store::child_count((u16) a) : 0;
    case MK61_USBDISK_CHILD: {
      if(payload == nullptr || a > 0xFFFFU || b > INT32_MAX) return 0;
      program_store::Entry entry = {};
      if(!program_store::child((u16) a, (int) b, entry)) return 0;
      export_file(entry, *(mk61_system_file*) payload);
      return 1;
    }
    case MK61_USBDISK_CREATE_DIRECTORY: {
      if(payload == nullptr) return 0;
      auto& request = *(mk61_system_usbdisk_name*) payload;
      if(request.parent > 0xFFFFU || request.preferred > 0xFFFFU) return 0;
      u16 id = program_store::INVALID_ID;
      const bool ok = program_store::create_directory(
          (u16) request.parent, request.name, (u16) request.preferred, &id);
      request.out_id = id;
      return ok;
    }
    case MK61_USBDISK_MOVE_RENAME: {
      if(payload == nullptr) return 0;
      const auto& request = *(mk61_system_usbdisk_name*) payload;
      return request.id <= 0xFFFFU && request.parent <= 0xFFFFU &&
          program_store::move_rename((u16) request.id,
                                     (u16) request.parent, request.name);
    }
    case MK61_USBDISK_ALLOCATE_DIRECTORY_EXTENT:
      return a <= 0xFFFFU && b <= 0xFFFFU &&
          program_store::allocate_directory_extent((u16) a, (u16) b);
    case MK61_USBDISK_RELEASE_DIRECTORY_EXTENT:
      return a <= 0xFFFFU &&
          program_store::release_directory_extent((u16) a);
    case MK61_USBDISK_FIRST_DIRECTORY_EXTENT:
    case MK61_USBDISK_NEXT_DIRECTORY_EXTENT:
    case MK61_USBDISK_FIRST_FILE_EXTENT:
    case MK61_USBDISK_NEXT_FILE_EXTENT: {
      if(payload == nullptr || a > 0xFFFFU) return 0;
      u16 id = program_store::INVALID_ID;
      bool ok = false;
      if(operation == MK61_USBDISK_FIRST_DIRECTORY_EXTENT)
        ok = program_store::first_extent((u16) a, id);
      else if(operation == MK61_USBDISK_NEXT_DIRECTORY_EXTENT)
        ok = program_store::next_extent((u16) a, id);
      else if(operation == MK61_USBDISK_FIRST_FILE_EXTENT)
        ok = program_store::first_file_extent((u16) a, id);
      else
        ok = program_store::next_file_extent((u16) a, id);
      ((mk61_system_usbdisk_extent*) payload)->id = id;
      return ok;
    }
    case MK61_USBDISK_DIRECTORY_EXTENT_INFO:
    case MK61_USBDISK_FILE_EXTENT_INFO: {
      if(payload == nullptr || a > 0xFFFFU) return 0;
      auto& output = *(mk61_system_usbdisk_extent*) payload;
      u16 owner = program_store::INVALID_ID;
      u16 next = program_store::INVALID_ID;
      u8 cluster = 0;
      const bool ok = operation == MK61_USBDISK_DIRECTORY_EXTENT_INFO
          ? program_store::extent_info((u16) a, owner, next)
          : program_store::file_extent_info((u16) a, owner, cluster, next);
      output.owner = owner;
      output.next = next;
      output.cluster_index = cluster;
      return ok;
    }
    case MK61_USBDISK_RELEASE_FILE_EXTENT:
      return a <= 0xFFFFU && program_store::release_file_extent((u16) a);
    case MK61_USBDISK_STAGE_WRITE:
      return payload != nullptr && program_store::vfat_stage_write(
          a, (const u8*) payload);
    case MK61_USBDISK_STAGE_READ:
      return payload != nullptr && program_store::vfat_stage_read(
          a, (u8*) payload);
    case MK61_USBDISK_STAGE_EXISTS:
      return program_store::vfat_stage_exists(a);
    case MK61_USBDISK_STAGE_COUNT:
      return program_store::vfat_stage_count();
    case MK61_USBDISK_STAGE_SNAPSHOT: {
      if(payload == nullptr) return 0;
      auto& request = *(mk61_service_usbdisk_stage_snapshot*) payload;
      if(request.capacity > 0xFFFFU ||
         (request.capacity != 0 && request.keys == nullptr)) return 0;
      u16 count = 0;
      const bool ok = program_store::vfat_stage_snapshot(
          request.keys, (u16) request.capacity, count);
      request.count = count;
      return ok;
    }
    case MK61_USBDISK_TRIM_DIRECTORY_EXTENTS:
      if(a > 0xFFFFU || b > 0xFFFFU) return MK61_USBDISK_TRIM_FAILED;
      return (u32) program_store::trim_directory_extents_step(
          (u16) a, (u16) b);
    case MK61_USBDISK_STAGE_DISCARD_ALL:
      return program_store::vfat_stage_discard_all();
    case MK61_USBDISK_STAGE_FORGET:
      if(a > program_store::VFAT_STAGE_KEY_MAX || b > 0xFFFFU ||
         b > program_store::VFAT_STAGE_KEY_MAX - a + 1U) return 0;
      program_store::vfat_stage_forget(a, (u16) b);
      for(u16 offset = 0; offset < (u16) b; ++offset) {
        if(program_store::vfat_stage_exists(a + offset)) return 0;
      }
      return 1;
    case MK61_USBDISK_STAGE_CLEAR:
      program_store::vfat_stage_clear();
      return 1;
    case MK61_USBDISK_STAGE_LOCK:
      return program_store::vfat_stage_lock();
    case MK61_USBDISK_STAGE_NARROW_MATCHING: {
      if(payload == nullptr) return 0;
      auto& request = *(mk61_system_usbdisk_stage_filter*) payload;
      if(request.index_capacity > 0xFFFFU) return 0;
      FilterBridge bridge = {&request};
      return program_store::vfat_stage_narrow_matching(
          include_stage_key, &bridge, request.index_storage,
          (u16) request.index_capacity);
    }
    case MK61_USBDISK_STAGE_RESTORE_FULL:
      return program_store::vfat_stage_restore_full();
    case MK61_USBDISK_STAGE_UNLOCK:
      program_store::vfat_stage_unlock();
      return 1;
    case MK61_USBDISK_WRITE_FILE_SOURCE: {
      if(payload == nullptr) return 0;
      auto& request = *(mk61_system_usbdisk_source*) payload;
      if(request.parent > 0xFFFFU || request.preferred > 0xFFFFU ||
         request.type > 0xFFU || request.size > 0xFFFFU ||
         request.extent_count > 0xFFU || request.read == nullptr) return 0;
      SourceBridge bridge = {&request};
      const program_store::FileSource source = {&bridge, read_source};
      u16 id = program_store::INVALID_ID;
      const bool ok = program_store::write_file_from_source(
          (u16) request.parent, (u16) request.preferred,
          (program_store::ProgramType) request.type, request.name,
          (u16) request.size, source, request.extents,
          (u8) request.extent_count, &id, request.compression_buffer,
          request.compression_buffer_size, request.contiguous_data);
      if(ok) independent_watchdog::completed_storage_unit();
      request.out_id = ok
          ? (u32) id
          : 0x80000000UL |
              (u32) program_store::last_write_failure() |
              ((u32) program_store::last_write_failure_detail() << 8);
      return ok;
    }
    case MK61_USBDISK_VALIDATE_APP: {
      if(payload == nullptr) return 0;
      auto& request = *(mk61_system_usbdisk_app_validation*) payload;
      request.status = (u32) validate_stored_app(request);
      return 1;
    }
    case MK61_USBDISK_MAX_FILE_SIZE:
      switch((program_store::ProgramType) a) {
        case program_store::ProgramType::TINYBASIC:
          return program_store::MAX_TINYBASIC_TEXT_SIZE;
        case program_store::ProgramType::FONT:
          return program_store::MAX_FONT_SIZE;
        case program_store::ProgramType::IMAGE1:
          return program_store::MAX_IMAGE1_SIZE;
        case program_store::ProgramType::CHIP8:
          return program_store::MAX_CHIP8_SIZE;
        case program_store::ProgramType::APP:
          return program_store::MAX_APP_FILE_SIZE;
        default:
          return program_store::MAX_MK61_TEXT_SIZE;
      }
    case MK61_USBDISK_VOLUME_SERIAL: {
      const u32 capacity = program_store::ready()
          ? program_store::geometry().capacity_bytes : 0;
      return device_identity::fat_volume_serial(
          device_identity::read(), 0xC6000000UL ^ capacity);
    }
    case MK61_USBDISK_MEDIA_REVISION:
      return program_store::media_revision();
    default:
      return 0;
  }
}

} // namespace usbdisk_backend
#endif
