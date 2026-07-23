#include "loadable_module_runtime.hpp"

#if MK61_ANY_LOADABLE_MODULE

#include "Arduino.h"
#include "loadable_app_api.hpp"
#include "loadable_module_system_app.hpp"
#include "program_store.hpp"
#include "spi_nor_flash.hpp"
#include "tools.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static_assert(program_store::MAX_APP_FILE_SIZE == MAX_CONTAINER_SIZE,
              "C5 and APP container limits must match");

static constexpr u32 INTERNAL_FLASH_ADDRESS = 0x08000000UL;

// Секция .bss.* подхватывается штатным скриптом STM32 Core и поэтому занимает
// только SRAM, а не внутреннюю Flash. Глобальное имя извлекается упаковщиком из
// resident ELF и служит адресом отдельной линковки модулей.
extern "C" {
__attribute__((used, aligned(8), section(".bss.mk61_module_overlay")))
u8 mk61_module_overlay[OVERLAY_SIZE];

// STM32 linker script кладёт начальные значения .data сразу после основной
// Flash-части образа. Эта тройка даёт точный размер того же непрерывного .bin,
// который получает упаковщик, без доверия полю resident_size из файла модуля.
extern u8 _sidata;
extern u8 _sdata;
extern u8 _edata;
}

static Kind g_active_kind = (Kind) 0;
static Header g_active_header;
static Entry g_active_entry;
static u16 g_active_file_id = program_store::INVALID_ID;
static u8 g_call_depth;
static u32 g_cached_resident_size;
static u32 g_cached_resident_crc;

extern "C" void mk61_module_keep_imports(void);

static u32 resident_image_size(void) {
  const usize data_size = (usize) &_edata - (usize) &_sdata;
  const usize data_load_end = (usize) &_sidata + data_size;
  return data_load_end >= INTERNAL_FLASH_ADDRESS
      ? (u32) (data_load_end - INTERNAL_FLASH_ADDRESS) : 0;
}

static bool resident_matches(const Header& header) {
  const u32 resident_size = resident_image_size();
  if(resident_size == 0 || header.resident_size != resident_size) return false;
  if(resident_size == g_cached_resident_size)
    return header.resident_crc32 == g_cached_resident_crc;
  const u8* resident = (const u8*) INTERNAL_FLASH_ADDRESS;
  g_cached_resident_size = resident_size;
  g_cached_resident_crc = crc32(resident, resident_size);
  return header.resident_crc32 == g_cached_resident_crc;
}

struct AppPayloadContext {
  u16 file_id;
  u16 container_size;
};

struct InstallPayloadSource {
  const ModuleSource* source;
};

static bool read_install_payload(void* context, u32 offset,
                                 u8* output, usize size) {
  const InstallPayloadSource& payload = *(InstallPayloadSource*) context;
  return payload.source != nullptr && payload.source->read != nullptr &&
         payload.source->read(payload.source->context,
                              HEADER_SIZE + offset, output, size);
}

static bool read_app_container(void* context, u32 offset,
                               u8* output, usize size) {
  const AppPayloadContext& app = *(AppPayloadContext*) context;
  if(output == nullptr || offset > app.container_size ||
     size > app.container_size - offset ||
     offset > 0xFFFFU || size > 0xFFFFU) return false;
  u16 copied = 0;
  return program_store::read_range_id(
             app.file_id, (u16) offset, output, (u16) size, &copied) &&
         copied == size;
}

static bool read_app_payload(void* context, u32 offset,
                             u8* output, usize size) {
  AppPayloadContext& app = *(AppPayloadContext*) context;
  if(offset > app.container_size - HEADER_SIZE) return false;
  return read_app_container(&app, HEADER_SIZE + offset, output, size);
}

static StoreStatus read_app_header(const program_store::Entry& entry,
                                   Kind expected_kind, Header& header) {
  memset(&header, 0, sizeof(header));
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::APP ||
     entry.data_len < HEADER_SIZE ||
     entry.data_len > MAX_CONTAINER_SIZE) {
    return StoreStatus::WRONG_FILE_SIZE;
  }
  u8 encoded[HEADER_SIZE];
  u16 copied = 0;
  if(!program_store::read_range_id(entry.id, 0, encoded, sizeof(encoded),
                                   &copied) ||
     copied != sizeof(encoded)) return StoreStatus::IO_ERROR;
  if(decode_header(encoded, MAX_CONTAINER_SIZE, expected_kind, header) !=
     HeaderStatus::OK) return StoreStatus::INVALID_HEADER;
  return entry.data_len == HEADER_SIZE + header.stored_size
      ? StoreStatus::OK : StoreStatus::WRONG_FILE_SIZE;
}

