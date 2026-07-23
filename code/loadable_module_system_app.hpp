#ifndef MK61_LOADABLE_MODULE_SYSTEM_APP_HPP
#define MK61_LOADABLE_MODULE_SYSTEM_APP_HPP

#include "loadable_module_format.hpp"
#include "program_store.hpp"

namespace loadable_module {

// Ищет системный APP только под каноническим именем в /System.
// Одноимённый файл в корне или другом каталоге намеренно игнорируется.
bool find_system_app(Kind kind, program_store::Entry& output);

} // namespace loadable_module

#endif
