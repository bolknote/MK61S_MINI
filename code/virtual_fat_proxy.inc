#include "device_identity.hpp"
#include "loadable_module_runtime.hpp"
#include "program_store.hpp"
#if defined(ARDUINO_ARCH_STM32)
  #include "usb_mass_storage.hpp"
#endif

#include <string.h>

namespace virtual_fat {
namespace {

static u8* external_cache;
static usize external_cache_size;
static u32 cached_sector_count;
static Diagnostic retained_diagnostic;

static void proxy_startup_stage(u32 stage) {
#if defined(ARDUINO_ARCH_STM32)
  usb_mass_storage::note_startup_stage(stage);
#else
  (void) stage;
#endif
}

static const char* pin_failure_subject(loadable_module::RuntimeStatus status) {
  using loadable_module::RuntimeStatus;
  switch(status) {
    case RuntimeStatus::DISABLED: return "app-disabled";
    case RuntimeStatus::UNAVAILABLE: return "app-storage";
    case RuntimeStatus::INVALID_MODULE: return "app-invalid";
    case RuntimeStatus::INCOMPATIBLE_FIRMWARE: return "app-mismatch";
    case RuntimeStatus::CORRUPT_MODULE: return "app-corrupt";
    case RuntimeStatus::BUSY: return "app-busy";
    case RuntimeStatus::IO_ERROR: return "app-io";
    case RuntimeStatus::OK: break;
  }
  return "app-pin";
}

static bool invoke(loadable_module::Command command, u32 a, u32 b, u32 c,
                   u32& result) {
  return loadable_module::pinned(loadable_module::Kind::USBDISK) &&
      loadable_module::invoke(loadable_module::Kind::USBDISK, command,
                              a, b, c, 0, result) ==
          loadable_module::RuntimeStatus::OK;
}

static bool invoke(loadable_module::Command command, u32& result) {
  return invoke(command, 0, 0, 0, result);
}

static void capture_diagnostic(void) {
  u32 result = 0;
  Diagnostic value = {};
  if(invoke(loadable_module::Command::USBDISK_DIAGNOSTIC,
            (u32) (uintptr_t) &value, sizeof(value), 0, result) && result != 0) {
    retained_diagnostic = value;
  }
}

static CommitResult commit_result(loadable_module::Command command) {
  u32 result = (u32) CommitResult::IO_FAILED;
  if(!invoke(command, result) || result > (u32) CommitResult::IO_FAILED) {
    return CommitResult::IO_FAILED;
  }
  capture_diagnostic();
  return (CommitResult) result;
}

} // namespace

u32 sector_count(void) { return cached_sector_count; }

u32 volume_serial(void) {
  const u32 capacity = program_store::ready()
      ? program_store::geometry().capacity_bytes : 0;
  const u32 stable = device_identity::fat_volume_serial(
      device_identity::read(), 0xC6000000UL ^ capacity);
  return stable ^ program_store::media_revision();
}

bool read_sector(u32 lba, u8* output) {
  return read_sectors(lba, output, 1);
}

bool read_sectors(u32 lba, u8* output, u16 count) {
  if(output == nullptr && count != 0) return false;
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_READ_SECTORS,
                lba, (u32) (uintptr_t) output, count, result) && result != 0;
}

bool set_external_cache(u8* data, usize size) {
  if(loadable_module::pinned(loadable_module::Kind::USBDISK)) return false;
  if(data == nullptr) {
    external_cache = nullptr;
    external_cache_size = 0;
    return true;
  }
  if(size < SECTOR_SIZE || size > UINT32_MAX) return false;
  external_cache = data;
  external_cache_size = size;
  return true;
}

u8 write_cache_capacity(void) {
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_WRITE_CACHE_CAPACITY,
                result) ? (u8) result : 0;
}

u8 dirty_cache_sectors(void) {
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_DIRTY_CACHE_SECTORS,
                result) ? (u8) result : 0;
}

bool try_write_cached_sectors(u32, const u8*, u16) {
  // Called by the MSC callback, which may run in interrupt context. APP code
  // is never entered here; the existing BOT deferred path handles the packet.
  return false;
}

bool write_cached_sectors(u32 lba, const u8* data, u16 count) {
  if(data == nullptr && count != 0) return false;
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_WRITE_CACHED_SECTORS,
                lba, (u32) (uintptr_t) data, count, result) && result != 0;
}

bool flush_write_cache(void) {
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_FLUSH_WRITE_CACHE,
                result) && result != 0;
}

bool write_sector(u32 lba, const u8* data) {
  return write_sectors(lba, data, 1);
}

