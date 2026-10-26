#ifndef MK61_FILE_HANDLERS_HPP
#define MK61_FILE_HANDLERS_HPP

#include "loadable_module_abi.hpp"
#include "program_store.hpp"

namespace file_handlers {

bool available(const program_store::Entry& entry);
loadable_module::FileOpenResult open(const program_store::Entry& entry);

} // namespace file_handlers

#endif
