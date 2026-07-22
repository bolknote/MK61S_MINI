#include "loadable_module_runtime.hpp"

#if MK61_ANY_LOADABLE_MODULE

#include "Arduino.h"
#include "ledcontrol.h"
#include "program_store.hpp"
#include "spi_nor_flash.hpp"
#include "tools.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static constexpr u32 INTERNAL_FLASH_ADDRESS = 0x08000000UL;
static constexpr u32 ERASE_TIMEOUT_MS = 5000;
static constexpr u16 TRANSFER_STAGE_BLOCKS =
    (OVERLAY_SIZE + program_store::VFAT_STAGE_BLOCK_SIZE - 1U) /
    program_store::VFAT_STAGE_BLOCK_SIZE;
static constexpr u32 TRANSFER_STAGE_FIRST_KEY =
    program_store::VFAT_STAGE_KEY_MAX - TRANSFER_STAGE_BLOCKS + 1U;

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
static u8 g_call_depth;
static u32 g_cached_resident_size;
static u32 g_cached_resident_crc;
static u32 g_transfer_sequence;
static u32 g_transfer_token;

extern "C" void mk61_module_keep_imports(void);

static bool flash_read(void*, u32 address, u8* output, usize size) {
  return flash_is_ok && output != nullptr &&
         external_flash().readByteArray(address, output, size);
}

static bool flash_program(void*, u32 address, const u8* data, usize size) {
  return flash_is_ok && data != nullptr &&
         external_flash().writeByteArray(address, (u8*) data, size);
}

static bool flash_erase(void*, u32 address) {
  if(!flash_is_ok) return false;
  const u32 stop_at = millis() + ERASE_TIMEOUT_MS;
  while(!external_flash().eraseSector(address)) {
    led::control();
    if((i32) (millis() - stop_at) >= 0) return false;
  }
  led::control();
  return true;
}

static Storage module_storage(void) {
  const Storage storage = {
    nullptr, flash_read, flash_program, flash_erase
  };
  return storage;
}

static const storage_geometry::Geometry& geometry(void) {
  return program_store::geometry();
}

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

struct PayloadContext {
  Storage storage;
  const storage_geometry::Geometry* geometry;
  Kind kind;
};

struct BufferedModuleSource {
  const u8* data;
  u32 size;
};

struct InstallPayloadSource {
  const ModuleSource* source;
};

struct StagedModuleSource {
  u32 size;
};

static bool read_buffered_module(void* context, u32 offset,
                                 u8* output, usize size) {
  const BufferedModuleSource& source = *(BufferedModuleSource*) context;
  if(output == nullptr || offset > source.size ||
     size > source.size - offset) return false;
  memcpy(output, source.data + offset, size);
  return true;
}

static bool read_install_payload(void* context, u32 offset,
                                 u8* output, usize size) {
  const InstallPayloadSource& payload = *(InstallPayloadSource*) context;
  return payload.source != nullptr && payload.source->read != nullptr &&
         payload.source->read(payload.source->context,
                              HEADER_SIZE + offset, output, size);
}

static void forget_transfer_staging(void) {
  if(program_store::ready()) {
    program_store::vfat_stage_forget(TRANSFER_STAGE_FIRST_KEY,
                                     TRANSFER_STAGE_BLOCKS);
  }
}

static bool stage_transfer_container(u32 size) {
  forget_transfer_staging();
  u8 block[program_store::VFAT_STAGE_BLOCK_SIZE];
  u32 offset = 0;
  u16 index = 0;
  while(offset < size) {
    const u32 remaining = size - offset;
    const usize count = remaining < sizeof(block)
        ? (usize) remaining : sizeof(block);
    memset(block, 0, sizeof(block));
    memcpy(block, mk61_module_overlay + offset, count);
    if(!program_store::vfat_stage_write(TRANSFER_STAGE_FIRST_KEY + index,
                                        block)) {
      forget_transfer_staging();
      return false;
    }
    offset += (u32) count;
    index++;
  }
  return true;
}

static bool read_staged_module(void* context, u32 offset,
                               u8* output, usize size) {
  const StagedModuleSource& source = *(StagedModuleSource*) context;
  if(output == nullptr || offset > source.size || size > source.size - offset) {
    return false;
  }
  u8 block[program_store::VFAT_STAGE_BLOCK_SIZE];
  while(size != 0) {
    const u32 block_index = offset / sizeof(block);
    const usize block_offset = (usize) (offset % sizeof(block));
    const usize available = sizeof(block) - block_offset;
    const usize count = size < available ? size : available;
    if(block_index >= TRANSFER_STAGE_BLOCKS ||
       !program_store::vfat_stage_read(
           TRANSFER_STAGE_FIRST_KEY + block_index, block)) return false;
    memcpy(output, block + block_offset, count);
    output += count;
    offset += (u32) count;
    size -= count;
  }
  return true;
}

