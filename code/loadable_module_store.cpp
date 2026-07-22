#include "loadable_module_store.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static constexpr usize COPY_BUFFER_SIZE = 128;

static bool storage_valid(const Storage& storage) {
  return storage.read != nullptr && storage.program != nullptr &&
         storage.erase_sector != nullptr;
}

static u8 slot_sectors(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return storage_geometry::FOCAL_MODULE_SECTORS;
    case Kind::TINYBASIC: return storage_geometry::TINYBASIC_MODULE_SECTORS;
    case Kind::WBMP_VIEWER: return storage_geometry::WBMP_MODULE_SECTORS;
  }
  return 0;
}

static u8 slot_mask(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return storage_geometry::MODULE_FOCAL;
    case Kind::TINYBASIC: return storage_geometry::MODULE_TINYBASIC;
    case Kind::WBMP_VIEWER: return storage_geometry::MODULE_WBMP_VIEWER;
  }
  return 0;
}

static u8 first_slot_sector(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return 0;
    case Kind::TINYBASIC: return storage_geometry::FOCAL_MODULE_SECTORS;
    case Kind::WBMP_VIEWER:
      return storage_geometry::FOCAL_MODULE_SECTORS +
             storage_geometry::TINYBASIC_MODULE_SECTORS;
  }
  return 0;
}

static StoreStatus read_slot_header(const Storage& storage, const Slot& slot,
                                    Kind kind, Header& output) {
  u8 encoded[HEADER_SIZE];
  if(!storage.read(storage.context, slot.address, encoded, sizeof(encoded))) {
    return StoreStatus::IO_ERROR;
  }
  return decode_header(encoded, slot.size, kind, output) == HeaderStatus::OK
      ? StoreStatus::OK : StoreStatus::INVALID_HEADER;
}

static bool crc_storage(const Storage& storage, u32 address, u32 size,
                        u32& output) {
  u8 buffer[COPY_BUFFER_SIZE];
  u32 state = crc32_begin();
  while(size != 0) {
    const usize count = size < sizeof(buffer) ? (usize) size : sizeof(buffer);
    if(!storage.read(storage.context, address, buffer, count)) return false;
    state = crc32_extend(state, buffer, count);
    address += count;
    size -= (u32) count;
  }
  output = crc32_finish(state);
  return true;
}

static StoreStatus validate_slot_source(const ModuleSource& source,
                                        const Slot& slot, Kind kind,
                                        Header& output) {
  if(source.read == nullptr || source.size < HEADER_SIZE) {
    return StoreStatus::WRONG_FILE_SIZE;
  }
  u8 encoded[HEADER_SIZE];
  if(!source.read(source.context, 0, encoded, sizeof(encoded))) {
    return StoreStatus::IO_ERROR;
  }
  if(decode_header(encoded, slot.size, kind, output) != HeaderStatus::OK) {
    return StoreStatus::INVALID_HEADER;
  }
  if(source.size != HEADER_SIZE + output.stored_size) {
    return StoreStatus::WRONG_FILE_SIZE;
  }
  u8 buffer[COPY_BUFFER_SIZE];
  u32 state = crc32_begin();
  u32 position = 0;
  while(position < output.stored_size) {
    const u32 remaining = output.stored_size - position;
    const usize count = remaining < sizeof(buffer)
        ? (usize) remaining : sizeof(buffer);
    if(!source.read(source.context, HEADER_SIZE + position, buffer, count)) {
      return StoreStatus::IO_ERROR;
    }
    state = crc32_extend(state, buffer, count);
    position += (u32) count;
  }
  return crc32_finish(state) == output.stored_crc32
      ? StoreStatus::OK : StoreStatus::BAD_STORED_CRC;
}

} // namespace

bool find_slot(const storage_geometry::Geometry& geometry, Kind kind,
               Slot& output) {
  memset(&output, 0, sizeof(output));
  if(geometry.module_first_sector == 0 || !valid_kind(kind) ||
     (geometry.module_mask & slot_mask(kind)) == 0) return false;
  const u8 sectors = slot_sectors(kind);
  const u8 first = first_slot_sector(kind);
  if(sectors == 0 ||
     (u16) first + sectors > storage_geometry::MODULE_SECTORS) return false;
  const u32 first_sector = geometry.module_first_sector + first;
  const u32 end_sector = first_sector + sectors;
  if(end_sector > geometry.settings_sector ||
     end_sector > geometry.physical_sectors) return false;
  output.address = first_sector * storage_geometry::PHYSICAL_SECTOR_SIZE;
  output.size = (u32) sectors * storage_geometry::PHYSICAL_SECTOR_SIZE;
  return true;
}

