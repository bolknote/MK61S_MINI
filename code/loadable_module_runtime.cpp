#include "loadable_module_runtime.hpp"

#include "Arduino.h"
#include "loadable_app_api.hpp"
#include "loadable_system_api.hpp"
#include "loadable_module_system_app.hpp"
#include "program_store.hpp"
#include "shared_memory.hpp"
#include "mpu_guard.hpp"
#include "spi_nor_flash.hpp"
#include "tools.hpp"

#include <string.h>

namespace loadable_module {
namespace {

static_assert(program_store::MAX_APP_FILE_SIZE == MAX_CONTAINER_SIZE,
              "C6 and APP container limits must match");

static_assert(shared_memory::APP_MAX_SIZE == APP_MAX_MEMORY_SIZE,
              "allocator and APP format limits differ");

static Kind g_active_kind = (Kind) 0;
static Header g_active_header;
static Entry g_active_entry;
static u16 g_active_file_id = program_store::INVALID_ID;
static u8 g_call_depth;
static u8 g_pin_depth;
static Kind g_pinned_kind = (Kind) 0;
static shared_memory::Lease g_app_cache;

static_assert((u8) Kind::FOCAL == MK61_APP_KIND_FOCAL &&
              (u8) Kind::TINYBASIC == MK61_APP_KIND_TINYBASIC &&
              (u8) Kind::WBMP_VIEWER == MK61_APP_KIND_WBMP_VIEWER &&
              (u8) Kind::APPLICATION == MK61_APP_KIND_APPLICATION &&
              (u8) Kind::CHIP8 == MK61_APP_KIND_CHIP8 &&
              (u8) Kind::MARKDOWN_VIEWER == MK61_APP_KIND_MARKDOWN_VIEWER &&
              (u8) Kind::SETUP == MK61_APP_KIND_SETUP &&
              (u8) Kind::USBDISK == MK61_APP_KIND_USBDISK,
              "public APP kinds must match the container ABI");

static bool resident_matches(const Header& header) {
  // Only the current relocatable ABI can coexist with ordinary globals and
  // the dynamic heap. Reject before acquiring memory or writing any payload.
  return (header.flags & (MK61_PORTABLE_APP_FLAG | MK61_APP_RELOCATABLE_FLAG)) ==
         (MK61_PORTABLE_APP_FLAG | MK61_APP_RELOCATABLE_FLAG);
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
  if(app.container_size < HEADER_SIZE ||
     offset > (u32) app.container_size - (u32) HEADER_SIZE) return false;
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
         left.code_stored_size == right.code_stored_size &&
         left.relocation_count == right.relocation_count &&
         left.stored_crc32 == right.stored_crc32 &&
         left.image_crc32 == right.image_crc32 &&
         left.handled_type_magic == right.handled_type_magic;
}

static bool same_active_image(Kind kind, u16 file_id, const Header& header) {
  return g_app_cache.ok() && g_active_entry != nullptr &&
         g_active_kind == kind &&
         g_active_file_id == file_id &&
         same_header(g_active_header, header);
}

static void clear_active_metadata(void) {
  g_active_kind = (Kind) 0;
  // Header/file id are read only while entry/lease are valid, then replaced.
  g_active_entry = nullptr;
}

static void invalidate_active(void) {
  (void) mpu_guard::set_app_execution(nullptr, 0);
  clear_active_metadata();
  g_app_cache.reset();
}

static shared_memory::EvictionDecision prepare_app_eviction(void) {
  if(g_call_depth != 0 || g_pin_depth != 0) {
    return shared_memory::EvictionDecision::KEEP;
  }
  (void) mpu_guard::set_app_execution(nullptr, 0);
  clear_active_metadata();
  return shared_memory::EvictionDecision::RELEASE;
}

static u8* acquire_app_memory(const Header& header) {
  if(g_app_cache.ok()) return g_app_cache.data();
  if(!g_app_cache.acquire_cache(
       shared_memory::Arena::APP, shared_memory::Owner::LOADABLE_MODULE,
       header.memory_size)) return nullptr;
  if(!g_app_cache.set_evictable(prepare_app_eviction)) {
    g_app_cache.reset();
    return nullptr;
  }
  return g_app_cache.data();
}

static u32 entry_api_argument(void) {
  return (u32) (usize) &loadable_app::resident_api();
}

static bool decode_checked(const Header& header, const Reader& reader, u8* image) {
  return decode_image(header, reader, image, (u32) (usize) image);
}

static RuntimeStatus activate(Kind kind, u16 file_id, const Header& header,
                              const Reader& reader) {
  if(!resident_matches(header)) {
    return RuntimeStatus::INCOMPATIBLE_FIRMWARE;
  }
  // Every APP is an opportunistic cache. Reopening the same inode/header
  // preserves its globals until another arena owner evicts the image.
  if(same_active_image(kind, file_id, header)) return RuntimeStatus::OK;
  if(g_call_depth != 0 || g_pin_depth != 0) return RuntimeStatus::BUSY;

  invalidate_active();
  u8* const image = acquire_app_memory(header);
  if(image == nullptr) return RuntimeStatus::BUSY;
  if(!decode_checked(header, reader, image)) {
    memset(image, 0, g_app_cache.size());
    invalidate_active();
    return RuntimeStatus::CORRUPT_MODULE;
  }
  memset(image + header.image_size, 0,
         header.memory_size - header.image_size);
  if(!mpu_guard::set_app_execution(image,
        shared_memory::capacity(g_app_cache.arena()))) {
    invalidate_active();
    return RuntimeStatus::INVALID_MODULE;
  }
  __DSB();
  __ISB();
  g_active_kind = kind;
  g_active_header = header;
  g_active_file_id = file_id;
  g_active_entry = (Entry) (usize) ((usize) image + header.entry_offset + 1U);

  g_call_depth++;
  const u32 initialized = g_active_entry((u32) Command::INITIALIZE,
                                         entry_api_argument(),
                                         header.image_crc32,
                                         (u32) kind,
                                         0);
  g_call_depth--;
  if(initialized != 0) {
    invalidate_active();
    return RuntimeStatus::INVALID_MODULE;
  }
  return RuntimeStatus::OK;
}

static RuntimeStatus load_entry(Kind kind, const program_store::Entry& app) {
  Header header = {};
  const StoreStatus header_status = read_app_header(app, kind, header);
  if(header_status == StoreStatus::IO_ERROR) return RuntimeStatus::IO_ERROR;
  if(header_status != StoreStatus::OK) return RuntimeStatus::INVALID_MODULE;
  AppPayloadContext context = {app.id, app.data_len};
  const Reader reader = {&context, read_app_payload};
  return activate(kind, app.id, header, reader);
}

// APPLICATION is merely the non-canonical case: System kinds resolve their
// fixed /System name, while APPLICATION supplies the selected C6 inode. From
// this point onward validation, decoding, initialization, API and cache are
// identical.
static RuntimeStatus load(Kind kind,
                          u16 file_id = program_store::INVALID_ID) {
  if(!enabled(kind)) return RuntimeStatus::DISABLED;
  if(!program_store::ready() || !flash_is_ok) {
    return RuntimeStatus::UNAVAILABLE;
  }

  program_store::Entry app = {};
  const bool found = kind == Kind::APPLICATION
      ? file_id != program_store::INVALID_ID &&
        program_store::entry_by_id(file_id, app)
      : find_system_app(kind, app);
  if(!found) {
    return RuntimeStatus::INVALID_MODULE;
  }
  return load_entry(kind, app);
}

} // namespace

bool enabled(Kind kind) {
  switch(kind) {
    case Kind::SETUP: return MK61_SETUP_IS_LOADABLE != 0;
    case Kind::USBDISK: return MK61_USBDISK_IS_LOADABLE != 0;
    case Kind::FOCAL: return MK61_FOCAL_IS_LOADABLE != 0;
    case Kind::TINYBASIC: return MK61_TINYBASIC_IS_LOADABLE != 0;
    case Kind::WBMP_VIEWER: return MK61_WBMP_VIEWER_IS_LOADABLE != 0;
    case Kind::CHIP8: return MK61_CHIP8_IS_LOADABLE != 0;
    case Kind::MARKDOWN_VIEWER:
      return MK61_MARKDOWN_VIEWER_IS_LOADABLE != 0;
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
  // A pinned APP owns its already validated SRAM image until unpin().  In
  // particular, USB-disk writes may replace /System/USBDISK.APP on C6 while
  // that very APP is serving the MSC session. Resolving its file again for
  // each command would reject the still-valid pinned image mid-session.
  const bool active_pinned = g_pin_depth != 0 && g_pinned_kind == kind;
  const RuntimeStatus loaded = active_pinned ? RuntimeStatus::OK : load(kind);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != kind) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_call_depth++;
  // The portable wire protocol carries an inode, never a resident C++ Entry.
  if(command == Command::WBMP_VIEW_ENTRY && argument1 != 0 &&
     (g_active_header.flags & MK61_PORTABLE_APP_FLAG) != 0)
    argument1 = ((const program_store::Entry*) (usize) argument1)->id;
  result = g_active_entry((u32) command, argument0, argument1,
                          argument2, argument3);
  g_call_depth--;
  return RuntimeStatus::OK;
}

RuntimeStatus pin(Kind kind) {
  if(g_pin_depth != 0) {
    if(g_pinned_kind != kind || g_pin_depth == 0xFFU) {
      return RuntimeStatus::BUSY;
    }
    ++g_pin_depth;
    return RuntimeStatus::OK;
  }
  const RuntimeStatus loaded = load(kind);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != kind) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_pinned_kind = kind;
  g_pin_depth = 1;
  return RuntimeStatus::OK;
}

