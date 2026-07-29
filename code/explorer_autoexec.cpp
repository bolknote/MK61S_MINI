#include "explorer_autoexec.hpp"

#include "storage_path.hpp"

namespace explorer_autoexec {

bool find(u16 directory_id, program_store::Entry& out) {
  if(directory_id != program_store::ROOT_ID) {
    program_store::Entry directory = {};
    if(!program_store::entry_by_id(directory_id, directory) ||
       directory.kind != program_store::NodeKind::DIRECTORY) {
      return false;
    }
  }

  program_store::Entry entry = {};
  if(storage_path::resolve_file(
         directory_id, FILE_NAME, program_store::ProgramType::MK61,
         entry) != storage_path::Status::OK ||
     entry.parent_id != directory_id) {
    return false;
  }
  out = entry;
  return true;
}

} // namespace explorer_autoexec