StoreStatus validate_source(const storage_geometry::Geometry& geometry,
                            Kind kind, const ModuleSource& source,
                            Header& output) {
  memset(&output, 0, sizeof(output));
  Slot slot;
  if(!find_slot(geometry, kind, slot)) return StoreStatus::UNAVAILABLE;
  return validate_slot_source(source, slot, kind, output);
}

StoreStatus read_header(const Storage& storage,
                        const storage_geometry::Geometry& geometry,
                        Kind kind, Header& output) {
  memset(&output, 0, sizeof(output));
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot)) {
    return StoreStatus::UNAVAILABLE;
  }
  return read_slot_header(storage, slot, kind, output);
}

StoreStatus inspect(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, Header& output) {
  memset(&output, 0, sizeof(output));
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot)) {
    return StoreStatus::UNAVAILABLE;
  }
  const StoreStatus header_status = read_slot_header(storage, slot, kind, output);
  if(header_status != StoreStatus::OK) return header_status;
  u32 checksum = 0;
  if(!crc_storage(storage, slot.address + HEADER_SIZE, output.stored_size,
                  checksum)) return StoreStatus::IO_ERROR;
  return checksum == output.stored_crc32
      ? StoreStatus::OK : StoreStatus::BAD_STORED_CRC;
}

StoreStatus install(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, const ModuleSource& source,
                    Header* installed) {
  if(installed != nullptr) memset(installed, 0, sizeof(*installed));
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot)) {
    return StoreStatus::UNAVAILABLE;
  }
  Header header = {};
  StoreStatus status = validate_slot_source(source, slot, kind, header);
  if(status != StoreStatus::OK) return status;

  for(u32 offset = 0; offset < slot.size;
      offset += storage_geometry::PHYSICAL_SECTOR_SIZE) {
    if(!storage.erase_sector(storage.context, slot.address + offset)) {
      return StoreStatus::IO_ERROR;
    }
  }

  u8 buffer[COPY_BUFFER_SIZE];
  u32 position = 0;
  while(position < header.stored_size) {
    const u32 remaining = header.stored_size - position;
    const usize count = remaining < sizeof(buffer)
        ? (usize) remaining : sizeof(buffer);
    if(!source.read(source.context, HEADER_SIZE + position, buffer, count) ||
       !storage.program(storage.context,
                        slot.address + HEADER_SIZE + position,
                        buffer, count)) return StoreStatus::IO_ERROR;
    position += (u32) count;
  }

  u32 checksum = 0;
  if(!crc_storage(storage, slot.address + HEADER_SIZE, header.stored_size,
                  checksum)) return StoreStatus::IO_ERROR;
  if(checksum != header.stored_crc32) return StoreStatus::VERIFY_FAILED;

  u8 encoded[HEADER_SIZE];
  if(!source.read(source.context, 0, encoded, sizeof(encoded)) ||
     !storage.program(storage.context, slot.address, encoded,
                      sizeof(encoded))) return StoreStatus::IO_ERROR;

  Header verified = {};
  status = inspect(storage, geometry, kind, verified);
  if(status != StoreStatus::OK) return StoreStatus::VERIFY_FAILED;
  if(installed != nullptr) *installed = verified;
  return StoreStatus::OK;
}

StoreStatus remove(const Storage& storage,
                   const storage_geometry::Geometry& geometry,
                   Kind kind) {
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot)) {
    return StoreStatus::UNAVAILABLE;
  }
  return storage.erase_sector(storage.context, slot.address)
      ? StoreStatus::OK : StoreStatus::IO_ERROR;
}

bool read_payload(const Storage& storage,
                  const storage_geometry::Geometry& geometry,
                  Kind kind, u32 offset, u8* output, usize size) {
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot) ||
     output == nullptr || offset > slot.size - HEADER_SIZE ||
     size > slot.size - HEADER_SIZE - offset) return false;
  return storage.read(storage.context, slot.address + HEADER_SIZE + offset,
                      output, size);
}

bool read_container(const Storage& storage,
                    const storage_geometry::Geometry& geometry,
                    Kind kind, u32 offset, u8* output, usize size) {
  Slot slot;
  if(!storage_valid(storage) || !find_slot(geometry, kind, slot) ||
     output == nullptr || offset > slot.size || size > slot.size - offset) {
    return false;
  }
  return storage.read(storage.context, slot.address + offset, output, size);
}

} // namespace loadable_module