bool unpin(Kind kind) {
  if(g_pin_depth == 0 || g_pinned_kind != kind) return false;
  if(--g_pin_depth == 0) g_pinned_kind = (Kind) 0;
  return true;
}

bool pinned(Kind kind) {
  return g_pin_depth != 0 && g_pinned_kind == kind;
}

RuntimeStatus run_app(u16 file_id, u32& result) {
  result = 0;
  const RuntimeStatus loaded = load(Kind::APPLICATION, file_id);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != Kind::APPLICATION) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_call_depth++;
  result = g_active_entry((u32) Command::APPLICATION_RUN,
                          entry_api_argument(), 0, 0, 0);
  g_call_depth--;
  return RuntimeStatus::OK;
}

bool find_file_handler(u16 type_magic, FileHandler& handler) {
  handler = {(Kind) 0, program_store::INVALID_ID, 0};
  if(type_magic == 0 || !program_store::ready() || !flash_is_ok) return false;

  // Канонические System APP имеют приоритет: их включение контролируется
  // конфигурацией прошивки и не зависит от порядка пользовательских файлов.
  for(u8 index = 0; index < KIND_COUNT; index++) {
    const Kind kind = kind_at(index);
    if(!enabled(kind)) continue;
    program_store::Entry app = {};
    Header header = {};
    if(find_system_app(kind, app) &&
       read_app_header(app, kind, header) == StoreStatus::OK &&
       (header.handled_type_magic == type_magic ||
        (kind == Kind::MARKDOWN_VIEWER &&
         MK61_MARKDOWN_USES_WBMP &&
         header.handled_type_magic ==
             program_store::TYPE_MAGIC_MARKDOWN &&
         type_magic == program_store::TYPE_MAGIC_IMAGE1))) {
      handler = {kind, app.id, type_magic};
      return true;
    }
  }

  const int count = program_store::count(program_store::ProgramType::APP);
  bool found = false;
  for(int index = 0; index < count; index++) {
    program_store::Entry app = {};
    Header header = {};
    if(!program_store::entry(program_store::ProgramType::APP, index, app) ||
       read_app_header(app, Kind::APPLICATION, header) != StoreStatus::OK ||
       header.handled_type_magic != type_magic) continue;
    // Два пользовательских APPLICATION с одним magic — неоднозначная
    // регистрация. Порядок inode и имя файла не выбирают победителя.
    if(found) {
      handler = {(Kind) 0, program_store::INVALID_ID, 0};
      return false;
    }
    handler = {Kind::APPLICATION, app.id, type_magic};
    found = true;
  }
  return found;
}

