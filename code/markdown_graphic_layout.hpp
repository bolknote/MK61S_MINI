#ifndef MK61_MARKDOWN_GRAPHIC_LAYOUT_HPP
#define MK61_MARKDOWN_GRAPHIC_LAYOUT_HPP

#include "markdown_document.hpp"
#include "markdown_scroll.hpp"
#include "builtin_font.hpp"
#include "fmk_font.hpp"
#include "mk8_codec.hpp"
#include "loadable_app_services.h"
#include "wbmp.hpp"
#include <string.h>

// Shared raster/layout engine. Platform supplies UI glyphs and a scoped WBMP
// reader; no display, storage driver, heap policy or event loop is assumed.
namespace markdown_graphics {
static constexpr u16 NO_LINK = 0xFFFFU;
static constexpr bool link_is_selected(u16 link, u16 selected) {
  return selected != NO_LINK && link == selected;
}
inline u8 styled_advance(const mk61_service_ui_glyph& glyph, bool bold, bool italic) {
  return (u8)(glyph.advance + (bold ? 1U : 0U) +
      (italic ? (glyph.height - 1U) / 3U : 0U));
}
using markdown::BlockKind;
using markdown::ListKind;
using markdown::TaskState;
using markdown::EventKind;
using markdown::STYLE_NONE;
using markdown::STYLE_BOLD;
using markdown::STYLE_ITALIC;
using markdown::STYLE_STRIKE;
using markdown::STYLE_CODE;
using markdown::STYLE_LINK;

static constexpr u8 STYLE_SELECTED = 1U << 7;
struct LinkLayout {
  u16 count;
  u16 first_visible;
  u16 last_visible;
  u16 selected_top;
  u16 selected_bottom;
  bool selected_seen;
  bool selected_visible;

  void reset() {
    count = 0;
    first_visible = NO_LINK;
    last_visible = NO_LINK;
    selected_top = 0;
    selected_bottom = 0;
    selected_seen = false;
    selected_visible = false;
  }
};

static void set_frame_pixel(
    u8* frame, u16 frame_width, u16 frame_height,
    i16 x, i16 y, bool dark) {
  if(frame == nullptr || x < 0 || x >= (i16) frame_width ||
     y < 0 || y >= (i16) frame_height) return;
  const usize offset = (usize) (y / 8) * frame_width + (u16) x;
  const u8 mask = (u8) (1U << (y & 7));
  if(dark) frame[offset] |= mask;
  else frame[offset] &= (u8) ~mask;
}

struct GlyphCell {
  u16 codepoint;
  u8 style;
  u8 advance;
  u16 link;
};

template<class Platform>
class Layout {
 public:
  Layout(u8* frame, u16 frame_width, u16 display_height,
                u16 viewport_top, u16 viewport_height, u16 parent_id,
                markdown_scroll::Probe& scroll_probe,
                u16 selected_link, LinkLayout* links, const Platform& platform = Platform{})
      : frame(frame), frame_width(frame_width),
        display_height(display_height), viewport_top(viewport_top),
        viewport_height(viewport_height), parent_id(parent_id),
        scroll_probe(scroll_probe), links(links), ui_font_source(platform),
        compact(frame_width <= 100U || display_height <= 16U),
        y(compact ? 0U : 2U), block_start_y(compact ? 0U : 2U),
        content_x(2),
        available_width(frame_width > 4U
            ? (u16) (frame_width - 4U) : 1U),
        line_height(8), line_pitch(10), scale(1),
        face(builtin_font::FaceId::FONT_5X8), cell_count(0),
        cell_width(0), first_visual_line(true), style(STYLE_NONE),
        block({BlockKind::PARAGRAPH, 0, ListKind::NONE,
               TaskState::NONE, 0}), block_open(false),
        stream_valid(true), first_anchor(true), current_link(NO_LINK),
        next_link(0), selected_link(selected_link) {
    if(links != nullptr) links->reset();
    if(frame != nullptr && viewport_height != 0) {
      const usize bytes = (usize) frame_width *
          ((viewport_height + 7U) / 8U);
      memset(frame, 0, bytes);
    }
  }

