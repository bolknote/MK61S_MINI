#include "markdown.hpp"
#include "canvas.hpp"
#include "script.hpp"
#include "storage_path.hpp"
#include "markdown_graphic_layout.hpp"
#include "fonts.hpp"
#include "native_assets.hpp"
#include <memory>
#include <new>
#include <cstdio>
#include <cstring>
namespace picocalc {
namespace {
struct GraphicPlatform {
  Settings settings;
  bool native_assets=true;
  u16 image_width(u16 normal) const { return native_assets?320:normal; }
  bool enabled() const { return settings.ui_font_family!=0; }
  mk61_service_ui_font_info info() const { return fonts::info(settings); }
  u8 height() const { return info().height; }
  u8 ascent() const { return info().ascent; }
  u8 line_gap() const { return info().line_gap; }
  bool glyph(u16 cp,mk61_service_ui_glyph& out) const { return fonts::glyph(settings,cp,out); }
  struct Image {
    std::unique_ptr<u8[]> bytes;
    u16 length=0;
    Image(const GraphicPlatform& platform,u16 parent,const char* path) {
      program_store::Entry entry{};
      if(storage_path::resolve_file(parent,path,program_store::ProgramType::IMAGE1,entry)!=storage_path::Status::OK ||
         !entry.data_len || entry.data_len>program_store::MAX_IMAGE1_SIZE) return;
      char native[files::PATH_SIZE];files::Entry info{};
      const char* resolved=script::file_path(entry.id);unsigned size=entry.data_len;
      if(platform.native_assets && native_assets::image(resolved,native,info)) { resolved=native;size=info.size; }
      if(!size || size>program_store::MAX_IMAGE1_SIZE) return;
      bytes.reset(new(std::nothrow) u8[size]);unsigned used=0;
      const u32 revision=files::revision();
      if(!bytes || !files::read(resolved,bytes.get(),size,used) ||
         used!=size || revision!=files::revision()) { bytes.reset();return; }
      length=(u16)used;
    }
    bool ok() const { return bytes!=nullptr; }
    const u8* data() const { return bytes.get(); }
    u16 size() const { return length; }
  };
};
}
const u8* MarkdownView::native_frame() const { return canvas::frame(); }
void MarkdownView::render() {
  program_store::Entry entry{};
  if(!script::register_file(path_,entry)) { std::memset(frame_,0,sizeof(frame_));return; }
  markdown_scroll::Probe compatibility(top);
  markdown_graphics::Layout<GraphicPlatform> compact(frame_,192,64,top,64,
      entry.parent_id,compatibility,selection,nullptr,GraphicPlatform{settings_,false});
  (void)compact.render(compiled_,compiled_size_);
  markdown_scroll::Probe probe(top);
  markdown_graphics::Layout<GraphicPlatform> layout(canvas::frame(),320,240,top,240,
      entry.parent_id,probe,selection,nullptr,GraphicPlatform{settings_});
  metrics_=probe.finish(layout.render(compiled_,compiled_size_));
  if(top!=metrics_.current_top) { top=metrics_.current_top;render(); }
}
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
  render();
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
  u16 at = 0;
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
void MarkdownView::scroll(int direction,bool page) {
  top=direction>0 ? (page?metrics_.fast_next_anchor:metrics_.next_anchor) :
      (page?metrics_.fast_previous_anchor:metrics_.previous_anchor);
  selection = 0xFFFF;
  render();
}
void MarkdownView::select(int direction) {
  if (!link_count_)
    return;
  selection = selection >= link_count_
                  ? (direction < 0 ? link_count_ - 1 : 0)
                  : (u16)((selection + link_count_ + (direction < 0 ? -1 : 1)) %
                          link_count_);
  program_store::Entry entry{};
  if(!script::register_file(path_,entry)) return;
  markdown_scroll::Probe probe(top);markdown_graphics::LinkLayout links{};
  markdown_graphics::Layout<GraphicPlatform> layout(canvas::frame(),320,240,top,240,
      entry.parent_id,probe,selection,&links,GraphicPlatform{settings_});
  (void)layout.render(compiled_,compiled_size_);
  if(links.selected_seen && !links.selected_visible) top=links.selected_top;
  render();
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