static bool read_payload_callback(void* context, u32 offset,
                                  u8* output, usize size) {
  PayloadContext& payload = *(PayloadContext*) context;
  return loadable_module::read_payload(payload.storage, *payload.geometry,
                                       payload.kind, offset, output, size);
}

static bool same_active_image(Kind kind, const Header& header) {
  return g_active_entry != nullptr && g_active_kind == kind &&
         g_active_header.stored_crc32 == header.stored_crc32 &&
         g_active_header.image_crc32 == header.image_crc32 &&
         g_active_header.resident_crc32 == header.resident_crc32;
}

static void invalidate_active(void) {
  g_active_kind = (Kind) 0;
  memset(&g_active_header, 0, sizeof(g_active_header));
  g_active_entry = nullptr;
}

static RuntimeStatus load(Kind kind) {
  mk61_module_keep_imports();
  if(!enabled(kind)) return RuntimeStatus::DISABLED;
  if(!program_store::ready() || !flash_is_ok ||
     geometry().module_first_sector == 0) return RuntimeStatus::UNAVAILABLE;

  const Storage storage = module_storage();
  Header header = {};
  const StoreStatus header_status =
      loadable_module::read_header(storage, geometry(), kind, header);
  if(header_status == StoreStatus::IO_ERROR) return RuntimeStatus::IO_ERROR;
  if(header_status != StoreStatus::OK) return RuntimeStatus::INVALID_MODULE;
  const u32 overlay_address = (u32) (usize) mk61_module_overlay;
  if(header.load_address != overlay_address || !resident_matches(header)) {
    return RuntimeStatus::INCOMPATIBLE_FIRMWARE;
  }
  if(same_active_image(kind, header)) return RuntimeStatus::OK;
  if(g_call_depth != 0) return RuntimeStatus::BUSY;

  g_transfer_token = 0;
  invalidate_active();
  PayloadContext context = {storage, &geometry(), kind};
  const Reader reader = {&context, read_payload_callback};
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
  g_active_entry = (Entry) (usize) (overlay_address + header.entry_offset + 1U);

  g_call_depth++;
  (void) g_active_entry((u32) Command::INITIALIZE, 0, 0, 0, 0);
  g_call_depth--;
  return RuntimeStatus::OK;
}

} // namespace