  u16 render(const u8* compiled, u16 size) {
    markdown::Reader reader(compiled, size);
    while(true) {
      markdown::Event event = {};
      const markdown::Status status = reader.next(event);
      if(status != markdown::Status::OK) {
        stream_valid = false;
        break;
      }
      if(event.kind == EventKind::END) break;
      switch(event.kind) {
        case EventKind::BLOCK_BEGIN:
          begin_block(event.block);
          break;
        case EventKind::BLOCK_END:
          end_block();
          break;
        case EventKind::STYLE:
          style = event.style;
          break;
        case EventKind::TEXT:
          append_text(event.text, event.text_len);
          break;
        case EventKind::HARD_BREAK:
          flush_line(true);
          break;
        case EventKind::IMAGE:
          render_image(event);
          break;
        case EventKind::LINK_BEGIN:
          current_link = next_link++;
          if(links != nullptr) links->count = next_link;
          break;
        case EventKind::LINK_END:
          current_link = NO_LINK;
          break;
        case EventKind::END:
          break;
      }
    }
    if(block_open) end_block();
    return y < 1 ? 1 : y;
  }

  bool valid(void) const { return stream_valid; }

 private:
  static constexpr u8 MAX_LINE_CELLS = 64;

  u8* frame;
  u16 frame_width;
  u16 display_height;
  u16 viewport_top;
  u16 viewport_height;
  u16 parent_id;
  markdown_scroll::Probe& scroll_probe;
  LinkLayout* links;
  Platform ui_font_source;
  bool compact;
  u16 y;
  u16 block_start_y;
  u16 content_x;
  u16 available_width;
  u8 line_height;
  u8 line_pitch;
  u8 scale;
  builtin_font::FaceId face;
  GlyphCell cells[MAX_LINE_CELLS];
  u8 cell_count;
  u16 cell_width;
  bool first_visual_line;
  u8 style;
  markdown::Block block;
  bool block_open;
  bool stream_valid;
  bool first_anchor;
  u16 current_link;
  u16 next_link;
  u16 selected_link;

  u8 glyph_advance(builtin_font::FaceId face, u8 scale) const {
    const u8 native_advance = face == builtin_font::FaceId::FONT_3X5
        ? 4U : (compact ? 5U : 6U);
    return (u8) (native_advance * scale);
  }

  bool ui_prose(void) const {
    return !compact && ui_font_source.enabled() && block.kind != BlockKind::CODE;
  }

  u8 text_advance(u16 codepoint, u8 glyph_style,
                  builtin_font::FaceId selected_face, u8 selected_scale) const {
    if(ui_prose() && selected_face == builtin_font::FaceId::FONT_5X8 &&
       (glyph_style & STYLE_CODE) == 0) {
      mk61_service_ui_glyph glyph = {};
      if(ui_font_source.glyph(codepoint, glyph)) {
        return styled_advance(glyph,
          (glyph_style & STYLE_BOLD) != 0, (glyph_style & STYLE_ITALIC) != 0);
      }
    }
    return glyph_advance(selected_face, selected_scale);
  }

  void record_anchor(u16 position) {
    // Первое содержимое сохраняет исходный двухпиксельный верхний отступ:
    // следующая остановка после начала документа должна быть уже второй
    // визуальной строкой, а не смещением 2.
    scroll_probe.note(first_anchor ? 0 : position);
    first_anchor = false;
  }

  bool vertical_span_visible(i32 global_y, i32 height) const {
    if(height <= 0) return false;
    const i32 top = viewport_top;
    const i32 bottom = top + viewport_height;
    return global_y < bottom && global_y + height > top;
  }

  void set_global_pixel(i16 x, i16 global_y, bool dark = true) {
    const i32 screen_y = (i32) global_y - viewport_top;
    if(screen_y < 0 || screen_y >= viewport_height) return;
    set_frame_pixel(frame, frame_width, viewport_height,
                    x, (i16) screen_y, dark);
  }

