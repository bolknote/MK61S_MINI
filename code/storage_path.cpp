#include "storage_path.hpp"

#include "fat_name.hpp"

#include <string.h>

namespace storage_path {
namespace {

struct View {
  const char* begin;
  const char* end;
};

static bool is_space(char value) {
  return value == ' ' || value == '\t';
}

static bool is_separator(char value) {
  return value == '/' || value == '\\';
}

static Status make_view(const char* path, View& view) {
  if(path == NULL) return Status::EMPTY;
  const char* begin = path;
  while(is_space(*begin)) begin++;
  const char* end = begin + strlen(begin);
  while(end > begin && is_space(end[-1])) end--;
  if(begin == end) return Status::EMPTY;
  if((*begin == '"' || *begin == '\'') && end - begin >= 2) {
    const char quote = *begin;
    if(end[-1] != quote) return Status::INVALID;
    begin++;
    end--;
    if(begin == end) return Status::EMPTY;
  } else if(*begin == '"' || *begin == '\'' || end[-1] == '"' || end[-1] == '\'') {
    return Status::INVALID;
  }
  view.begin = begin;
  view.end = end;
  return Status::OK;
}

static bool copy_component(const char* begin, const char* end, char* out,
                           usize capacity) {
  const usize len = (usize) (end - begin);
  if(out == NULL || capacity == 0 || len == 0 || len >= capacity) return false;
  memcpy(out, begin, len);
  out[len] = 0;
  return true;
}

static bool parent_of(u16 directory, u16& out) {
  if(directory == program_store::ROOT_ID) {
    out = program_store::ROOT_ID;
    return true;
  }
  program_store::Entry entry;
  if(!program_store::entry_by_id(directory, entry) ||
     entry.kind != program_store::NodeKind::DIRECTORY) return false;
  out = entry.parent_id;
  return true;
}

static Status find_directory_child(u16 parent, const char* name, u16& out) {
  const int count = program_store::child_count(parent);
  bool file_match = false;
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent, index, entry)) return Status::INVALID;
    char visible[VISIBLE_NAME_SIZE];
    if(!visible_name(entry, visible, sizeof(visible))) return Status::INVALID;
    if(!fat_name::equal(visible, name)) continue;
    if(entry.kind == program_store::NodeKind::DIRECTORY) {
      out = entry.id;
      return Status::OK;
    }
    file_match = true;
  }
  return file_match ? Status::NOT_DIRECTORY : Status::NOT_FOUND;
}

static Status walk_directory(u16 cwd, const View& view, u16& out) {
  u16 current = is_separator(*view.begin) ? program_store::ROOT_ID : cwd;
  if(current != program_store::ROOT_ID) {
    program_store::Entry entry;
    if(!program_store::entry_by_id(current, entry) ||
       entry.kind != program_store::NodeKind::DIRECTORY) {
      current = program_store::ROOT_ID;
    }
  }

  const char* cursor = view.begin;
  while(cursor < view.end) {
    while(cursor < view.end && is_separator(*cursor)) cursor++;
    if(cursor == view.end) break;
    const char* component_begin = cursor;
    while(cursor < view.end && !is_separator(*cursor)) cursor++;
    char component[VISIBLE_NAME_SIZE];
    if(!copy_component(component_begin, cursor, component,
                       sizeof(component))) return Status::TOO_LONG;
    if(strcmp(component, ".") == 0) continue;
    if(strcmp(component, "..") == 0) {
      if(!parent_of(current, current)) return Status::NOT_DIRECTORY;
      continue;
    }
    const Status status = find_directory_child(current, component, current);
    if(status != Status::OK) return status;
  }
  out = current;
  return Status::OK;
}

