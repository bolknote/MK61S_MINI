#include "explorer_autoexec.hpp"

#include "storage_path.hpp"

namespace explorer_autoexec {

static bool find_direct(u16 directory_id, const char* name,
                        program_store::ProgramType type,
                        program_store::Entry& out) {
  program_store::Entry entry = {};
  if(storage_path::resolve_file(directory_id, name, type, entry) !=
         storage_path::Status::OK ||
     entry.parent_id != directory_id) {
    return false;
  }
  out = entry;
  return true;
}

bool find(u16 directory_id, program_store::Entry& out) {
  if(directory_id != program_store::ROOT_ID) {
    program_store::Entry directory = {};
    if(!program_store::entry_by_id(directory_id, directory) ||
       directory.kind != program_store::NodeKind::DIRECTORY) {
      return false;
    }
  }

  if(find_direct(directory_id, M61_FILE_NAME,
                 program_store::ProgramType::MK61, out)) return true;
  return find_direct(directory_id, TINYBASIC_FILE_NAME,
                     program_store::ProgramType::TINYBASIC, out);
}

} // namespace explorer_autoexec
