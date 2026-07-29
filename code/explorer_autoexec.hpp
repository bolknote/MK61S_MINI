#ifndef MK61_EXPLORER_AUTOEXEC_HPP
#define MK61_EXPLORER_AUTOEXEC_HPP

#include "program_store.hpp"

namespace explorer_autoexec {

static constexpr char FILE_NAME[] = "autoexec.m61";

// Finds the M61 auto-start script that belongs directly to the entered
// directory. Parent directories are intentionally not searched.
bool find(u16 directory_id, program_store::Entry& out);

} // namespace explorer_autoexec

#endif