  void hline(i16 x, i16 global_y, i16 width, bool dark = true) {
    if(width <= 0 || !vertical_span_visible(global_y, 1)) return;
    for(i16 dx = 0; dx < width; dx++) {
      set_global_pixel((i16) (x + dx), global_y, dark);
    }
  }

  void vline(i16 x, i16 global_y, i16 height, bool dark = true) {
    if(height <= 0) return;
    const i32 begin = (i32) global_y < (i32) viewport_top
        ? (i32) viewport_top : (i32) global_y;
    const i32 raw_end = (i32) global_y + height;
    const i32 viewport_end = (i32) viewport_top + viewport_height;
    const i32 end = raw_end < viewport_end ? raw_end : viewport_end;
    for(i32 py = begin; py < end; py++) {
      set_global_pixel(x, (i16) py, dark);
    }
  }

  void rect(i16 x, i16 global_y, i16 width, i16 height) {
    if(width <= 0 || height <= 0) return;
    hline(x, global_y, width);
    hline(x, (i16) (global_y + height - 1), width);
    vline(x, global_y, height);
    vline((i16) (x + width - 1), global_y, height);
  }

  void fill_rect(i16 x, i16 global_y, i16 width, i16 height, bool dark) {
    if(width <= 0 || height <= 0) return;
    const i32 begin = (i32) global_y < (i32) viewport_top
        ? (i32) viewport_top : (i32) global_y;
    const i32 raw_end = (i32) global_y + height;
    const i32 viewport_end = (i32) viewport_top + viewport_height;
    const i32 end = raw_end < viewport_end ? raw_end : viewport_end;
    for(i32 py = begin; py < end; py++) {
      hline(x, (i16) py, width, dark);
    }
  }

  void draw_glyph(u16 codepoint, u8 glyph_style,
                  i16 x, i16 global_y,
                  builtin_font::FaceId selected_face, u8 selected_scale) {
    const bool prose = ui_prose() && selected_face == builtin_font::FaceId::FONT_5X8;
    i16 height = prose ? ui_font_source.height() : (i16) (
        (selected_face == builtin_font::FaceId::FONT_3X5 ? 5U : 8U) *
        selected_scale);
    if(!vertical_span_visible(global_y, height)) return;

    builtin_font::Raster raster = {};
    i16 ink_x = x;
    i16 ink_y = global_y;
    u8 advance = glyph_advance(selected_face, selected_scale);
    if(prose && (glyph_style & STYLE_CODE) == 0) {
      mk61_service_ui_glyph glyph = {};
      if(ui_font_source.glyph(codepoint, glyph)) {
        raster.width = glyph.width;
        raster.height = glyph.height;
        memcpy(raster.data, glyph.pixels, sizeof(glyph.pixels));
        ink_x = (i16) (x + glyph.bearing_x);
        ink_y = (i16) (global_y + ui_font_source.ascent() - glyph.bearing_y);
        advance = styled_advance(glyph,
          (glyph_style & STYLE_BOLD) != 0, (glyph_style & STYLE_ITALIC) != 0);
      }
    }
    if(raster.height == 0) {
      if(!builtin_font::decode(selected_face, codepoint, raster) &&
         !builtin_font::decode(selected_face, '?', raster)) return;
      height = (i16) raster.height * selected_scale;
      if(prose) {
        // Inline code stays 5x8 and aligns to the surrounding baseline.
        ink_y = global_y = (i16) (global_y + ui_font_source.ascent() - 7U);
        glyph_style &= (u8) ~(STYLE_BOLD | STYLE_ITALIC);
      }
    }
    const bool inverse =
        (glyph_style & (STYLE_CODE | STYLE_SELECTED)) != 0;
    if(inverse) fill_rect(x, global_y, advance, height, true);

    for(u8 source_y = 0; source_y < raster.height; source_y++) {
      const i16 italic_shift = (glyph_style & STYLE_ITALIC) != 0
          ? (i16) ((raster.height - 1U - source_y) / 3U)
          : 0;
      for(u8 source_x = 0; source_x < raster.width; source_x++) {
        if(!fmk::bitmapPixel(raster.data, raster.width,
                             source_x, source_y)) continue;
        for(u8 sy = 0; sy < selected_scale; sy++) {
          for(u8 sx = 0; sx < selected_scale; sx++) {
            const i16 px = (i16) (ink_x + italic_shift * selected_scale +
                                  source_x * selected_scale + sx);
            const i16 py = (i16) (ink_y +
                                  source_y * selected_scale + sy);
            set_global_pixel(px, py, !inverse);
            if((glyph_style & STYLE_BOLD) != 0) {
              set_global_pixel((i16) (px + 1), py, !inverse);
            }
          }
        }
      }
    }

    if((glyph_style & STYLE_STRIKE) != 0) {
      hline(x, (i16) (global_y + height / 2), advance, !inverse);
    }
    if((glyph_style & STYLE_LINK) != 0) {
      hline(x, (i16) (global_y + height - 1), advance, !inverse);
    }
  }