bool write_sectors(u32 lba, const u8* data, u16 count) {
  if(data == nullptr && count != 0) return false;
  u32 result = 0;
  return invoke(loadable_module::Command::USBDISK_WRITE_SECTORS,
                lba, (u32) (uintptr_t) data, count, result) && result != 0;
}

CommitResult flush_pending_result(void) {
  return commit_result(loadable_module::Command::USBDISK_FLUSH_PENDING);
}
bool flush_pending(void) { return flush_pending_result() == CommitResult::OK; }

CommitResult finalize_pending_result(void) {
  return commit_result(loadable_module::Command::USBDISK_FINALIZE_PENDING);
}
bool finalize_pending(void) {
  return finalize_pending_result() == CommitResult::OK;
}

bool reset_session(void) {
  using namespace loadable_module;
  proxy_startup_stage(600U);
  const RuntimeStatus pin_status = pin(Kind::USBDISK);
  proxy_startup_stage(601U);
  if(pin_status != RuntimeStatus::OK) {
    report_startup_failure((u32) pin_status,
                           pin_failure_subject(pin_status));
    return false;
  }
  u32 result = 0;
  u32 failed_stage = 0;
  const char* failed_subject = nullptr;
  proxy_startup_stage(602U);
  if(!invoke(Command::USBDISK_SET_EXTERNAL_CACHE,
             (u32) (uintptr_t) external_cache,
             (u32) external_cache_size, 0, result) || result == 0) {
    failed_stage = 2;
    failed_subject = "app-cache";
  } else if(!invoke(Command::USBDISK_RESTORE_DIAGNOSTIC,
                    (u32) (uintptr_t) &retained_diagnostic,
                    sizeof(retained_diagnostic), 0, result) || result == 0) {
    failed_stage = 3;
    failed_subject = "app-restore";
  } else if(!invoke(Command::USBDISK_RESET_SESSION, result) || result == 0) {
    failed_stage = 4;
    failed_subject = "app-reset";
    // reset_session() can reject mounting while preserving a retryable
    // journal. Capture its exact APP-side reason before unloading the APP.
    capture_diagnostic();
  } else if(!invoke(Command::USBDISK_SECTOR_COUNT, result) || result == 0) {
    failed_stage = 5;
    failed_subject = "app-sectors";
  }
  proxy_startup_stage(603U);
  if(failed_stage != 0) {
    if(failed_stage != 4 || retained_diagnostic.code == ErrorCode::NONE) {
      report_startup_failure(failed_stage, failed_subject);
    }
    u32 ignored = 0;
    proxy_startup_stage(610U);
    (void) invoke(Command::USBDISK_END_SESSION, ignored);
    proxy_startup_stage(611U);
    (void) unpin(Kind::USBDISK);
    proxy_startup_stage(612U);
    cached_sector_count = 0;
    return false;
  }
  cached_sector_count = result;
  return true;
}

void end_session(void) {
  using namespace loadable_module;
  if(!pinned(Kind::USBDISK)) return;
  capture_diagnostic();
  u32 ignored = 0;
  (void) invoke(Command::USBDISK_END_SESSION, ignored);
  (void) unpin(Kind::USBDISK);
  cached_sector_count = 0;
  external_cache = nullptr;
  external_cache_size = 0;
}

const Diagnostic& diagnostic(void) { return retained_diagnostic; }

void clear_diagnostic(void) {
  retained_diagnostic = {};
  u32 ignored = 0;
  (void) invoke(loadable_module::Command::USBDISK_CLEAR_DIAGNOSTIC, ignored);
}

void report_startup_failure(u32 stage, const char* subject) {
  retained_diagnostic = {};
  retained_diagnostic.code = ErrorCode::STORAGE_UNAVAILABLE;
  retained_diagnostic.phase = Phase::SESSION;
  retained_diagnostic.flags = RETRYABLE;
  retained_diagnostic.actual = stage;
  usize offset = 0;
  if(subject != nullptr) {
    while(subject[offset] != 0 &&
          offset + 1U < sizeof(retained_diagnostic.subject)) {
      retained_diagnostic.subject[offset] = subject[offset];
      ++offset;
    }
  }
  retained_diagnostic.subject[offset] = 0;
}

void restore_diagnostic(const Diagnostic& value) {
  retained_diagnostic = value;
  u32 ignored = 0;
  (void) invoke(loadable_module::Command::USBDISK_RESTORE_DIAGNOSTIC,
                (u32) (uintptr_t) &retained_diagnostic,
                sizeof(retained_diagnostic), 0, ignored);
}

} // namespace virtual_fat
