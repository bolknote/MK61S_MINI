#ifndef MK61_EXPLORER_AUTOEXEC_HPP
#define MK61_EXPLORER_AUTOEXEC_HPP

#include "program_store.hpp"

namespace explorer_autoexec {

static constexpr char M61_FILE_NAME[] = "autoexec.m61";
static constexpr char TINYBASIC_FILE_NAME[] = "autoexec.tbi";
// Compatibility name for callers that only need the historical M61 entry.
static constexpr const char* FILE_NAME = M61_FILE_NAME;

// Finds an auto-start script that belongs directly to the entered directory.
// The established M61 form wins when both names exist; TinyBASIC is the
// fallback. Parent directories are intentionally not searched.
bool find(u16 directory_id, program_store::Entry& out);

} // namespace explorer_autoexec

#endif