static Status split_parent(u16 cwd, const View& view, u16& out_parent,
                           char* leaf, usize leaf_capacity) {
  if(view.end > view.begin && is_separator(view.end[-1])) return Status::INVALID;
  u16 current = is_separator(*view.begin) ? program_store::ROOT_ID : cwd;
  if(current != program_store::ROOT_ID) {
    program_store::Entry entry;
    if(!program_store::entry_by_id(current, entry) ||
       entry.kind != program_store::NodeKind::DIRECTORY) {
      current = program_store::ROOT_ID;
    }
  }

  const char* cursor = view.begin;
  bool found = false;
  while(cursor < view.end) {
    while(cursor < view.end && is_separator(*cursor)) cursor++;
    if(cursor == view.end) break;
    const char* component_begin = cursor;
    while(cursor < view.end && !is_separator(*cursor)) cursor++;
    const char* next = cursor;
    while(next < view.end && is_separator(*next)) next++;
    char component[VISIBLE_NAME_SIZE];
    if(!copy_component(component_begin, cursor, component,
                       sizeof(component))) return Status::TOO_LONG;
    if(next == view.end) {
      if(strcmp(component, ".") == 0 || strcmp(component, "..") == 0) {
        return Status::INVALID;
      }
      if(!copy_component(component_begin, cursor, leaf, leaf_capacity)) {
        return Status::TOO_LONG;
      }
      found = true;
      break;
    }
    if(strcmp(component, ".") == 0) {
      cursor = next;
      continue;
    }
    if(strcmp(component, "..") == 0) {
      if(!parent_of(current, current)) return Status::NOT_DIRECTORY;
      cursor = next;
      continue;
    }
    const Status status = find_directory_child(current, component, current);
    if(status != Status::OK) return status;
    cursor = next;
  }
  if(!found) return Status::ROOT;
  out_parent = current;
  return Status::OK;
}

struct Extension {
  const char* suffix;
  program_store::ProgramType type;
};

static const Extension EXTENSIONS[] = {
  { ".state.txt", program_store::ProgramType::MK61_STATE },
  { ".m61",       program_store::ProgramType::MK61 },
  { ".foc",       program_store::ProgramType::FOCAL },
  { ".tbi",       program_store::ProgramType::TINYBASIC },
  { ".txt",       program_store::ProgramType::TEXT },
  { ".fmk",       program_store::ProgramType::FONT },
  { ".wbmp",      program_store::ProgramType::IMAGE1 },
  // Старые терминальные псевдонимы по-прежнему принимаются, но каноническая
  // запись использует расширения из program_store::file_extension().
  { ".t1",        program_store::ProgramType::TEXT },
  { ".m2",        program_store::ProgramType::MK61_STATE },
  { ".wbm",       program_store::ProgramType::IMAGE1 }
};

static bool ends_with_ci(const char* text, const char* suffix) {
  const usize text_len = strlen(text);
  const usize suffix_len = strlen(suffix);
  if(suffix_len > text_len) return false;
  return fat_name::equal(text + text_len - suffix_len, suffix);
}

static bool parse_file_leaf(const char* leaf,
                            program_store::ProgramType default_type,
                            bool default_valid,
                            program_store::ProgramType& type,
                            char* basename) {
  const usize leaf_len = strlen(leaf);
  for(const Extension& extension : EXTENSIONS) {
    if(!ends_with_ci(leaf, extension.suffix)) continue;
    const usize suffix_len = strlen(extension.suffix);
    const usize base_len = leaf_len - suffix_len;
    if(base_len == 0 || base_len >= program_store::NAME_SIZE) return false;
    memcpy(basename, leaf, base_len);
    basename[base_len] = 0;
    type = extension.type;
    return true;
  }
  if(!default_valid || leaf_len == 0 || leaf_len >= program_store::NAME_SIZE) {
    return false;
  }
  memcpy(basename, leaf, leaf_len + 1);
  type = default_type;
  return true;
}

static Status find_typed_file(u16 parent, program_store::ProgramType type,
                              const char* basename,
                              program_store::Entry& out) {
  const int count = program_store::child_count(parent);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent, index, entry)) return Status::INVALID;
    if(entry.kind == program_store::NodeKind::FILE && entry.type == type &&
       fat_name::equal(entry.name, basename)) {
      out = entry;
      return Status::OK;
    }
  }
  return Status::NOT_FOUND;
}

