#ifndef MK61_PICOCALC_MARKDOWN_HPP
#define MK61_PICOCALC_MARKDOWN_HPP
#include "markdown_document.hpp"
#include "storage.hpp"
#include "settings.hpp"
#include "markdown_scroll.hpp"
namespace picocalc {
class MarkdownView {
public:
  static constexpr unsigned COLS = 38, ROWS = 14;
  bool open(const char *path);
  void row(unsigned index, char out[COLS + 1]) const;
  bool selected(unsigned row, unsigned column) const;
  void scroll(int direction, bool page = false);
  void select(int direction);
  bool target(char out[files::PATH_SIZE]) const;
  const u8* frame() const { return frame_; }
  const u8* native_frame() const;
  u32 revision() const { return revision_; }
  void set_font(const Settings& settings) { settings_=settings;render(); }
  void restore(u16 offset,u16 link) { top=offset;selection=link;render(); }
  const char *path() const { return path_; }
  u16 top = 0, selection = 0xFFFF;
  u16 links() const { return link_count_; }

private:
  u32 revision_=0;
  u16 next(u16 at) const;
  u16 row_start(unsigned row) const;
  char path_[files::PATH_SIZE]{};
  u8 compiled_[markdown::MAX_COMPILED_SIZE]{};
  char plain_[markdown::MAX_COMPILED_SIZE + 1]{};
  markdown::PlainLink links_[markdown::MAX_PLAIN_LINKS]{};
  u16 compiled_size_ = 0, length_ = 0, link_count_ = 0;
  void render();
  Settings settings_{};
  u8 frame_[1536]{};
  markdown_scroll::Metrics metrics_{};
};
} // namespace picocalc
#endif
