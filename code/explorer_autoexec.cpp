#include "explorer_autoexec.hpp"

#include "storage_path.hpp"
#include "fat_name.hpp"

#include <string.h>

#if defined(MK61_CORE_STANDALONE)
#include "../ports/picocalc/file_associations.hpp"
#endif

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

bool find_icon(u16 directory_id, program_store::Entry& out) {
  return find_direct(directory_id,"autoexec.wbmp",program_store::ProgramType::IMAGE1,out);
}

bool find_game(u16 directory_id, program_store::Entry& out) {
  using Type = program_store::ProgramType;
  if(find(directory_id, out)) return true;
  program_store::Entry launcher{};
  if(!find_direct(directory_id, "Play.txt", Type::TEXT, launcher)) return false;
  char leaf[program_store::NAME_SIZE + 4 + 2]; // extension and optional CRLF
  u16 length = launcher.data_len;
  u16 read = 0;
  if(!length || length > sizeof(leaf) ||
     !program_store::read_range_id(launcher.id, 0, (u8*)leaf, length, &read) ||
     read != length) return false;
  while(length && (leaf[length-1] == '\n' || leaf[length-1] == '\r')) --length;
  if(length < 5 || length >= program_store::NAME_SIZE + 4 || leaf[0] == '.') return false;
  leaf[length] = 0;
  const char* ext = nullptr;
  for(u16 i = 0; i < length; ++i) {
    if((u8)leaf[i] < 32 || strchr("/\\:\"'", leaf[i])) return false;
    if(leaf[i] == '.') ext = leaf + i;
  }
  if(!ext) return false;
  static constexpr struct { const char* suffix; Type type; } formats[] = {
    {".m61", Type::MK61}, {".tbi", Type::TINYBASIC}, {".foc", Type::FOCAL},
    {".app", Type::APP}, {".ch8", Type::CHIP8}, {".urq", Type::URQ},
  };
  for(const auto& format : formats)
    if(fat_name::equal(ext, format.suffix))
      return find_direct(directory_id, leaf, format.type, out);
#if defined(MK61_CORE_STANDALONE)
  if(picocalc::file_associations::handler(leaf))
    return find_direct(directory_id, leaf, Type::EXTERNAL_BINARY, out);
#endif
  return false;
}

bool find_manual(u16 directory_id, program_store::Entry& out) {
  return find_direct(directory_id, "manual.md", program_store::ProgramType::MARKDOWN, out) ||
         find_direct(directory_id, "manual.txt", program_store::ProgramType::TEXT, out);
}

} // namespace explorer_autoexec