static Status find_untyped_file(u16 parent, const char* basename,
                                program_store::Entry& out) {
  const int count = program_store::child_count(parent);
  bool found = false;
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent, index, entry)) return Status::INVALID;
    if(entry.kind != program_store::NodeKind::FILE ||
       !fat_name::equal(entry.name, basename)) continue;
    if(found) return Status::AMBIGUOUS;
    out = entry;
    found = true;
  }
  return found ? Status::OK : Status::NOT_FOUND;
}

static Status exact_visible_entry(u16 parent, const char* leaf,
                                  program_store::Entry& out) {
  const int count = program_store::child_count(parent);
  for(int index = 0; index < count; index++) {
    program_store::Entry entry;
    if(!program_store::child(parent, index, entry)) return Status::INVALID;
    char visible[VISIBLE_NAME_SIZE];
    if(!visible_name(entry, visible, sizeof(visible))) return Status::INVALID;
    if(fat_name::equal(visible, leaf)) {
      out = entry;
      return Status::OK;
    }
  }
  return Status::NOT_FOUND;
}

static Status append_text(char* out, usize capacity, usize& length,
                          const char* text) {
  const usize add = strlen(text);
  if(length + add >= capacity) return Status::TOO_LONG;
  memcpy(out + length, text, add + 1);
  length += add;
  return Status::OK;
}

} // пространство имён

const char* status_text(Status status) {
  switch(status) {
    case Status::OK: return "ok";
    case Status::EMPTY: return "empty path";
    case Status::INVALID: return "invalid path";
    case Status::TOO_LONG: return "path too long";
    case Status::NOT_FOUND: return "not found";
    case Status::NOT_DIRECTORY: return "not a directory";
    case Status::NOT_FILE: return "not a file";
    case Status::WRONG_TYPE: return "wrong file type";
    case Status::AMBIGUOUS: return "ambiguous name; add an extension";
    case Status::EXISTS: return "already exists";
    case Status::IO_ERROR: return "storage error";
    case Status::ROOT: return "root has no directory entry";
  }
  return "path error";
}

bool visible_name(const program_store::Entry& entry, char* out,
                  usize capacity) {
  if(out == NULL || capacity == 0 || entry.name[0] == 0) return false;
  const usize base_len = strlen(entry.name);
  if(entry.kind == program_store::NodeKind::DIRECTORY) {
    if(base_len >= capacity) return false;
    memcpy(out, entry.name, base_len + 1);
    return true;
  }
  if(entry.kind != program_store::NodeKind::FILE) return false;
  const char* extension = program_store::file_extension(entry.type);
  const usize extension_len = strlen(extension);
  if(base_len + 1 + extension_len >= capacity) return false;
  memcpy(out, entry.name, base_len);
  out[base_len] = '.';
  memcpy(out + base_len + 1, extension, extension_len + 1);
  return true;
}

Status resolve_directory(u16 cwd, const char* path, u16& out_directory) {
  View view;
  const Status status = make_view(path, view);
  return status == Status::OK ? walk_directory(cwd, view, out_directory)
                              : status;
}

Status resolve_entry(u16 cwd, const char* path, program_store::Entry& out) {
  View view;
  Status status = make_view(path, view);
  if(status != Status::OK) return status;
  u16 parent = program_store::ROOT_ID;
  char leaf[VISIBLE_NAME_SIZE];
  status = split_parent(cwd, view, parent, leaf, sizeof(leaf));
  if(status != Status::OK) return status;
  status = exact_visible_entry(parent, leaf, out);
  if(status == Status::OK) return status;

  program_store::ProgramType type = program_store::ProgramType::MK61;
  char basename[program_store::NAME_SIZE];
  if(parse_file_leaf(leaf, type, false, type, basename)) {
    return find_typed_file(parent, type, basename, out);
  }
  return find_untyped_file(parent, leaf, out);
}

Status resolve_file(u16 cwd, const char* path, program_store::Entry& out) {
  const Status status = resolve_entry(cwd, path, out);
  if(status != Status::OK) return status;
  return out.kind == program_store::NodeKind::FILE ? Status::OK
                                                   : Status::NOT_FILE;
}