static bool same_header(const Header& left, const Header& right) {
  return left.kind == right.kind &&
         left.compression == right.compression &&
         left.flags == right.flags &&
         left.load_address == right.load_address &&
         left.stored_size == right.stored_size &&
         left.image_size == right.image_size &&
         left.memory_size == right.memory_size &&
         left.entry_offset == right.entry_offset &&
         left.resident_size == right.resident_size &&
         left.resident_crc32 == right.resident_crc32 &&
         left.stored_crc32 == right.stored_crc32 &&
         left.image_crc32 == right.image_crc32;
}

static bool same_active_image(Kind kind, u16 file_id, const Header& header) {
  return g_active_entry != nullptr && g_active_kind == kind &&
         g_active_file_id == file_id &&
         same_header(g_active_header, header);
}

static void invalidate_active(void) {
  g_active_kind = (Kind) 0;
  memset(&g_active_header, 0, sizeof(g_active_header));
  g_active_entry = nullptr;
  g_active_file_id = program_store::INVALID_ID;
}

static u32 entry_api_argument(Kind kind) {
  return kind == Kind::APPLICATION
      ? (u32) (usize) &loadable_app::resident_api() : 0;
}

static RuntimeStatus activate(Kind kind, u16 file_id, const Header& header,
                              const Reader& reader) {
  const u32 overlay_address = (u32) (usize) mk61_module_overlay;
  if(header.load_address != overlay_address || !resident_matches(header)) {
    return RuntimeStatus::INCOMPATIBLE_FIRMWARE;
  }
  if(same_active_image(kind, file_id, header)) return RuntimeStatus::OK;
  if(g_call_depth != 0) return RuntimeStatus::BUSY;

  invalidate_active();
  DecodeResult decoded = {};
  if(!decode_payload(reader, header.compression, header.stored_size,
                     mk61_module_overlay, header.image_size, decoded)) {
    memset(mk61_module_overlay, 0, sizeof(mk61_module_overlay));
    return RuntimeStatus::CORRUPT_MODULE;
  }
  if(decoded.stored_crc32 != header.stored_crc32 ||
     decoded.image_crc32 != header.image_crc32) {
    memset(mk61_module_overlay, 0, sizeof(mk61_module_overlay));
    return RuntimeStatus::CORRUPT_MODULE;
  }
  memset(mk61_module_overlay + header.image_size, 0,
         header.memory_size - header.image_size);
  __DSB();
  __ISB();
  g_active_kind = kind;
  g_active_header = header;
  g_active_file_id = file_id;
  g_active_entry = (Entry) (usize) (overlay_address + header.entry_offset + 1U);

  g_call_depth++;
  (void) g_active_entry((u32) Command::INITIALIZE,
                        entry_api_argument(kind), 0, 0, 0);
  g_call_depth--;
  return RuntimeStatus::OK;
}

static RuntimeStatus load(Kind kind) {
  mk61_module_keep_imports();
  if(!enabled(kind)) return RuntimeStatus::DISABLED;
  if(!program_store::ready() || !flash_is_ok) {
    return RuntimeStatus::UNAVAILABLE;
  }

  program_store::Entry app = {};
  if(find_system_app(kind, app)) {
    Header header = {};
    const StoreStatus header_status = read_app_header(app, kind, header);
    if(header_status == StoreStatus::IO_ERROR) return RuntimeStatus::IO_ERROR;
    if(header_status != StoreStatus::OK) return RuntimeStatus::INVALID_MODULE;
    AppPayloadContext context = {app.id, app.data_len};
    const Reader reader = {&context, read_app_payload};
    return activate(kind, app.id, header, reader);
  }
  return RuntimeStatus::INVALID_MODULE;
}

static RuntimeStatus load_application(u16 file_id) {
  mk61_module_keep_imports();
  if(!enabled(Kind::APPLICATION)) return RuntimeStatus::DISABLED;
  if(!program_store::ready() || !flash_is_ok) {
    return RuntimeStatus::UNAVAILABLE;
  }
  program_store::Entry app = {};
  if(!program_store::entry_by_id(file_id, app)) {
    return RuntimeStatus::INVALID_MODULE;
  }
  Header header = {};
  const StoreStatus header_status =
      read_app_header(app, Kind::APPLICATION, header);
  if(header_status == StoreStatus::IO_ERROR) return RuntimeStatus::IO_ERROR;
  if(header_status != StoreStatus::OK) return RuntimeStatus::INVALID_MODULE;
  AppPayloadContext context = {app.id, app.data_len};
  const Reader reader = {&context, read_app_payload};
  return activate(Kind::APPLICATION, app.id, header, reader);
}

} // namespace