  void draw_ascii(const char* text, i16 x, i16 global_y, u8 glyph_style,
                  builtin_font::FaceId selected_face =
                      builtin_font::FaceId::FONT_5X8) {
    if(text == nullptr) return;
    while(*text != 0) {
      const u8 codepoint = (u8) *text++;
      const u8 advance = text_advance(codepoint, glyph_style, selected_face, 1);
      draw_glyph(codepoint, glyph_style, x, global_y,
                 selected_face, 1);
      x = (i16) (x + advance);
    }
  }

  u8 base_margin(void) const { return compact ? 0U : 2U; }

  u16 width_from(u16 left) const {
    const u8 right = base_margin();
    return frame_width > (u16) left + right
        ? (u16) (frame_width - left - right) : 1U;
  }

  void configure_block(void) {
    content_x = base_margin();
    available_width = width_from(content_x);
    face = builtin_font::FaceId::FONT_5X8;
    scale = 1;
    line_height = 8U;
    line_pitch = compact ? 8U : 10U;

    if(ui_prose()) {
      line_height = ui_font_source.height();
      line_pitch = (u8) (line_height + ui_font_source.line_gap());
    }

    if(block.kind == BlockKind::HEADING) {
      if(block.level == 1 && !ui_prose()) {
        if(compact) {
          face = builtin_font::FaceId::FONT_5X8;
          line_height = 8;
          line_pitch = 8;
        } else {
          scale = 2;
          line_height = 16;
          line_pitch = 18;
        }
      }
    } else if(block.kind == BlockKind::CODE) {
      face = compact ? builtin_font::FaceId::FONT_5X8
                     : builtin_font::FaceId::FONT_3X5;
      line_height = compact ? 8U : 5U;
      line_pitch = compact ? 8U : 6U;
      content_x = compact ? 2U : 5U;
      available_width = width_from(content_x);
    } else if(block.kind == BlockKind::QUOTE) {
      const u8 depth = block.level == 0 ? 1 : block.level;
      const u8 margin = compact
          ? (depth > 3 ? 6U : (u8) (depth * 2U))
          : (depth > 3 ? 12U : (u8) (depth * 4U));
      content_x = (u8) (base_margin() + margin);
      available_width = width_from(content_x);
    } else if(block.kind == BlockKind::LIST_ITEM) {
      char prefix[16];
      const u8 prefix_length = list_prefix(prefix);
      const u8 indent = compact
          ? (block.level > 3 ? 12U : (u8) (block.level * 4U))
          : (block.level > 3 ? 24U : (u8) (block.level * 8U));
      u8 prefix_width = 0;
      for(u8 i = 0; i < prefix_length; i++) {
        prefix_width = (u8) (prefix_width + text_advance((u8) prefix[i], STYLE_NONE, face, scale));
      }
      content_x = (u8) (base_margin() + indent + prefix_width);
      available_width = width_from(content_x);
    }
  }

