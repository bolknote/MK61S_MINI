#ifndef MK61_LOADABLE_MODULE_ABI_HPP
#define MK61_LOADABLE_MODULE_ABI_HPP

#include "rust_types.h"

namespace loadable_module {

// Единственная C ABI-функция каждого образа. Пять 32-битных регистровых
// аргументов не требуют общей структуры данных и сохраняют границу модулей
// независимой от C++ name mangling.
using Entry = u32 (*)(u32 command, u32 argument0, u32 argument1,
                      u32 argument2, u32 argument3);

enum class Command : u32 {
  // Unified ABI 6 startup for every Kind; all text pointers contain M8:
  // argument0 = const mk61_app_api*, argument1 = image CRC,
  // argument2 = Kind, argument3 = 0.
  INITIALIZE = 0,
  APPLICATION_RUN = 1,
  // Универсальный запуск файла зарегистрированного типа:
  // argument0 — тот же mk61_app_api* для любого APP,
  // argument1 — стабильный C6 file id.
  FILE_OPEN = 2,

  FOCAL_LIBRARY_SELECT = 0x100,
  FOCAL_MENU_SELECT,
  FOCAL_COMPILE,
  FOCAL_IS_READY,
  FOCAL_RUN_INDEX,
  FOCAL_RUN_NAME,
  FOCAL_RUN_ID,
  FOCAL_EDIT,
  FOCAL_EDIT_NAME,
  FOCAL_EDIT_ID,

  TINYBASIC_LIBRARY_SELECT = 0x200,
  TINYBASIC_MENU_SELECT,
  TINYBASIC_COMPILE,
  TINYBASIC_IS_READY,
  TINYBASIC_RUN_INDEX,
  TINYBASIC_RUN_NAME,
  TINYBASIC_RUN_ID,
  TINYBASIC_EDIT,
  TINYBASIC_EDIT_NAME,
  TINYBASIC_EDIT_ID,
  // argument0 = stable C6 file id, argument1 = TinyBasicRunMode.
  // Returns TinyBasicRunStatus; appended to preserve older command numbers.
  TINYBASIC_RUN_ID_STATUS,

  WBMP_VIEW = 0x300,
  WBMP_VIEW_ENTRY,

  SETUP_HARDWARE = 0x400,
  SETUP_DATE_TIME, SETUP_CALIBRATION, SETUP_FONT, SETUP_PREVIEW,
  SETUP_FONT_STEP, SETUP_FONT_COMPILE,

  // USBDISK.APP is pinned for the complete MSC session. Pointer-bearing
  // commands are issued only by usb_mass_storage::service(), never an IRQ.
  USBDISK_SECTOR_COUNT = 0x500,
  USBDISK_SET_EXTERNAL_CACHE,
  USBDISK_RESET_SESSION,
  USBDISK_END_SESSION,
  USBDISK_READ_SECTORS,
  USBDISK_WRITE_CACHED_SECTORS,
  USBDISK_WRITE_SECTORS,
  USBDISK_FLUSH_WRITE_CACHE,
  USBDISK_FLUSH_PENDING,
  USBDISK_FINALIZE_PENDING,
  USBDISK_DIRTY_CACHE_SECTORS,
  USBDISK_WRITE_CACHE_CAPACITY,
  USBDISK_DIAGNOSTIC,
  USBDISK_CLEAR_DIAGNOSTIC,
  // argument0 = const virtual_fat::Diagnostic*, argument1 = sizeof(value).
  // Restores the resident-retained report after this APP was evicted.
  USBDISK_RESTORE_DIAGNOSTIC
};

// Общий результат FILE_OPEN позволяет проводнику одинаково показывать ошибки
// встроенных обработчиков, System APP и пользовательских APPLICATION.
enum class FileOpenResult : u32 {
  OK = 0,
  INVALID_FILE,
  UNSUPPORTED_DISPLAY,
  BUSY,
  IO_ERROR,
  RUNTIME_ERROR
};

} // namespace loadable_module

#endif