bool enabled(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return MK61_FOCAL_IS_LOADABLE != 0;
    case Kind::TINYBASIC: return MK61_TINYBASIC_IS_LOADABLE != 0;
    case Kind::WBMP_VIEWER: return MK61_WBMP_VIEWER_IS_LOADABLE != 0;
    case Kind::APPLICATION: return MK61_ENABLE_LOADABLE_MODULES != 0;
  }
  return false;
}

RuntimeStatus status(Kind kind) {
  const RuntimeStatus loaded = load(kind);
  return loaded;
}

const char* status_text(RuntimeStatus value) {
  switch(value) {
    case RuntimeStatus::OK: return "ok";
    case RuntimeStatus::DISABLED: return "disabled";
    case RuntimeStatus::UNAVAILABLE: return "storage unavailable";
    case RuntimeStatus::INVALID_MODULE: return "app not installed";
    case RuntimeStatus::INCOMPATIBLE_FIRMWARE: return "app/firmware mismatch";
    case RuntimeStatus::CORRUPT_MODULE: return "corrupt app";
    case RuntimeStatus::BUSY: return "another app is active";
    case RuntimeStatus::IO_ERROR: return "app storage I/O error";
  }
  return "unknown app error";
}

RuntimeStatus invoke(Kind kind, Command command,
                     u32 argument0, u32 argument1,
                     u32 argument2, u32 argument3,
                     u32& result) {
  result = 0;
  const RuntimeStatus loaded = load(kind);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != kind) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_call_depth++;
  result = g_active_entry((u32) command, argument0, argument1,
                          argument2, argument3);
  g_call_depth--;
  return RuntimeStatus::OK;
}

RuntimeStatus run_app(u16 file_id, u32& result) {
  result = 0;
  const RuntimeStatus loaded = load_application(file_id);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != Kind::APPLICATION) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_call_depth++;
  result = g_active_entry((u32) Command::APPLICATION_RUN,
                          entry_api_argument(Kind::APPLICATION), 0, 0, 0);
  g_call_depth--;
  return RuntimeStatus::OK;
}

StoreStatus validate_app(const ModuleSource& source, Header& header) {
  memset(&header, 0, sizeof(header));
  mk61_module_keep_imports();
  if(!program_store::ready() || g_call_depth != 0 ||
     source.read == nullptr || source.size < HEADER_SIZE ||
     source.size > MAX_CONTAINER_SIZE) return StoreStatus::UNAVAILABLE;
  u8 encoded[HEADER_SIZE];
  if(!source.read(source.context, 0, encoded, sizeof(encoded))) {
    return StoreStatus::IO_ERROR;
  }
  if(decode_header(encoded, MAX_CONTAINER_SIZE, header) != HeaderStatus::OK) {
    return StoreStatus::INVALID_HEADER;
  }
  if(source.size != HEADER_SIZE + header.stored_size) {
    return StoreStatus::WRONG_FILE_SIZE;
  }
  const u32 overlay_address = (u32) (usize) mk61_module_overlay;
  if(header.load_address != overlay_address || !resident_matches(header)) {
    return StoreStatus::INCOMPATIBLE_FIRMWARE;
  }

  invalidate_active();
  InstallPayloadSource payload_context = {&source};
  const Reader payload_reader = {&payload_context, read_install_payload};
  DecodeResult decoded = {};
  if(!decode_payload(payload_reader, header.compression, header.stored_size,
                     mk61_module_overlay, header.image_size, decoded) ||
     decoded.stored_crc32 != header.stored_crc32 ||
     decoded.image_crc32 != header.image_crc32) {
    memset(mk61_module_overlay, 0, sizeof(mk61_module_overlay));
    return StoreStatus::BAD_STORED_CRC;
  }
  return StoreStatus::OK;
}

} // namespace loadable_module

#else

namespace loadable_module {

bool enabled(Kind) { return false; }
RuntimeStatus status(Kind) { return RuntimeStatus::DISABLED; }
const char* status_text(RuntimeStatus) { return "disabled"; }
RuntimeStatus invoke(Kind, Command, u32, u32, u32, u32, u32& result) {
  result = 0;
  return RuntimeStatus::DISABLED;
}
RuntimeStatus run_app(u16, u32& result) {
  result = 0;
  return RuntimeStatus::DISABLED;
}
StoreStatus validate_app(const ModuleSource&, Header&) {
  return StoreStatus::UNAVAILABLE;
}

} // namespace loadable_module

#endif
