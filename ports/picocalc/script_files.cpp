#include "m61_text.hpp"
#include "mk8_codec.hpp"
#include "script.hpp"
#include "storage.hpp"
#include "storage_path.hpp"
#include "terminal_core.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace picocalc {
namespace script {
namespace {
struct Node {
  char *path;
  char *source;
  u32 revision;
  u16 length, parent;
  program_store::ProgramType type;
  bool directory, virtual_source;
};
Node *nodes = nullptr;
u16 node_count = 0, node_capacity = 0;
u16 disk_cache = program_store::INVALID_ID;
bool reserve_node() {
  if (node_count < node_capacity)
    return true;
  if (node_capacity == 1024)
    return false;
  const u16 capacity = node_capacity ? node_capacity * 2 : 32;
  auto *candidate = (Node *)std::realloc(nodes, capacity * sizeof(Node));
  if (!candidate)
    return false;
  std::memset(candidate + node_capacity, 0,
              (capacity - node_capacity) * sizeof(Node));
  nodes = candidate;
  node_capacity = capacity;
  return true;
}
using Type = program_store::ProgramType;
struct Extension {
  const char *suffix;
  Type type;
};
constexpr Extension extensions[] = {
    {".m61", Type::MK61},      {".tbi", Type::TINYBASIC},
    {".bas", Type::TINYBASIC}, {".foc", Type::FOCAL},
    {".fcl", Type::FOCAL},     {".md", Type::MARKDOWN},
    {".txt", Type::TEXT},      {".fmk", Type::FONT},
    {".wbmp", Type::IMAGE1},   {".bin", Type::MK61_BINARY},
    {".ch8", Type::CHIP8},     {".app", Type::APP}, {".c8", Type::CHIP8}, {".sheet", Type::SHEET}};
bool ends(const char *text, const char *suffix) {
  const unsigned n = std::strlen(text), k = std::strlen(suffix);
  if (n < k)
    return false;
  for (unsigned i = 0; i < k; ++i)
    if ((text[n - k + i] | 32) != (suffix[i] | 32))
      return false;
  return true;
}
Type type_of(const char *path) {
  for (const auto &ext : extensions)
    if (ends(path, ext.suffix))
      return ext.type;
  return Type::TEXT;
}
bool normalize(const char *base, const char *name, char out[files::PATH_SIZE]) {
  char joined[files::PATH_SIZE];
  const int n = std::snprintf(
      joined, sizeof(joined), "%s%s%s",
      name[0] == '/' || name[0] == '\\' ? "" : base,
      name[0] == '/' || name[0] == '\\' || std::strcmp(base, "/") == 0 ? ""
                                                                       : "/",
      name);
  if (n < 0 || n >= (int)sizeof(joined))
    return false;
  unsigned used = 1;
  out[0] = '/';
  out[1] = 0;
  const char *p = joined;
  while (*p) {
    while (*p == '/' || *p == '\\')
      ++p;
    const char *begin = p;
    while (*p && *p != '/' && *p != '\\')
      ++p;
    const unsigned count = (unsigned)(p - begin);
    if (!count || (count == 1 && *begin == '.'))
      continue;
    if (count == 2 && begin[0] == '.' && begin[1] == '.') {
      while (used > 1 && out[used - 1] != '/')
        --used;
      if (used > 1)
        --used;
    } else {
      if (used > 1)
        out[used++] = '/';
      if (used + count >= files::PATH_SIZE)
        return false;
      std::memcpy(out + used, begin, count);
      used += count;
    }
    out[used] = 0;
  }
  return true;
}
bool argument_utf8(const char *argument, char out[files::PATH_SIZE]) {
  argument = terminal_core::skip_spaces(argument);
  if (!argument)
    return false;
  unsigned size = std::strlen(argument);
  while (size && terminal_core::is_space(argument[size - 1]))
    --size;
  if (size && (*argument == '\'' || *argument == '"')) {
    if (size < 2 || argument[size - 1] != *argument)
      return false;
    ++argument;
    size -= 2;
  }
  unsigned used = 0;
  for (unsigned i = 0; i < size; ++i) {
    const u16 cp = mk8::codepoint((u8)argument[i]);
    if (!cp || used + 3 >= files::PATH_SIZE)
      return false;
    if (cp < 128)
      out[used++] = (char)cp;
    else if (cp < 2048) {
      out[used++] = (char)(0xC0 | (cp >> 6));
      out[used++] = (char)(0x80 | (cp & 63));
    } else {
      out[used++] = (char)(0xE0 | (cp >> 12));
      out[used++] = (char)(0x80 | ((cp >> 6) & 63));
      out[used++] = (char)(0x80 | (cp & 63));
    }
  }
  out[used] = 0;
  return used != 0;
}
bool entry_at(u16 id, program_store::Entry &out) {
  if (id >= node_count)
    return false;
  auto &node = nodes[id];
  files::Entry info;
  if (!node.virtual_source && !files::stat(node.path, info))
    return false;
  if (node.type == Type::MK61 && !node.virtual_source &&
      (!node.source || node.revision != files::revision())) {
    // One decoded SD script cache; return frames keep stable file IDs.
    // Visiting nested scripts must not retain every source in RAM.
    if (disk_cache != id && disk_cache < node_count &&
        !nodes[disk_cache].virtual_source) {
      std::free(nodes[disk_cache].source);
      nodes[disk_cache].source = nullptr;
    }
    disk_cache = id;
    std::free(node.source);
    node.source = nullptr;
    const unsigned capacity = info.size < 65534 ? info.size + 1 : 65535;
    char *source = (char *)std::malloc(capacity);
    unsigned used = 0;
    if (!source)
      return false;
    if (!files::read_text(node.path, source, capacity, used)) {
      std::free(source);
      return false;
    }
    std::free(node.source);
    node.source = source;
    node.length = (u16)used;
    node.revision = files::revision();
  }
  out = {};
  out.id = id;
  out.parent_id = node.parent;
  out.type = node.type;
  out.kind = node.directory ? program_store::NodeKind::DIRECTORY
                            : program_store::NodeKind::FILE;
  out.data_len = node.type == Type::MK61
                     ? node.length
                     : (u16)(info.size > 65534 ? 65534 : info.size);
  const char *name = std::strrchr(node.path, '/');
  name = name ? name + 1 : node.path;
  unsigned length = std::strlen(name);
  if (!node.directory)
    for (const auto &ext : extensions)
      if (ends(name, ext.suffix)) {
        length -= std::strlen(ext.suffix);
        break;
      }
  usize used=0;
  if(!mk8::from_utf8((const u8*)name,length,(u8*)out.name,sizeof(out.name)-1,used)) {
    used=0;
    while(used<length && used+1<sizeof(out.name) && (u8)name[used]<128) { out.name[used]=name[used];++used; }
  }
  out.name[used]=0;
  return true;
}
bool register_normalized(const char *path, program_store::Entry &out) {
  if (std::strcmp(path, "/") == 0) {
    out = {};
    out.id = out.parent_id = program_store::ROOT_ID;
    out.kind = program_store::NodeKind::DIRECTORY;
    return true;
  }
  for (u16 i = 0; i < node_count; ++i)
    if (std::strcmp(nodes[i].path, path) == 0)
      return entry_at(i, out);
  files::Entry info;
  if (!files::stat(path, info))
    return false;
  char parent[files::PATH_SIZE];
  std::snprintf(parent, sizeof(parent), "%s", path);
  char *slash = std::strrchr(parent, '/');
  if (!slash)
    return false;
  if (slash == parent)
    slash[1] = 0;
  else
    *slash = 0;
  program_store::Entry directory;
  if (!register_normalized(parent, directory))
    return false;
  if (!reserve_node())
    return false;
  const u16 id = node_count++;
  char *saved = (char *)std::malloc(std::strlen(path) + 1);
  if (!saved) {
    --node_count;
    return false;
  }
  std::strcpy(saved, path);
  nodes[id] = {saved,         nullptr,        0,    0, directory.id,
               type_of(path), info.directory, false};
  return entry_at(id, out);
}
} // namespace
void reset_files() {
  if (m61_text::active())
    return;
  for (u16 i = 0; i < node_count; ++i) {
    std::free(nodes[i].path);
    std::free(nodes[i].source);
    nodes[i] = {};
  }
  std::free(nodes);
  nodes = nullptr;
  node_count = node_capacity = 0;
  disk_cache = program_store::INVALID_ID;
}
const char *file_path(u16 id) {
  return id == program_store::ROOT_ID ? "/"
         : id < node_count            ? nodes[id].path
                                      : nullptr;
}
bool normalize_path(const char* base,const char* name,char out[files::PATH_SIZE]) {
  return base && name && normalize(base,name,out);
}
program_store::ProgramType file_type(const char* path) { return type_of(path); }
bool register_file(const char *path, program_store::Entry &out) {
  char normalized[files::PATH_SIZE];
  return normalize("/", path, normalized) &&
         register_normalized(normalized, out);
}
bool register_source(const char *path, const char *source, u16 length,
                     program_store::Entry &out) {
  char normalized[files::PATH_SIZE], parent[files::PATH_SIZE];
  if (!source || length > 65534 || !normalize("/", path, normalized))
    return false;
  std::snprintf(parent, sizeof(parent), "%s", normalized);
  char *slash = std::strrchr(parent, '/');
  if (!slash)
    return false;
  if (slash == parent)
    slash[1] = 0;
  else
    *slash = 0;
  program_store::Entry directory;
  if (!register_normalized(parent, directory))
    return false;
  u16 id = 0;
  while (id < node_count && std::strcmp(nodes[id].path, normalized) != 0)
    ++id;
  if (id == node_count && !reserve_node())
    return false;
  auto *copy = (char *)std::malloc((unsigned)length + 1);
  if (!copy)
    return false;
  std::memcpy(copy, source, length);
  copy[length] = 0;
  if (id == node_count) {
    auto *name = (char *)std::malloc(std::strlen(normalized) + 1);
    if (!name) {
      std::free(copy);
      return false;
    }
    std::strcpy(name, normalized);
    nodes[id].path = name;
    ++node_count;
  }
  auto &node = nodes[id];
  std::free(node.source);
  node.source = copy;
  node.length = length;
  node.parent = directory.id;
  node.type = Type::MK61;
  node.directory = false;
  node.virtual_source = true;
  node.revision = files::revision();
  if (disk_cache == id)
    disk_cache = program_store::INVALID_ID;
  return entry_at(id, out);
}
bool lookup_id(u16 id, program_store::Entry &out) { return entry_at(id, out); }
bool read_id(u16 id, u16 offset, u8 *out, u16 count, u16 *used) {
  if (used)
    *used = 0;
  if (count && !out)
    return false;
  program_store::Entry entry;
  if (!entry_at(id, entry))
    return false;
  auto &node = nodes[id];
  if (node.type == Type::MK61) {
    const unsigned n =
        offset < node.length
            ? (node.length - offset < count ? node.length - offset : count)
            : 0;
    if (n)
      std::memcpy(out, node.source + offset, n);
    if (used)
      *used = (u16)n;
    return true;
  }
  unsigned n = 0;
  if (!files::read_range(node.path, offset, out, count, n))
    return false;
  if (used)
    *used = (u16)n;
  return true;
}
storage_path::Status resolve(u16 directory, const char *argument,
                             const Type *required, program_store::Entry &out) {
  using storage_path::Status;
  const char *base = file_path(directory);
  if (!base)
    return Status::NOT_DIRECTORY;
  char name[files::PATH_SIZE], path[files::PATH_SIZE];
  if (!argument_utf8(argument, name) || !normalize(base, name, path))
    return Status::INVALID;
  if (register_normalized(path, out)) {
    if (out.kind != program_store::NodeKind::FILE)
      return Status::NOT_FILE;
    return !required || out.type == *required ? Status::OK : Status::WRONG_TYPE;
  }
  const char *leaf = std::strrchr(path, '/');
  leaf = leaf ? leaf + 1 : path;
  if (std::strchr(leaf, '.'))
    return Status::NOT_FOUND;
  bool found = false;
  program_store::Entry candidate;
  for (const auto &ext : extensions) {
    if (required && ext.type != *required)
      continue;
    char with_extension[files::PATH_SIZE];
    const int n = std::snprintf(with_extension, sizeof(with_extension), "%s%s",
                                path, ext.suffix);
    if (n < 0 || n >= (int)sizeof(with_extension))
      return Status::TOO_LONG;
    if (register_normalized(with_extension, candidate)) {
      if (found)
        return Status::AMBIGUOUS;
      out = candidate;
      found = true;
    }
  }
  return found ? Status::OK : Status::NOT_FOUND;
}
} // namespace script
} // namespace picocalc

namespace program_store {
u32 media_revision() { return picocalc::files::revision(); }
bool entry_by_id(u16 id, Entry &out) {
  return picocalc::script::lookup_id(id, out);
}
bool read_range_id(u16 id, u16 offset, u8 *data, u16 count, u16 *used) {
  return picocalc::script::read_id(id, offset, data, count, used);
}
} // namespace program_store
namespace storage_path {
Status resolve_file(u16 directory, const char *path,
                    program_store::Entry &out) {
  return picocalc::script::resolve(directory, path, nullptr, out);
}
Status resolve_file(u16 directory, const char *path,
                    program_store::ProgramType type,
                    program_store::Entry &out) {
  return picocalc::script::resolve(directory, path, &type, out);
}
} // namespace storage_path