  void begin_block(const markdown::Block& next) {
    if(block_open) end_block();
    block = next;
    block_open = true;
    block_start_y = y;
    cell_count = 0;
    cell_width = 0;
    first_visual_line = true;
    style = STYLE_NONE;
    configure_block();
    if(block.kind == BlockKind::THEMATIC_BREAK) {
      record_anchor(y);
      const u8 left = compact ? 2U : 4U;
      hline(left, (i16) (y + (compact ? 1U : 2U)),
            frame_width > (u16) left * 2U
                ? (i16) (frame_width - (u16) left * 2U) : 1);
      y = (u16) (y + (compact ? 2U : 5U));
    } else if(block.kind == BlockKind::BLANK) {
      y = (u16) (y + (compact ? 1U : 4U));
    }
  }

  u8 list_prefix(char output[16]) const {
    u8 length = 0;
    output[0] = 0;
    if(block.kind != BlockKind::LIST_ITEM) return 0;
    if(block.list_kind == ListKind::ORDERED) {
      char digits[5];
      u8 digit_count = 0;
      u16 number = block.ordinal;
      do {
        digits[digit_count++] = (char) ('0' + number % 10U);
        number = (u16) (number / 10U);
      } while(number != 0 && digit_count < sizeof(digits));
      while(digit_count != 0) output[length++] = digits[--digit_count];
      output[length++] = '.';
      output[length++] = ' ';
    } else {
      output[length++] = '-';
      output[length++] = ' ';
    }
    if(block.task != TaskState::NONE) {
      output[length++] = '[';
      output[length++] =
          block.task == TaskState::CHECKED ? 'x' : ' ';
      output[length++] = ']';
      output[length++] = ' ';
    }
    output[length] = 0;
    return length;
  }

  void draw_line_decorations(u16 line_y) {
    if(block.kind == BlockKind::QUOTE) {
      const u8 depth = block.level == 0 ? 1 : block.level;
      for(u8 index = 0; index < depth && index < 3; index++) {
        vline((i16) (base_margin() + index * (compact ? 2U : 4U)),
              (i16) line_y, line_height);
      }
    }
    if(block.kind == BlockKind::LIST_ITEM && first_visual_line) {
      char prefix[16];
      list_prefix(prefix);
      const u8 indent = compact
          ? (block.level > 3 ? 12U : (u8) (block.level * 4U))
          : (block.level > 3 ? 24U : (u8) (block.level * 8U));
      draw_ascii(prefix, (i16) (base_margin() + indent), (i16) line_y,
                 STYLE_NONE, face);
    }
  }

  void note_link(u16 link, u16 line_y) {
    if(links == nullptr || link == NO_LINK) return;
    const u16 bottom = (u16) (line_y + line_height);
    const bool visible = line_y < (u16) (viewport_top + viewport_height) &&
                         bottom > viewport_top;
    if(visible && links->first_visible == NO_LINK) {
      links->first_visible = link;
    }
    if(visible) links->last_visible = link;
    if(link != selected_link) return;
    if(!links->selected_seen) {
      links->selected_top = line_y;
      links->selected_bottom = bottom;
      links->selected_seen = true;
    } else {
      if(line_y < links->selected_top) links->selected_top = line_y;
      if(bottom > links->selected_bottom) links->selected_bottom = bottom;
    }
    links->selected_visible = links->selected_visible || visible;
  }

  void render_cells(u8 count) {
    record_anchor(y);
    draw_line_decorations(y);
    i16 x = content_x;
    for(u8 index = 0; index < count; index++) {
      note_link(cells[index].link, y);
      const u8 glyph_style = link_is_selected(cells[index].link, selected_link)
          ? (u8) (cells[index].style | STYLE_SELECTED)
          : cells[index].style;
      draw_glyph(cells[index].codepoint, glyph_style, x, (i16) y,
                 face, scale);
      x = (i16) (x + cells[index].advance);
    }
    y = (u16) (y + line_pitch);
    first_visual_line = false;
  }

