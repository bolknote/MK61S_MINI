#include "markdown.hpp"
#include "script.hpp"
#include "storage_path.hpp"
#include <cstdio>
#include <cstring>
namespace picocalc {
bool MarkdownView::open(const char *path) {
  char input[markdown::MAX_SOURCE_SIZE + 1];
  unsigned used = 0;
  if (!files::read_text(path, input, sizeof(input), used) ||
      markdown::compile((const u8 *)input, (u16)used, compiled_,
                        sizeof(compiled_),
                        compiled_size_) != markdown::Status::OK ||
      markdown::to_plain_text_with_links(
          compiled_, compiled_size_, plain_, sizeof(plain_), length_, links_,
          markdown::MAX_PLAIN_LINKS, link_count_) != markdown::Status::OK)
    return false;
  std::snprintf(path_, sizeof(path_), "%s", path);
  top = 0;
  selection = 0xFFFF;
  return true;
}
u16 MarkdownView::next(u16 at) const {
  unsigned count = 0;
  while (at < length_ && plain_[at] != '\n' && count < COLS) {
    ++at;
    ++count;
  }
  if (at < length_ && plain_[at] == '\n')
    ++at;
  return at;
}
u16 MarkdownView::row_start(unsigned row) const {
  u16 at = top;
  while (row-- && at < length_)
    at = next(at);
  return at;
}
void MarkdownView::row(unsigned index, char out[COLS + 1]) const {
  u16 at = row_start(index);
  unsigned count = 0;
  while (at < length_ && plain_[at] != '\n' && count < COLS)
    out[count++] = plain_[at++];
  out[count] = 0;
}
bool MarkdownView::selected(unsigned row, unsigned column) const {
  if (selection >= link_count_)
    return false;
  const unsigned at = row_start(row) + column;
  return at >= links_[selection].begin && at < links_[selection].end;
}
void MarkdownView::scroll(int direction) {
  if (direction > 0) {
    if (row_start(ROWS) < length_)
      top = next(top);
  } else {
    u16 at = 0, previous = 0;
    while (at < top) {
      previous = at;
      at = next(at);
    }
    top = previous;
  }
  selection = 0xFFFF;
}
void MarkdownView::select(int direction) {
  if (!link_count_)
    return;
  selection = selection >= link_count_
                  ? (direction < 0 ? link_count_ - 1 : 0)
                  : (u16)((selection + link_count_ + (direction < 0 ? -1 : 1)) %
                          link_count_);
  const auto &link = links_[selection];
  if (link.begin < top || link.begin >= row_start(ROWS)) {
    top = 0;
    while (next(top) <= link.begin && next(top) > top)
      top = next(top);
  }
}
bool MarkdownView::target(char out[files::PATH_SIZE]) const {
  if (selection >= link_count_)
    return false;
  markdown::Reader reader(compiled_, compiled_size_);
  markdown::Event event{};
  unsigned n = 0;
  while (reader.next(event) == markdown::Status::OK &&
         event.kind != markdown::EventKind::END) {
    if (event.kind != markdown::EventKind::LINK_BEGIN)
      continue;
    if (n++ != selection)
      continue;
    if (!event.path_len || event.path_len >= files::PATH_SIZE)
      return false;
    char path[files::PATH_SIZE];
    std::memcpy(path, event.path, event.path_len);
    path[event.path_len] = 0;
    program_store::Entry current, target;
    if (!script::register_file(path_, current) ||
        storage_path::resolve_file(current.parent_id, path,
                                   program_store::ProgramType::MARKDOWN,
                                   target) != storage_path::Status::OK)
      return false;
    const char *resolved = script::file_path(target.id);
    if (!resolved)
      return false;
    std::snprintf(out, files::PATH_SIZE, "%s", resolved);
    return true;
  }
  return false;
}
} // namespace picocalc
