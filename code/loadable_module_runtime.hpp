#ifndef MK61_LOADABLE_MODULE_RUNTIME_HPP
#define MK61_LOADABLE_MODULE_RUNTIME_HPP

#include "config.h"
#include "loadable_module_abi.hpp"
#include "loadable_module_store.hpp"

namespace loadable_module {

enum class RuntimeStatus : u8 {
  OK = 0,
  DISABLED,
  UNAVAILABLE,
  INVALID_MODULE,
  INCOMPATIBLE_FIRMWARE,
  CORRUPT_MODULE,
  BUSY,
  IO_ERROR
};

bool enabled(Kind kind);
RuntimeStatus status(Kind kind);
const char* status_text(RuntimeStatus status);

RuntimeStatus invoke(Kind kind, Command command,
                     u32 argument0, u32 argument1,
                     u32 argument2, u32 argument3,
                     u32& result);

inline RuntimeStatus invoke(Kind kind, Command command, u32& result) {
  return invoke(kind, command, 0, 0, 0, 0, result);
}

StoreStatus validate_install(Kind kind, const ModuleSource& source,
                             Header& header);
StoreStatus install(Kind kind, const ModuleSource& source,
                    Header* installed = nullptr);
StoreStatus remove(Kind kind);

// Представление установленного контейнера для синтетических файлов USB FAT.
bool container_size(Kind kind, u32& size);
bool read_container(Kind kind, u32 offset, u8* output, usize size);

} // namespace loadable_module

#endif