Status resolve_file(u16 cwd, const char* path,
                    program_store::ProgramType required_type,
                    program_store::Entry& out) {
  View view;
  Status status = make_view(path, view);
  if(status != Status::OK) return status;
  u16 parent = program_store::ROOT_ID;
  char leaf[VISIBLE_NAME_SIZE];
  status = split_parent(cwd, view, parent, leaf, sizeof(leaf));
  if(status != Status::OK) return status;

  program_store::ProgramType type = required_type;
  char basename[program_store::NAME_SIZE];
  if(!parse_file_leaf(leaf, required_type, true, type, basename)) {
    return Status::INVALID;
  }
  if(type != required_type) return Status::WRONG_TYPE;
  return find_typed_file(parent, type, basename, out);
}

Status file_target(u16 cwd, const char* path,
                   program_store::ProgramType default_type,
                   FileTarget& out) {
  View view;
  Status status = make_view(path, view);
  if(status != Status::OK) return status;
  char leaf[VISIBLE_NAME_SIZE];
  status = split_parent(cwd, view, out.parent_id, leaf, sizeof(leaf));
  if(status != Status::OK) return status;
  if(!parse_file_leaf(leaf, default_type, true, out.type, out.name)) {
    return Status::INVALID;
  }
  if(out.type != default_type) return Status::WRONG_TYPE;
  return program_store::basename_valid(out.name) ? Status::OK : Status::INVALID;
}

Status file_target(u16 cwd, const char* path, FileTarget& out) {
  View view;
  Status status = make_view(path, view);
  if(status != Status::OK) return status;
  char leaf[VISIBLE_NAME_SIZE];
  status = split_parent(cwd, view, out.parent_id, leaf, sizeof(leaf));
  if(status != Status::OK) return status;
  program_store::ProgramType ignored_default = program_store::ProgramType::MK61;
  if(!parse_file_leaf(leaf, ignored_default, false, out.type, out.name)) {
    return Status::INVALID;
  }
  return program_store::basename_valid(out.name) ? Status::OK : Status::INVALID;
}

Status create_directory(u16 cwd, const char* path, bool parents,
                        u16& out_directory) {
  View view;
  Status status = make_view(path, view);
  if(status != Status::OK) return status;
  u16 current = is_separator(*view.begin) ? program_store::ROOT_ID : cwd;
  if(current != program_store::ROOT_ID) {
    program_store::Entry entry;
    if(!program_store::entry_by_id(current, entry) ||
       entry.kind != program_store::NodeKind::DIRECTORY) {
      current = program_store::ROOT_ID;
    }
  }

  const char* cursor = view.begin;
  bool any = false;
  while(cursor < view.end) {
    while(cursor < view.end && is_separator(*cursor)) cursor++;
    if(cursor == view.end) break;
    const char* begin = cursor;
    while(cursor < view.end && !is_separator(*cursor)) cursor++;
    const char* next = cursor;
    while(next < view.end && is_separator(*next)) next++;
    const bool last = next == view.end;
    char component[VISIBLE_NAME_SIZE];
    if(!copy_component(begin, cursor, component, sizeof(component))) {
      return Status::TOO_LONG;
    }
    any = true;
    if(strcmp(component, ".") == 0) {
      if(last && !parents) return Status::EXISTS;
      cursor = next;
      continue;
    }
    if(strcmp(component, "..") == 0) {
      if(!parent_of(current, current)) return Status::NOT_DIRECTORY;
      if(last && !parents) return Status::EXISTS;
      cursor = next;
      continue;
    }

    u16 child = program_store::INVALID_ID;
    status = find_directory_child(current, component, child);
    if(status == Status::OK) {
      if(last && !parents) return Status::EXISTS;
      current = child;
      cursor = next;
      continue;
    }
    if(status == Status::NOT_DIRECTORY) return status;
    if(!last && !parents) return Status::NOT_FOUND;
    if(!program_store::basename_valid(component)) return Status::INVALID;
    if(!program_store::create_directory(current, component,
        program_store::INVALID_ID, &child)) return Status::IO_ERROR;
    current = child;
    cursor = next;
  }
  if(!any) {
    out_directory = current;
    return parents ? Status::OK : Status::EXISTS;
  }
  out_directory = current;
  return Status::OK;
}