RuntimeStatus open_file(const FileHandler& handler, u16 file_id, u32& result) {
  result = 0;
  RuntimeStatus loaded = RuntimeStatus::INVALID_MODULE;
  loaded = load(handler.kind, handler.module_file_id);
  if(loaded != RuntimeStatus::OK) return loaded;
  if(g_active_entry == nullptr || g_active_kind != handler.kind) {
    return RuntimeStatus::INVALID_MODULE;
  }
  g_call_depth++;
  result = g_active_entry(
      (u32) Command::FILE_OPEN,
      entry_api_argument(),
      file_id, 0, 0);
  g_call_depth--;
  return RuntimeStatus::OK;
}

StoreStatus validate_app(const ModuleSource& source, Header& header) {
  memset(&header, 0, sizeof(header));
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
  if(!resident_matches(header)) {
    return StoreStatus::INCOMPATIBLE_FIRMWARE;
  }

  invalidate_active();
  u8* const image = acquire_app_memory(header);
  if(image == nullptr) return StoreStatus::UNAVAILABLE;
  InstallPayloadSource payload_context = {&source};
  const Reader payload_reader = {&payload_context, read_install_payload};
  if(!decode_checked(header, payload_reader, image)) {
    memset(image, 0, g_app_cache.size());
    invalidate_active();
    return StoreStatus::BAD_STORED_CRC;
  }
  invalidate_active();
  return StoreStatus::OK;
}

} // namespace loadable_module
