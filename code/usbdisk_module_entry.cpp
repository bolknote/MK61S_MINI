#if defined(MK61_BUILD_USBDISK_MODULE)

#include "loadable_module_abi.hpp"
#include "virtual_fat.hpp"

#include <string.h>

extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  if(!portable_system::bind(api, image_crc, kind)) return 1;
  const u32 capabilities = portable_system::call(MK61_SERVICE_CAPABILITIES);
  return (capabilities & MK61_SERVICE_CAP_USBDISK) != 0 ? 0 : 1;
}

extern "C" u32 mk61_app_command(u32 raw_command, u32 a, u32 b, u32 c, u32) {
  using loadable_module::Command;
  switch((Command) raw_command) {
    case Command::USBDISK_SECTOR_COUNT:
      return virtual_fat::sector_count();
    case Command::USBDISK_SET_EXTERNAL_CACHE:
      return virtual_fat::set_external_cache((u8*) (usize) a, b);
    case Command::USBDISK_RESET_SESSION:
      return virtual_fat::reset_session();
    case Command::USBDISK_END_SESSION:
      virtual_fat::end_session();
      return 1;
    case Command::USBDISK_READ_SECTORS:
      return c <= 0xFFFFU &&
          virtual_fat::read_sectors(a, (u8*) (usize) b, (u16) c);
    case Command::USBDISK_WRITE_CACHED_SECTORS:
      return c <= 0xFFFFU && virtual_fat::write_cached_sectors(
          a, (const u8*) (usize) b, (u16) c);
    case Command::USBDISK_WRITE_SECTORS:
      return c <= 0xFFFFU && virtual_fat::write_sectors(
          a, (const u8*) (usize) b, (u16) c);
    case Command::USBDISK_FLUSH_WRITE_CACHE:
      return virtual_fat::flush_write_cache();
    case Command::USBDISK_FLUSH_PENDING:
      return (u32) virtual_fat::flush_pending_result();
    case Command::USBDISK_FINALIZE_PENDING:
      return (u32) virtual_fat::finalize_pending_result();
    case Command::USBDISK_DIRTY_CACHE_SECTORS:
      return virtual_fat::dirty_cache_sectors();
    case Command::USBDISK_WRITE_CACHE_CAPACITY:
      return virtual_fat::write_cache_capacity();
    case Command::USBDISK_DIAGNOSTIC:
      if(a == 0 || b < sizeof(virtual_fat::Diagnostic)) return 0;
      memcpy((void*) (usize) a, &virtual_fat::diagnostic(),
             sizeof(virtual_fat::Diagnostic));
      return 1;
    case Command::USBDISK_CLEAR_DIAGNOSTIC:
      virtual_fat::clear_diagnostic();
      return 1;
    case Command::USBDISK_RESTORE_DIAGNOSTIC:
      if(a == 0 || b != sizeof(virtual_fat::Diagnostic)) return 0;
      virtual_fat::restore_diagnostic(
          *(const virtual_fat::Diagnostic*) (usize) a);
      return 1;
    default:
      return 0;
  }
}

#endif