Status move_target(u16 cwd, const program_store::Entry& source,
                   const char* destination, u16& out_parent,
                   char* out_name, usize name_capacity) {
  u16 directory = program_store::ROOT_ID;
  Status status = resolve_directory(cwd, destination, directory);
  if(status == Status::OK) {
    const usize len = strlen(source.name);
    if(len >= name_capacity) return Status::TOO_LONG;
    memcpy(out_name, source.name, len + 1);
    out_parent = directory;
    return Status::OK;
  }

  program_store::Entry existing;
  const Status existing_status = resolve_entry(cwd, destination, existing);
  if(existing_status == Status::OK && existing.id != source.id) {
    return Status::EXISTS;
  }

  View view;
  status = make_view(destination, view);
  if(status != Status::OK) return status;
  char leaf[VISIBLE_NAME_SIZE];
  status = split_parent(cwd, view, out_parent, leaf, sizeof(leaf));
  if(status != Status::OK) return status;
  if(source.kind == program_store::NodeKind::DIRECTORY) {
    const usize len = strlen(leaf);
    if(len >= name_capacity || !program_store::basename_valid(leaf)) {
      return Status::INVALID;
    }
    memcpy(out_name, leaf, len + 1);
    return Status::OK;
  }
  if(source.kind != program_store::NodeKind::FILE) return Status::INVALID;

  program_store::ProgramType type = source.type;
  char basename[program_store::NAME_SIZE];
  if(!parse_file_leaf(leaf, source.type, true, type, basename)) {
    return Status::INVALID;
  }
  if(type != source.type) return Status::WRONG_TYPE;
  const usize len = strlen(basename);
  if(len >= name_capacity || !program_store::basename_valid(basename)) {
    return Status::INVALID;
  }
  memcpy(out_name, basename, len + 1);
  return Status::OK;
}

Status format_directory(u16 directory_id, char* out, usize capacity) {
  if(out == NULL || capacity < 2) return Status::TOO_LONG;
  usize begin = capacity - 1;
  out[begin] = 0;
  u16 current = directory_id;
  for(u8 depth = 0; current != program_store::ROOT_ID; depth++) {
    if(depth >= program_store::MAX_DIRECTORY_DEPTH) return Status::INVALID;
    program_store::Entry entry;
    if(!program_store::entry_by_id(current, entry) ||
       entry.kind != program_store::NodeKind::DIRECTORY) {
      return Status::NOT_DIRECTORY;
    }
    const usize len = strlen(entry.name);
    if(begin < len + 1) return Status::TOO_LONG;
    begin -= len;
    memcpy(out + begin, entry.name, len);
    out[--begin] = '/';
    current = entry.parent_id;
  }
  if(begin == capacity - 1) out[--begin] = '/';
  const usize length = capacity - begin;
  memmove(out, out + begin, length);
  return Status::OK;
}

Status format_entry(const program_store::Entry& entry, char* out,
                    usize capacity) {
  Status status = format_directory(entry.parent_id, out, capacity);
  if(status != Status::OK) return status;
  usize length = strlen(out);
  if(length > 1) {
    status = append_text(out, capacity, length, "/");
    if(status != Status::OK) return status;
  }
  char leaf[VISIBLE_NAME_SIZE];
  if(!visible_name(entry, leaf, sizeof(leaf))) return Status::INVALID;
  return append_text(out, capacity, length, leaf);
}

bool directory_within(u16 directory_id, u16 ancestor_id) {
  u16 current = directory_id;
  for(u8 depth = 0; depth <= program_store::MAX_DIRECTORY_DEPTH; depth++) {
    if(current == ancestor_id) return true;
    if(current == program_store::ROOT_ID) return false;
    if(!parent_of(current, current)) return false;
  }
  return false;
}

} // пространство имён storage_path
