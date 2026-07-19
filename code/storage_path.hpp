#ifndef STORAGE_PATH_HPP
#define STORAGE_PATH_HPP

#include "program_store.hpp"
#include "rust_types.h"

namespace storage_path {

// A visible FAT name is the 31-byte C5 basename plus the longest generated
// extension (".state.txt") and the terminating zero.
static constexpr usize VISIBLE_NAME_SIZE = program_store::NAME_SIZE + 16;

enum class Status : u8 {
  OK = 0,
  EMPTY,
  INVALID,
  TOO_LONG,
  NOT_FOUND,
  NOT_DIRECTORY,
  NOT_FILE,
  WRONG_TYPE,
  AMBIGUOUS,
  EXISTS,
  IO_ERROR,
  ROOT
};

struct FileTarget {
  u16 parent_id;
  program_store::ProgramType type;
  char name[program_store::NAME_SIZE];
};

const char* status_text(Status status);

// Produces the FAT-visible leaf name (basename plus the type extension for a
// file). The result is also the canonical terminal spelling of an entry.
bool visible_name(const program_store::Entry& entry, char* out, usize capacity);

// Paths accept '/' and '\\', absolute or relative spelling, repeated
// separators, '.' and '..'. A whole path may be enclosed in matching single
// or double quotes. Matching follows locale-independent FAT-style simple
// Unicode case folding for common cased scripts, including Cyrillic.
Status resolve_directory(u16 cwd, const char* path, u16& out_directory);
Status resolve_entry(u16 cwd, const char* path, program_store::Entry& out);
Status resolve_file(u16 cwd, const char* path, program_store::Entry& out);
Status resolve_file(u16 cwd, const char* path,
                    program_store::ProgramType required_type,
                    program_store::Entry& out);

// Resolves the directory portion and validates a file leaf for creation or
// overwrite. If the suffix is omitted, default_type is used.
Status file_target(u16 cwd, const char* path,
                   program_store::ProgramType default_type,
                   FileTarget& out);

// Creates the final directory. With parents=true, missing intermediate
// components are created as in `mkdir -p`.
Status create_directory(u16 cwd, const char* path, bool parents,
                        u16& out_directory);

// Implements shell-style mv destination rules: an existing directory keeps
// the source name; otherwise the final component is the new name.
Status move_target(u16 cwd, const program_store::Entry& source,
                   const char* destination, u16& out_parent,
                   char* out_name, usize name_capacity);

Status format_directory(u16 directory_id, char* out, usize capacity);
Status format_entry(const program_store::Entry& entry, char* out,
                    usize capacity);

// True for the directory itself and every directory below it.
bool directory_within(u16 directory_id, u16 ancestor_id);

} // namespace storage_path

#endif
