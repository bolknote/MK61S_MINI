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

// MKC принимает контейнер несколькими терминальными командами. На это время он
// занимает тот же SRAM-overlay, что и исполняемый модуль; token позволяет
// обнаружить, если между пакетами overlay понадобился другому модулю.
struct TransferBuffer {
  u8* data;
  u32 capacity;
  u32 token;
};

bool begin_transfer(u32 size, TransferBuffer& transfer);
u8* transfer_data(u32 token, u32 size);
StoreStatus finish_transfer(Kind kind, u32 token, u32 size,
                            Header* installed = nullptr);
void cancel_transfer(u32 token);
void discard_transfer_staging(void);

} // namespace loadable_module

#endif
