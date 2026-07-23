#include "loadable_module_system_app.hpp"

namespace loadable_module {
namespace {

static char ascii_upper(char value) {
  return value >= 'a' && value <= 'z'
      ? (char) (value - 'a' + 'A') : value;
}

static bool stem_matches(const char* name, const char* full_name) {
  if(name == nullptr || full_name == nullptr) return false;
  while(*name != 0 && *full_name != 0 && *full_name != '.') {
    if(ascii_upper(*name) != ascii_upper(*full_name)) return false;
    name++;
    full_name++;
  }
  return *name == 0 && *full_name == '.';
}

} // namespace

bool find_system_app(Kind kind, program_store::Entry& output) {
  output = {};
  const char* canonical = file_name(kind);
  if(canonical == nullptr) return false;

  u16 system_directory = program_store::INVALID_ID;
  const int root_count = program_store::child_count(program_store::ROOT_ID);
  for(int index = 0; index < root_count; index++) {
    program_store::Entry entry = {};
    if(!program_store::child(program_store::ROOT_ID, index, entry)) {
      return false;
    }
    if(entry.kind == program_store::NodeKind::DIRECTORY &&
       system_directory_name_matches(entry.name)) {
      system_directory = entry.id;
      break;
    }
  }
  if(system_directory == program_store::INVALID_ID) return false;

  const int count = program_store::child_count(system_directory);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry = {};
    if(!program_store::child(system_directory, index, entry)) return false;
    if(entry.kind == program_store::NodeKind::FILE &&
       entry.type == program_store::ProgramType::APP &&
       stem_matches(entry.name, canonical)) {
      output = entry;
      return true;
    }
  }
  return false;
}

} // namespace loadable_module
