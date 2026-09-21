#include "device_identity.hpp"
#include "loadable_module_runtime.hpp"
#include "program_store.hpp"
#include "virtual_fat.hpp"

#include <assert.h>
#include <vector>

namespace {

static constexpr u32 EVENT_PIN = 0xFFFFFFF0UL;
static constexpr u32 EVENT_UNPIN = 0xFFFFFFF1UL;

static std::vector<u32> events;
static bool module_pinned;
static loadable_module::RuntimeStatus pin_status =
    loadable_module::RuntimeStatus::OK;
static loadable_module::Command failing_command =
    (loadable_module::Command) 0xFFFFFFFFUL;
static virtual_fat::CommitResult commit_result_value =
    virtual_fat::CommitResult::OK;

static void reset_mock(void) {
  events.clear();
  module_pinned = false;
  pin_status = loadable_module::RuntimeStatus::OK;
  failing_command = (loadable_module::Command) 0xFFFFFFFFUL;
  commit_result_value = virtual_fat::CommitResult::OK;
}

static void expect_events(const std::vector<u32>& expected) {
  assert(events == expected);
}

} // namespace

namespace loadable_module {

RuntimeStatus invoke(Kind kind, Command command,
                     u32, u32, u32, u32, u32& result) {
  assert(kind == Kind::USBDISK);
  assert(module_pinned);
  events.push_back((u32) command);
  result = 1;
  if(command == Command::USBDISK_SECTOR_COUNT) result = 321;
  if(command == Command::USBDISK_FLUSH_PENDING ||
     command == Command::USBDISK_FINALIZE_PENDING) {
    result = (u32) commit_result_value;
  }
  if(command == Command::USBDISK_DIAGNOSTIC) result = 0;
  if(command == failing_command) return RuntimeStatus::IO_ERROR;
  return RuntimeStatus::OK;
}

RuntimeStatus pin(Kind kind) {
  assert(kind == Kind::USBDISK);
  events.push_back(EVENT_PIN);
  if(pin_status != RuntimeStatus::OK) return pin_status;
  module_pinned = true;
  return RuntimeStatus::OK;
}

bool unpin(Kind kind) {
  assert(kind == Kind::USBDISK);
  events.push_back(EVENT_UNPIN);
  const bool was_pinned = module_pinned;
  module_pinned = false;
  return was_pinned;
}

bool pinned(Kind kind) {
  return kind == Kind::USBDISK && module_pinned;
}

} // namespace loadable_module

namespace device_identity {

Uid96 read(void) { return {}; }
u32 fat_volume_serial(const Uid96&, u32 fallback) { return fallback; }

} // namespace device_identity

namespace program_store {

bool ready(void) { return false; }
u32 media_revision(void) { return 0x12345678UL; }
const storage_geometry::Geometry& geometry(void) {
  static const storage_geometry::Geometry value = {};
  return value;
}

} // namespace program_store

#include "../code/virtual_fat_proxy.inc"

int main(void) {
  using loadable_module::Command;
  using loadable_module::RuntimeStatus;

  static u8 cache[virtual_fat::SECTOR_SIZE];
  static u8 sector[virtual_fat::SECTOR_SIZE];

  reset_mock();
  assert(virtual_fat::set_external_cache(cache, sizeof(cache)));
  assert(virtual_fat::reset_session());
  assert(module_pinned);
  assert(virtual_fat::sector_count() == 321);
  expect_events({EVENT_PIN,
                 (u32) Command::USBDISK_SET_EXTERNAL_CACHE,
                 (u32) Command::USBDISK_RESTORE_DIAGNOSTIC,
                 (u32) Command::USBDISK_RESET_SESSION,
                 (u32) Command::USBDISK_SECTOR_COUNT});

  // The USB callback may only choose the deferred path. In particular, this
  // operation must not enter the pinned APP from interrupt context.
  const usize before_irq_probe = (usize) events.size();
  assert(!virtual_fat::try_write_cached_sectors(7, sector, 1));
  assert(events.size() == before_irq_probe);
  assert(!virtual_fat::set_external_cache(nullptr, 0));

  assert(virtual_fat::read_sectors(7, sector, 1));
  assert(events.back() == (u32) Command::USBDISK_READ_SECTORS);

  // CommitResult::OK is encoded as zero. The proxy must not confuse the APP
  // command's result with RuntimeStatus::OK or a generic false return value.
  const usize before_flush = (usize) events.size();
  assert(virtual_fat::flush_pending_result() ==
         virtual_fat::CommitResult::OK);
  assert(events[before_flush] == (u32) Command::USBDISK_FLUSH_PENDING);
  assert(events[before_flush + 1] == (u32) Command::USBDISK_DIAGNOSTIC);
  commit_result_value = virtual_fat::CommitResult::REJECTED;
  assert(virtual_fat::finalize_pending_result() ==
         virtual_fat::CommitResult::REJECTED);
  commit_result_value = virtual_fat::CommitResult::IO_FAILED;
  assert(virtual_fat::flush_pending_result() ==
         virtual_fat::CommitResult::IO_FAILED);
  virtual_fat::end_session();
  assert(!module_pinned);
  assert(virtual_fat::sector_count() == 0);
  assert(events[events.size() - 3] == (u32) Command::USBDISK_DIAGNOSTIC);
  assert(events[events.size() - 2] == (u32) Command::USBDISK_END_SESSION);
  assert(events.back() == EVENT_UNPIN);

  // A partially initialized session is closed and unpinned atomically.
  reset_mock();
  failing_command = Command::USBDISK_RESET_SESSION;
  assert(!virtual_fat::reset_session());
  assert(!module_pinned);
  assert(virtual_fat::sector_count() == 0);
  expect_events({EVENT_PIN,
                 (u32) Command::USBDISK_SET_EXTERNAL_CACHE,
                 (u32) Command::USBDISK_RESTORE_DIAGNOSTIC,
                 (u32) Command::USBDISK_RESET_SESSION,
                 (u32) Command::USBDISK_DIAGNOSTIC,
                 (u32) Command::USBDISK_END_SESSION,
                 EVENT_UNPIN});

  // A failed pin cannot issue even the first APP command.
  reset_mock();
  pin_status = RuntimeStatus::BUSY;
  assert(!virtual_fat::reset_session());
  assert(!module_pinned);
  expect_events({EVENT_PIN});
  assert(virtual_fat::diagnostic().code ==
         virtual_fat::ErrorCode::STORAGE_UNAVAILABLE);
  assert(virtual_fat::diagnostic().actual == 1);
  assert(strcmp(virtual_fat::diagnostic().subject, "app-pin") == 0);

  return 0;
}
