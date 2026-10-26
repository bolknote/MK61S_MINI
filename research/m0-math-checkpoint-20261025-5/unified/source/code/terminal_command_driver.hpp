#ifndef MK61_TERMINAL_COMMAND_DRIVER_HPP
#define MK61_TERMINAL_COMMAND_DRIVER_HPP
#include "rust_types.h"
#include <stddef.h>
namespace led { struct PatternStep; }
struct SoundNote;
namespace crash_dump_format {
struct Record;
}
namespace mpu_guard {
struct Snapshot;
}
namespace independent_watchdog {
struct Snapshot;
}
namespace rtc_clock {
struct DateTime;
struct StartupSnapshot;
struct BackupStatus;
} // namespace rtc_clock
namespace rtc_backup_layout {
enum class AlarmId : u8;
struct Alarm;
} // namespace rtc_backup_layout
namespace storage_path {
enum class Status : u8;
struct FileTarget;
} // namespace storage_path
namespace program_store {
enum class ProgramType : u8;
}
namespace power_monitor {
struct Snapshot;
struct ThresholdRange;
} // namespace power_monitor
namespace resident_firmware {
struct Result;
struct Failure;
} // namespace resident_firmware
namespace virtual_fat {
struct Diagnostic;
}
namespace usb_mass_storage {
struct StartupDiagnostic;
}

namespace entropy_pool {
enum class Domain : u8;
}
namespace terminal_command_driver {
// Synchronous resident/APP ABI: all pointers refer to the resident invocation or the
// currently loaded APP. No callback or APP pointer survives its return.
static constexpr u32 VERSION = 3, EXECUTE = 0x54434D44;
enum class Operation : u32 {
  WRITE_BYTES,
  NUMBER,
  CORE_INFO,
  CORE_PAGE,
  CORE_READ,
  CORE_WRITE,
  CORE_APPLY,
  CORE_INSERT,
  REGISTER_TEXT,
  STACK_TEXT,
  CHIP_TEXT,
  RING_BYTE,
  RING_CHIP,
  ERROR_REACTION,
  CRASH_COPY,
  CRASH_CLEAR,
  CRASH_FLAGS,
  CRASH_METADATA,
  CRASH_PERSIST,
  PATH_TARGET,
  PATH_STATUS,
  MPU_SNAPSHOT,
  MPU_BACKEND,
  WATCHDOG_SNAPSHOT,
  WATCHDOG_RUNNING,
  RTC_SNAPSHOT,
  RTC_SET,
  RTC_ALARM_READ,
  RTC_ALARM_SET,
  RTC_ALARM_AFTER,
  RTC_ALARM_CANCEL,
  RTC_BACKUP,
  STORAGE_INFO,
  NOR_SNAPSHOT,
  POWER_SNAPSHOT,
  POWER_THRESHOLD,
  FIRMWARE_VERIFY,
  FIRMWARE_FAILURE,
  FIRMWARE_BUILD,
  VFAT_DIAGNOSTIC,
  VFAT_CLEAR,
  MSC_DIAGNOSTIC,
  MSC_CLEAR
};
struct Services;
struct History;
struct Request {
  u32 size, version;
  const Services *services;
  const char *arguments;
  u32 command, directory;
  i32 assembly_address;
  const History *history;
};
struct CoreInfo {
  u32 steps, limit, bank, instruction, expanded, ring_size, ring_chips;
};
struct StorageInfo {
  u32 ready, mount_status, capacity, used, maximum, files, directories,
      cluster_bytes, settings_bytes, required_crc;
};
struct FlashSnapshot {
  u32 jedec_id, capacity_bytes, probe_upper_bytes, requested_clock_hz,
      peripheral_clock_hz, actual_clock_hz;
  u16 page_size, prescaler;
  u8 status[3], status_count, erase_opcode;
  bool sfdp_present, four_byte_address, four_byte_opcodes;
};
struct CrashMetadata {
  u32 build;
  char public_id[17];
  const char *profile;
};
struct RingChip {
  const char *name;
  u32 offset;
};
struct PathTarget {
  const char *path;
  void *output;
};
struct History {
  u32 capacity, depth;
  const u8 *head;
  const u8 *count;
  const char *text;
  const u16 *start;
  const u8 *length;
};
struct Services {
  u32 size, version;
  bool (*output)(u32, const u8 *, usize);
  void (*number)(u32, u32);
  CoreInfo (*core_info)();
  void (*core_page)(u8 *);
  bool (*core_read)(u16, u8 &);
  bool (*core_write)(u16, u8);
  void (*core_apply)(const u8 *, usize, bool, bool);
  void (*core_insert)(usize, usize);
  void (*register_text)(int, char *, const char *);
  const char *(*stack_text)(u32, char *, const char *);
  void (*chip_text)(char *);
  const u8 *ring;
  RingChip (*ring_chip)(u32);
  void (*error_reaction)();
  bool (*crash_copy)(crash_dump_format::Record &);
  void (*crash_clear)();
  u32 (*crash_flags)();
  bool (*crash_layout)();
  CrashMetadata (*crash_metadata)();
  bool (*crash_persist)();
  storage_path::Status (*path_target)(u16, const char *,
                                      program_store::ProgramType,
                                      storage_path::FileTarget &);
  const char *(*path_status)(storage_path::Status);
  mpu_guard::Snapshot (*mpu_snapshot)();
  const char *(*mpu_backend)();
  independent_watchdog::Snapshot (*watchdog_snapshot)();
  bool (*watchdog_running)();
  bool (*rtc_snapshot)(rtc_clock::StartupSnapshot &);
  bool (*rtc_set)(const rtc_clock::DateTime &);
  bool (*rtc_alarm_read)(rtc_backup_layout::AlarmId,
                         rtc_backup_layout::Alarm &);
  bool (*rtc_alarm_set)(rtc_backup_layout::AlarmId,
                        const rtc_backup_layout::Alarm &);
  bool (*rtc_alarm_after)(rtc_backup_layout::AlarmId, u32);
  bool (*rtc_alarm_cancel)(rtc_backup_layout::AlarmId);
  bool (*rtc_backup)(rtc_clock::BackupStatus &);
  StorageInfo (*storage_info)();
  bool (*nor_snapshot)(FlashSnapshot &);
  power_monitor::Snapshot (*power_snapshot)();
  power_monitor::ThresholdRange (*power_threshold)();
  resident_firmware::Result (*firmware_verify)();
  bool (*firmware_failure)(resident_firmware::Failure &);
  u32 (*firmware_build)();
  const virtual_fat::Diagnostic &(*vfat_diagnostic)();
  void (*vfat_clear)();
  usb_mass_storage::StartupDiagnostic (*msc_diagnostic)();
  void (*msc_clear)();
  bool (*write_raw)(u8, const u8 *);
  bool (*write_fraction)(u8, u32);
  u32 (*random7)(entropy_pool::Domain);
  const char *(*help_signature)();
  void (*help_fallback)();
  bool (*led_pattern)(const led::PatternStep *, usize);
  bool (*sound_pattern)(const SoundNote *, usize);
};
#if defined(__arm__) || defined(__thumb__)
static_assert(sizeof(Request) == 32 && sizeof(History) == 28,
              "terminal APP request layout changed; bump its ABI version");
#endif
inline bool compatible(const Request *r) {
  return r && r->size == sizeof(*r) && r->version == VERSION && r->arguments &&
         r->services && r->services->size == sizeof(Services) &&
         r->services->version == VERSION;
}
} // namespace terminal_command_driver
#endif