bool enabled(Kind kind) {
  switch(kind) {
    case Kind::FOCAL: return MK61_FOCAL_IS_LOADABLE != 0;
    case Kind::TINYBASIC: return MK61_TINYBASIC_IS_LOADABLE != 0;
    case Kind::WBMP_VIEWER: return MK61_WBMP_VIEWER_IS_LOADABLE != 0;
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
    case RuntimeStatus::INVALID_MODULE: return "module not installed";
    case RuntimeStatus::INCOMPATIBLE_FIRMWARE: return "module/firmware mismatch";
    case RuntimeStatus::CORRUPT_MODULE: return "corrupt module";
    case RuntimeStatus::BUSY: return "another module is active";
    case RuntimeStatus::IO_ERROR: return "module storage I/O error";
  }
  return "unknown module error";
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

StoreStatus validate_install(Kind kind, const ModuleSource& source,
                             Header& header) {
  if(!enabled(kind) || !program_store::ready()) return StoreStatus::UNAVAILABLE;
  const StoreStatus status = validate_source(geometry(), kind, source, header);
  if(status != StoreStatus::OK) return status;
  return resident_matches(header) ? StoreStatus::OK
                                  : StoreStatus::INCOMPATIBLE_FIRMWARE;
}

StoreStatus install(Kind kind, const ModuleSource& source, Header* installed) {
  if(!enabled(kind) || !program_store::ready()) return StoreStatus::UNAVAILABLE;
  if(g_call_depth != 0) return StoreStatus::IO_ERROR;
  g_transfer_token = 0;
  Header validated = {};
  const StoreStatus validation =
      validate_source(geometry(), kind, source, validated);
  if(validation != StoreStatus::OK) return validation;
  if(!resident_matches(validated)) {
    return StoreStatus::INCOMPATIBLE_FIRMWARE;
  }
  if(source.size > sizeof(mk61_module_overlay)) {
    return StoreStatus::WRONG_FILE_SIZE;
  }

  // До стирания старого слота проверяем не только CRC хранимого потока, но и
  // сам ZX0-поток с CRC готового SRAM-образа. Затем контейнер будет перечитан
  // целиком: распаковка использует overlay как выход и не может одновременно
  // сохранять в нём исходные байты для последующей записи во flash.
  InstallPayloadSource payload_context = {&source};
  const Reader payload_reader = {&payload_context, read_install_payload};
  DecodeResult decoded = {};
  if(!decode_payload(payload_reader, validated.compression,
                     validated.stored_size, mk61_module_overlay,
                     validated.image_size, decoded) ||
     decoded.stored_crc32 != validated.stored_crc32 ||
     decoded.image_crc32 != validated.image_crc32) {
    memset(mk61_module_overlay, 0, sizeof(mk61_module_overlay));
    return StoreStatus::BAD_STORED_CRC;
  }

  // FAT-хост вправе переиспользовать прежнюю цепочку файла и не присылать
  // неизменившиеся 512-байтовые блоки. Поэтому весь уже проверенный контейнер
  // сначала собирается в SRAM, и лишь затем стирается его старый SPI-слот.
  // Ошибка повторного чтения источника тем самым обнаруживается до стирания.
  invalidate_active();
  u32 position = 0;
  while(position < source.size) {
    const u32 remaining = source.size - position;
    const usize count = remaining < 128U ? (usize) remaining : 128U;
    if(!source.read(source.context, position,
                    mk61_module_overlay + position, count)) {
      memset(mk61_module_overlay, 0, sizeof(mk61_module_overlay));
      return StoreStatus::IO_ERROR;
    }
    position += (u32) count;
  }
  BufferedModuleSource buffered = {mk61_module_overlay, source.size};
  const ModuleSource stable = {
    &buffered, source.size, read_buffered_module
  };
  return loadable_module::install(module_storage(), geometry(), kind, stable,
                                  installed);
}

StoreStatus remove(Kind kind) {
  if(!enabled(kind) || !program_store::ready()) return StoreStatus::UNAVAILABLE;
  if(g_call_depth != 0) return StoreStatus::IO_ERROR;
  if(g_active_kind == kind) invalidate_active();
  return loadable_module::remove(module_storage(), geometry(), kind);
}

bool container_size(Kind kind, u32& size) {
  size = 0;
  if(!enabled(kind) || !program_store::ready()) return false;
  Header header = {};
  if(loadable_module::read_header(module_storage(), geometry(), kind, header) !=
     StoreStatus::OK) return false;
  size = HEADER_SIZE + header.stored_size;
  return true;
}

bool read_container(Kind kind, u32 offset, u8* output, usize size) {
  if(!enabled(kind) || !program_store::ready()) return false;
  u32 total = 0;
  return container_size(kind, total) && offset <= total && size <= total - offset &&
         loadable_module::read_container(module_storage(), geometry(), kind,
                                         offset, output, size);
}

bool begin_transfer(u32 size, TransferBuffer& transfer) {
  memset(&transfer, 0, sizeof(transfer));
  if(!program_store::ready() || g_call_depth != 0 ||
     size < HEADER_SIZE || size > sizeof(mk61_module_overlay)) return false;
  forget_transfer_staging();
  invalidate_active();
  g_transfer_sequence++;
  if(g_transfer_sequence == 0) g_transfer_sequence++;
  g_transfer_token = g_transfer_sequence;
  memset(mk61_module_overlay, 0, size);
  transfer.data = mk61_module_overlay;
  transfer.capacity = sizeof(mk61_module_overlay);
  transfer.token = g_transfer_token;
  return true;
}

u8* transfer_data(u32 token, u32 size) {
  return token != 0 && token == g_transfer_token &&
         size <= sizeof(mk61_module_overlay)
      ? mk61_module_overlay : nullptr;
}

StoreStatus finish_transfer(Kind kind, u32 token, u32 size,
                            Header* installed) {
  if(transfer_data(token, size) == nullptr) return StoreStatus::IO_ERROR;
  if(!stage_transfer_container(size)) {
    g_transfer_token = 0;
    return StoreStatus::IO_ERROR;
  }
  g_transfer_token = 0;
  StagedModuleSource context = {size};
  const ModuleSource source = {&context, size, read_staged_module};
  const StoreStatus result = install(kind, source, installed);
  forget_transfer_staging();
  return result;
}

void cancel_transfer(u32 token) {
  if(token != 0 && token == g_transfer_token) g_transfer_token = 0;
}

void discard_transfer_staging(void) {
  g_transfer_token = 0;
  forget_transfer_staging();
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
StoreStatus validate_install(Kind, const ModuleSource&, Header&) {
  return StoreStatus::UNAVAILABLE;
}
StoreStatus install(Kind, const ModuleSource&, Header*) {
  return StoreStatus::UNAVAILABLE;
}
StoreStatus remove(Kind) { return StoreStatus::UNAVAILABLE; }
bool container_size(Kind, u32& size) { size = 0; return false; }
bool read_container(Kind, u32, u8*, usize) { return false; }
bool begin_transfer(u32, TransferBuffer& transfer) {
  transfer = {nullptr, 0, 0};
  return false;
}
u8* transfer_data(u32, u32) { return nullptr; }
StoreStatus finish_transfer(Kind, u32, u32, Header*) {
  return StoreStatus::UNAVAILABLE;
}
void cancel_transfer(u32) {}
void discard_transfer_staging(void) {}

} // namespace loadable_module

#endif