  void remove_front(u8 count) {
    if(count >= cell_count) {
      cell_count = 0;
      cell_width = 0;
      return;
    }
    memmove(cells, cells + count,
            (usize) (cell_count - count) * sizeof(cells[0]));
    cell_count = (u8) (cell_count - count);
    cell_width = 0;
    for(u8 index = 0; index < cell_count; index++) {
      cell_width = (u16) (cell_width + cells[index].advance);
    }
  }

  void wrap_if_needed(void) {
    while(cell_width > available_width && cell_count != 0) {
      i16 space = -1;
      for(u8 index = 0; index < cell_count; index++) {
        if(cells[index].codepoint == ' ') space = index;
      }
      if(space > 0) {
        render_cells((u8) space);
        remove_front((u8) (space + 1));
      } else if(cell_count > 1) {
        const GlyphCell last = cells[cell_count - 1U];
        cell_count--;
        cell_width = (u16) (cell_width - last.advance);
        render_cells(cell_count);
        cell_count = 1;
        cells[0] = last;
        cell_width = last.advance;
      } else {
        render_cells(1);
        remove_front(1);
      }
    }
  }

  void append_codepoint(u16 codepoint) {
    if(codepoint == '\r') return;
    if(codepoint == '\n') {
      flush_line(true);
      return;
    }
    if(codepoint == '\t') {
      for(u8 count = 0; count < 2; count++) append_codepoint(' ');
      return;
    }
    if(codepoint == ' ' && cell_count == 0) return;
    if(cell_count >= MAX_LINE_CELLS) {
      render_cells(cell_count);
      remove_front(cell_count);
    }
    const u8 effective_style =
        block.kind == BlockKind::HEADING && block.level <= 6
            ? (u8) (style | STYLE_BOLD)
            : style;
    cells[cell_count++] = {
      codepoint,
      effective_style,
      text_advance(codepoint, effective_style, face, scale),
      current_link
    };
    cell_width = (u16) (cell_width + cells[cell_count - 1U].advance);
    wrap_if_needed();
  }

  static u16 decode_m8(const u8* data, u16 length,
                       u16 offset, u16& next) {
    if(data == nullptr || offset >= length) {
      next = length;
      return '?';
    }
    next = (u16) (offset + 1U);
    return mk8::valid_byte(data[offset]) ? mk8::codepoint(data[offset]) : '?';
  }

  void append_text(const u8* text, u16 length) {
    u16 offset = 0;
    while(offset < length) {
      u16 next = offset;
      const u16 codepoint = decode_m8(text, length, offset, next);
      append_codepoint(codepoint);
      offset = next;
    }
  }

  void flush_line(bool force) {
    if(cell_count != 0) {
      while(cell_count != 0 && cells[cell_count - 1U].codepoint == ' ') {
        cell_width = (u16) (cell_width -
                            cells[cell_count - 1U].advance);
        cell_count--;
      }
      if(cell_count != 0) render_cells(cell_count);
      remove_front(cell_count);
    } else if(force) {
      record_anchor(y);
      draw_line_decorations(y);
      y = (u16) (y + line_pitch);
      first_visual_line = false;
    }
  }

  bool image_path(const markdown::Event& event,
                  char* output, u16 capacity) const {
    if(output == nullptr || capacity == 0 || event.path_len == 0 ||
       event.path_len >= capacity) return false;
    memcpy(output, event.path, event.path_len);
    output[event.path_len] = 0;
    return true;
  }

  static void fit_image(const wbmp::Info& info, u16 maximum_width,
                        u16 maximum_height, u16& width, u16& height) {
    width = info.width > maximum_width ? maximum_width : (u16) info.width;
    height = info.width > maximum_width
        ? (u16) (((u64) info.height * maximum_width + info.width - 1U) /
                 info.width)
        : (u16) (info.height > 0xFFFFU ? 0xFFFFU : info.height);
    if(height > maximum_height) {
      width = (u16) (((u64) width * maximum_height + height - 1U) /
                     height);
      height = maximum_height;
    }
    if(width == 0) width = 1;
    if(height == 0) height = 1;
  }

  void draw_missing_image(const markdown::Event& event) {
    static constexpr u8 PLACEHOLDER_HEIGHT = 12;
    record_anchor(y);
    rect(content_x, (i16) y, available_width, PLACEHOLDER_HEIGHT);
    i16 x = (i16) (content_x + 3U);
    const i16 max_x = (i16) (content_x + available_width - 3U);
    const u8* label = event.alt_len != 0 ? event.alt : event.path;
    const u16 length = event.alt_len != 0 ? event.alt_len : event.path_len;
    u16 offset = 0;
    while(offset < length && x + 4 <= max_x) {
      u16 next = offset;
      const u16 codepoint = decode_m8(label, length, offset, next);
      draw_glyph(codepoint, STYLE_NONE, x, (i16) (y + 3U),
                 builtin_font::FaceId::FONT_3X5, 1);
      x = (i16) (x + 4);
      offset = next;
    }
    y = (u16) (y + PLACEHOLDER_HEIGHT + 2U);
  }

  void render_image(const markdown::Event& event) {
    flush_line(false);
    char path[128];
    if(!image_path(event, path, sizeof(path))) {
      draw_missing_image(event);
      return;
    }
    typename Platform::Image image_file(ui_font_source, parent_id, path);
    const u16 length = image_file.size();
    wbmp::Info info = {};
    if(!image_file.ok() ||
       wbmp::inspect(image_file.data(), length, info) != wbmp::Status::OK) {
      draw_missing_image(event);
      return;
    }

    u16 width = 0;
    u16 height = 0;
    fit_image(info, available_width, display_height, width, height);
    record_anchor(y);
    const i16 left = (i16) (content_x +
        (available_width > width ? (available_width - width) / 2U : 0));
    const i32 visible_begin = (i32) y > viewport_top ? y : viewport_top;
    const i32 image_end = (i32) y + height;
    const i32 viewport_end = (i32) viewport_top + viewport_height;
    const i32 visible_end = image_end < viewport_end
        ? image_end : viewport_end;
    for(u16 target_y = visible_begin < visible_end
            ? (u16) (visible_begin - y) : height;
        target_y < height && (i32) (y + target_y) < visible_end;
        target_y++) {
      const u32 source_y = (u32) target_y * info.height / height;
      for(u16 target_x = 0; target_x < width; target_x++) {
        const u32 source_x = (u32) target_x * info.width / width;
        if(wbmp::dark_pixel(image_file.data(), length, info,
                            source_x, source_y)) {
          set_global_pixel((i16) (left + target_x),
                           (i16) (y + target_y));
        }
      }
    }
    y = (u16) (y + height + 2U);
    first_visual_line = true;
  }

  void end_block(void) {
    if(!block_open) return;
    flush_line(false);
    if(block.kind == BlockKind::HEADING && block.level == 2) {
      hline(base_margin(), (i16) y, width_from(base_margin()));
      y = (u16) (y + (compact ? 0U : 2U));
    } else if(block.kind == BlockKind::CODE) {
      const i16 height = (i16) (y - block_start_y);
      rect(base_margin(), (i16) block_start_y,
           width_from(base_margin()),
           height == 0 ? 7 : height);
      y = (u16) (y + (compact ? 0U : 2U));
    } else if(block.kind == BlockKind::HEADING) {
      y = (u16) (y + (compact ? 0U : 2U));
    } else if(block.kind == BlockKind::PARAGRAPH ||
              block.kind == BlockKind::QUOTE) {
      y = (u16) (y + (compact ? 0U : 2U));
    } else if(block.kind == BlockKind::LIST_ITEM) {
      y = (u16) (y + (compact ? 0U : 1U));
    }
    block_open = false;
    style = STYLE_NONE;
  }
};

} // namespace markdown_graphics
#endif
