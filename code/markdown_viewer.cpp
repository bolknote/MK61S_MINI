#include "config.h"

#if MK61_MARKDOWN_VIEWER_IS_BUILTIN || defined(MK61_BUILD_MARKDOWN_MODULE)

#include "markdown_viewer.hpp"

#include "cross_hal.h"
#include "keyboard.h"
#include "language_workspace.hpp"
#include "lcd_ru.hpp"
#include "markdown_document.hpp"
#include "shared_scratch.hpp"
#include "utf8_view.hpp"

#if MK61_HAS_COMPILED_GRAPHICS
  #include "builtin_font.hpp"
  #include "fmk_font.hpp"
  #include "storage_path.hpp"
  #include "wbmp.hpp"
#endif

#include <stdio.h>
#include <string.h>

extern void idle_main_process(void);

namespace markdown_viewer {
namespace {

static constexpr u16 DISPLAY_WIDTH = 192;
static constexpr u8 DISPLAY_HEIGHT = 64;
static constexpr usize FRAME_BYTES =
    (usize) DISPLAY_WIDTH * DISPLAY_HEIGHT / 8U;
static constexpr u16 PLAIN_CAPACITY = 2048;
static constexpr i32 VIEWER_DISPLAY_CHANGED = -2;
static constexpr i32 VIEWER_KEY_NONE = -1;

union OutputBuffer {
  u8 frame[FRAME_BYTES];
  char plain[PLAIN_CAPACITY];
};

struct ViewerWorkspace {
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  OutputBuffer output;
};

static_assert(sizeof(ViewerWorkspace) <= language_workspace::SIZE,
              "Markdown viewer must fit the shared runtime workspace");

struct Navigation {
  u16 page;
};

static i32 scan_key(void) {
  const i32 scan_code = kbd::scan_and_debounced();
  if(scan_code < 0) return VIEWER_KEY_NONE;
  kbd::exclude_before(scan_code);
  if((scan_code & (i32) key_state::RELEASED) != 0) {
    return VIEWER_KEY_NONE;
  }
  return scan_code & ~(i32) key_state::RELEASED;
}

static i32 wait_key(MK61Display& display, u32 display_revision) {
  kbd::debounce_init();
  while(true) {
    idle_main_process();
    if(display.displayModeRevision() != display_revision) {
      return VIEWER_DISPLAY_CHANGED;
    }
    const i32 key = scan_key();
    if(key >= 0) return key;
    delay(10);
  }
}

static bool forward_key(i32 key) {
  return key == KEY_RIGHT || key == KEY_RIGHT_PRESS ||
         key == KEY_SHG_RIGHT_PRESS;
}

static bool backward_key(i32 key) {
  return key == KEY_LEFT || key == KEY_LEFT_PRESS ||
         key == KEY_SHG_LEFT_PRESS;
}

static bool exit_key(i32 key) {
  return key == KEY_ESC || key == KEY_OK || key == KEY_OK_PRESS;
}

struct PlainLine {
  u16 begin;
  u16 end;
  u16 next;
};

static bool plain_space(u8 value) {
  return value == ' ' || value == '\t';
}

static PlainLine plain_line(const u8* data, u16 len, u16 offset) {
  PlainLine line = {offset, offset, offset};
  if(offset >= len) return line;
  if(data[offset] == '\n' || data[offset] == '\r') {
    line.next = (u16) (offset + 1U);
    if(data[offset] == '\r' && line.next < len &&
       data[line.next] == '\n') line.next++;
    return line;
  }

  u16 cursor = offset;
  u16 last_space = offset;
  bool has_space = false;
  u8 used = 0;
  while(cursor < len && data[cursor] != '\n' && data[cursor] != '\r' &&
        used < lcd_display::COLS) {
    const u16 next = utf8_view::next_offset(data, len, cursor);
    if(next <= cursor) break;
    if(next == cursor + 1U && plain_space(data[cursor])) {
      last_space = cursor;
      has_space = true;
    }
    cursor = next;
    used++;
  }

  if(cursor < len && data[cursor] != '\n' && data[cursor] != '\r' &&
     has_space && last_space > offset) {
    line.end = last_space;
    line.next = (u16) (last_space + 1U);
    while(line.next < len && plain_space(data[line.next])) line.next++;
    return line;
  }

  line.end = cursor;
  line.next = cursor;
  if(line.next < len && data[line.next] == '\r') {
    line.next++;
    if(line.next < len && data[line.next] == '\n') line.next++;
  } else if(line.next < len && data[line.next] == '\n') {
    line.next++;
  }
  return line;
}

static u16 plain_line_count(const u8* data, u16 len) {
  if(len == 0) return 1;
  u16 count = 0;
  u16 offset = 0;
  while(offset < len) {
    count++;
    const PlainLine line = plain_line(data, len, offset);
    if(line.next <= offset) break;
    offset = line.next;
  }
  return count == 0 ? 1 : count;
}

static u16 plain_line_offset(const u8* data, u16 len, u16 index) {
  u16 offset = 0;
  while(index != 0 && offset < len) {
    const PlainLine line = plain_line(data, len, offset);
    if(line.next <= offset) break;
    offset = line.next;
    index--;
  }
  return offset;
}

static void copy_plain_line(const u8* data, u16 len, u16 index,
                            char* output, u16 capacity) {
  if(output == nullptr || capacity == 0) return;
  output[0] = 0;
  const u16 offset = plain_line_offset(data, len, index);
  if(offset >= len) return;
  const PlainLine line = plain_line(data, len, offset);
  const u16 bytes = (u16) (line.end - line.begin);
  const u16 copied = bytes < capacity - 1U ? bytes
                                           : (u16) (capacity - 1U);
  if(copied != 0) memcpy(output, data + line.begin, copied);
  output[copied] = 0;
}

static void draw_plain_page(MK61Display& display, const u8* data, u16 len,
                            u16 top_line) {
  static constexpr u16 ROW_BYTES = lcd_display::COLS * 4U + 1U;
  char rows[lcd_display::RUNTIME_MAX_ROWS][ROW_BYTES];
  const u8 row_count = display.rows();
  for(u8 row = 0; row < row_count; row++) {
    copy_plain_line(data, len, (u16) (top_line + row),
                    rows[row], sizeof(rows[row]));
  }

  lcd_ru::font_map_t map = {{0}, 0, false};
  for(u8 row = 0; row < row_count; row++) {
    lcd_ru::scan_text(map, rows[row], lcd_display::COLS);
  }

  MK61DisplayUpdate update(display);
  display.clear();
  lcd_ru::load_custom_font(map);
  for(u8 row = 0; row < row_count; row++) {
    display.setCursor(0, row);
    lcd_ru::write_text(map, rows[row], lcd_display::COLS);
  }
}

static Result view_plain(MK61Display& display, ViewerWorkspace& workspace,
                         u16 compiled_size, Navigation& navigation,
                         bool& display_changed) {
  display_changed = false;
  u16 plain_size = 0;
  const markdown::Status plain_status = markdown::to_plain_text(
      workspace.compiled, compiled_size, workspace.output.plain,
      sizeof(workspace.output.plain), plain_size);
  if(plain_status != markdown::Status::OK) return Result::INVALID_DOCUMENT;

  const u8 rows = display.rows() == 0 ? 1 : display.rows();
  const u16 total_lines = plain_line_count(
      (const u8*) workspace.output.plain, plain_size);
  const u16 page_count =
      (u16) ((total_lines + rows - 1U) / rows);
  if(navigation.page >= page_count) {
    navigation.page = page_count == 0 ? 0 : (u16) (page_count - 1U);
  }

  while(true) {
    const u32 revision = display.displayModeRevision();
    draw_plain_page(display, (const u8*) workspace.output.plain, plain_size,
                    (u16) (navigation.page * rows));
    const i32 key = wait_key(display, revision);
    if(key == VIEWER_DISPLAY_CHANGED) {
      display_changed = true;
      return Result::OK;
    }
    if(exit_key(key)) return Result::OK;
    if(forward_key(key) && navigation.page + 1U < page_count) {
      navigation.page++;
    } else if(backward_key(key) && navigation.page != 0) {
      navigation.page--;
    }
  }
}

#if MK61_HAS_COMPILED_GRAPHICS

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

static void set_frame_pixel(u8* frame, i16 x, i16 y, bool dark) {
  if(frame == nullptr || x < 0 || x >= (i16) DISPLAY_WIDTH ||
     y < 0 || y >= (i16) DISPLAY_HEIGHT) return;
  const usize offset = (usize) (y / 8) * DISPLAY_WIDTH + (u16) x;
  const u8 mask = (u8) (1U << (y & 7));
  if(dark) frame[offset] |= mask;
  else frame[offset] &= (u8) ~mask;
}

struct GlyphCell {
  u16 codepoint;
  u8 style;
  u8 advance;
};

class GraphicLayout {
 public:
  GraphicLayout(u8* frame, u16 viewport_top, u16 parent_id)
      : frame(frame), viewport_top(viewport_top), parent_id(parent_id),
        y(2), block_start_y(2), content_x(2), available_width(188),
        line_height(8), line_pitch(10), scale(1),
        face(builtin_font::FaceId::FONT_5X8), cell_count(0),
        cell_width(0), first_visual_line(true), style(STYLE_NONE),
        block({BlockKind::PARAGRAPH, 0, ListKind::NONE,
               TaskState::NONE, 0}), block_open(false),
        stream_valid(true) {
    memset(frame, 0, FRAME_BYTES);
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
  u16 viewport_top;
  u16 parent_id;
  u16 y;
  u16 block_start_y;
  u8 content_x;
  u8 available_width;
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

  static u8 glyph_advance(builtin_font::FaceId face, u8 scale) {
    return (u8) ((face == builtin_font::FaceId::FONT_3X5 ? 4U : 6U) *
                 scale);
  }

  void set_global_pixel(i16 x, i16 global_y, bool dark = true) {
    const i32 screen_y = (i32) global_y - viewport_top;
    if(screen_y < 0 || screen_y >= DISPLAY_HEIGHT) return;
    set_frame_pixel(frame, x, (i16) screen_y, dark);
  }

  void hline(i16 x, i16 global_y, i16 width, bool dark = true) {
    for(i16 dx = 0; dx < width; dx++) {
      set_global_pixel((i16) (x + dx), global_y, dark);
    }
  }

  void vline(i16 x, i16 global_y, i16 height, bool dark = true) {
    for(i16 dy = 0; dy < height; dy++) {
      set_global_pixel(x, (i16) (global_y + dy), dark);
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
    for(i16 dy = 0; dy < height; dy++) {
      hline(x, (i16) (global_y + dy), width, dark);
    }
  }

  void draw_glyph(u16 codepoint, u8 glyph_style,
                  i16 x, i16 global_y,
                  builtin_font::FaceId selected_face, u8 selected_scale) {
    builtin_font::Raster raster = {};
    if(!builtin_font::decode(selected_face, codepoint, raster) &&
       !builtin_font::decode(selected_face, '?', raster)) return;

    const u8 advance = glyph_advance(selected_face, selected_scale);
    const i16 height = (i16) raster.height * selected_scale;
    const bool inverse = (glyph_style & STYLE_CODE) != 0;
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
            const i16 px = (i16) (x + italic_shift * selected_scale +
                                  source_x * selected_scale + sx);
            const i16 py = (i16) (global_y +
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
    const u8 advance = glyph_advance(selected_face, 1);
    while(*text != 0) {
      draw_glyph((u8) *text++, glyph_style, x, global_y,
                 selected_face, 1);
      x = (i16) (x + advance);
    }
  }

  void configure_block(void) {
    content_x = 2;
    available_width = 188;
    face = builtin_font::FaceId::FONT_5X8;
    scale = 1;
    line_height = 8;
    line_pitch = 10;

    if(block.kind == BlockKind::HEADING) {
      if(block.level == 1) {
        scale = 2;
        line_height = 16;
        line_pitch = 18;
      }
    } else if(block.kind == BlockKind::CODE) {
      face = builtin_font::FaceId::FONT_3X5;
      line_height = 5;
      line_pitch = 6;
      content_x = 5;
      available_width = 182;
    } else if(block.kind == BlockKind::QUOTE) {
      const u8 depth = block.level == 0 ? 1 : block.level;
      const u8 margin = depth > 3 ? 12 : (u8) (depth * 4U);
      content_x = (u8) (2U + margin);
      available_width = (u8) (188U - margin);
    } else if(block.kind == BlockKind::LIST_ITEM) {
      char prefix[16];
      const u8 prefix_length = list_prefix(prefix);
      const u8 indent = block.level > 3 ? 24 : (u8) (block.level * 8U);
      const u8 prefix_width = (u8) (prefix_length * 6U);
      content_x = (u8) (2U + indent + prefix_width);
      available_width = content_x < 190
          ? (u8) (190U - content_x) : 1;
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
      hline(4, (i16) (y + 2U), 184);
      y = (u16) (y + 5U);
    } else if(block.kind == BlockKind::BLANK) {
      y = (u16) (y + 4U);
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
        vline((i16) (2 + index * 4), (i16) line_y, line_height);
      }
    }
    if(block.kind == BlockKind::LIST_ITEM && first_visual_line) {
      char prefix[16];
      list_prefix(prefix);
      const u8 indent = block.level > 3 ? 24 : (u8) (block.level * 8U);
      draw_ascii(prefix, (i16) (2U + indent), (i16) line_y,
                 STYLE_NONE);
    }
  }

  void render_cells(u8 count) {
    draw_line_decorations(y);
    i16 x = content_x;
    for(u8 index = 0; index < count; index++) {
      draw_glyph(cells[index].codepoint, cells[index].style, x, (i16) y,
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
      glyph_advance(face, scale)
    };
    cell_width = (u16) (cell_width + cells[cell_count - 1U].advance);
    wrap_if_needed();
  }

  static u16 decode_utf8(const u8* data, u16 length,
                         u16 offset, u16& next) {
    next = utf8_view::next_offset(data, length, offset);
    if(next <= offset) {
      next = (u16) (offset + 1U);
      return '?';
    }
    const u8 bytes = (u8) (next - offset);
    if(bytes == 1) return data[offset] >= 0x20 || data[offset] == '\t'
        ? data[offset] : (u16) '?';
    if(bytes == 2) {
      return (u16) (((data[offset] & 0x1FU) << 6) |
                    (data[offset + 1] & 0x3FU));
    }
    if(bytes == 3) {
      return (u16) (((data[offset] & 0x0FU) << 12) |
                    ((data[offset + 1] & 0x3FU) << 6) |
                    (data[offset + 2] & 0x3FU));
    }
    return '?';
  }

  void append_text(const u8* text, u16 length) {
    u16 offset = 0;
    while(offset < length) {
      u16 next = offset;
      const u16 codepoint = decode_utf8(text, length, offset, next);
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
                        u16& width, u16& height) {
    width = info.width > maximum_width ? maximum_width : (u16) info.width;
    height = info.width > maximum_width
        ? (u16) (((u64) info.height * maximum_width + info.width - 1U) /
                 info.width)
        : (u16) (info.height > 0xFFFFU ? 0xFFFFU : info.height);
    if(height > DISPLAY_HEIGHT) {
      width = (u16) (((u64) width * DISPLAY_HEIGHT + height - 1U) /
                     height);
      height = DISPLAY_HEIGHT;
    }
    if(width == 0) width = 1;
    if(height == 0) height = 1;
  }

  void draw_missing_image(const markdown::Event& event) {
    static constexpr u8 PLACEHOLDER_HEIGHT = 12;
    rect(content_x, (i16) y, available_width, PLACEHOLDER_HEIGHT);
    i16 x = (i16) (content_x + 3U);
    const i16 max_x = (i16) (content_x + available_width - 3U);
    const u8* label = event.alt_len != 0 ? event.alt : event.path;
    const u16 length = event.alt_len != 0 ? event.alt_len : event.path_len;
    u16 offset = 0;
    while(offset < length && x + 4 <= max_x) {
      u16 next = offset;
      const u16 codepoint = decode_utf8(label, length, offset, next);
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
    program_store::Entry image_entry = {};
    if(storage_path::resolve_file(parent_id, path,
                                  program_store::ProgramType::IMAGE1,
                                  image_entry) != storage_path::Status::OK ||
       image_entry.data_len == 0 ||
       image_entry.data_len > program_store::MAX_IMAGE1_SIZE) {
      draw_missing_image(event);
      return;
    }

    shared_scratch::Lease image_file(
        shared_scratch::Owner::MARKDOWN_VIEWER,
        program_store::MAX_IMAGE1_SIZE);
    u16 length = 0;
    if(!image_file.ok() ||
       !program_store::read_id(image_entry.id, image_file.data(),
                               image_entry.data_len, &length) ||
       length != image_entry.data_len) {
      draw_missing_image(event);
      return;
    }
    wbmp::Info info = {};
    if(wbmp::inspect(image_file.data(), length, info) != wbmp::Status::OK) {
      draw_missing_image(event);
      return;
    }

    u16 width = 0;
    u16 height = 0;
    fit_image(info, available_width, width, height);
    const i16 left = (i16) (content_x +
        (available_width > width ? (available_width - width) / 2U : 0));
    for(u16 target_y = 0; target_y < height; target_y++) {
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
      hline(2, (i16) y, 188);
      y = (u16) (y + 2U);
    } else if(block.kind == BlockKind::CODE) {
      const i16 height = (i16) (y - block_start_y);
      rect(2, (i16) block_start_y, 188, height == 0 ? 7 : height);
      y = (u16) (y + 2U);
    } else if(block.kind == BlockKind::HEADING) {
      y = (u16) (y + 2U);
    } else if(block.kind == BlockKind::PARAGRAPH ||
              block.kind == BlockKind::QUOTE) {
      y = (u16) (y + 2U);
    } else if(block.kind == BlockKind::LIST_ITEM) {
      y = (u16) (y + 1U);
    }
    block_open = false;
    style = STYLE_NONE;
  }
};

static Result render_graphic_page(MK61Display& display,
                                  ViewerWorkspace& workspace,
                                  u16 compiled_size, u16 parent_id,
                                  u16 viewport_top,
                                  u16& document_height) {
  GraphicLayout layout(workspace.output.frame, viewport_top, parent_id);
  document_height = layout.render(workspace.compiled, compiled_size);
  if(!layout.valid()) return Result::INVALID_DOCUMENT;
  return display.showFullscreenBitmap(workspace.output.frame, FRAME_BYTES)
      ? Result::OK : Result::DISPLAY_ERROR;
}

static Result view_graphics(MK61Display& display, ViewerWorkspace& workspace,
                            u16 compiled_size, u16 parent_id,
                            Navigation& navigation,
                            bool& display_changed) {
  display_changed = false;
  if(!display.beginFullscreenBitmap()) return Result::DISPLAY_ERROR;
  bool fullscreen = true;
  Result result = Result::OK;
  while(true) {
    const u32 revision = display.displayModeRevision();
    u16 document_height = 1;
    const u32 requested_top = (u32) navigation.page * DISPLAY_HEIGHT;
    const u16 viewport_top = requested_top > 0xFFFFU
        ? 0xFFFFU : (u16) requested_top;
    result = render_graphic_page(display, workspace, compiled_size,
                                 parent_id, viewport_top, document_height);
    if(result != Result::OK) {
      if(display.displayModeRevision() != revision) {
        display_changed = true;
        result = Result::OK;
      }
      break;
    }
    const u16 page_count = (u16) (
        (document_height + DISPLAY_HEIGHT - 1U) / DISPLAY_HEIGHT);
    if(navigation.page >= page_count) {
      navigation.page = page_count == 0 ? 0 : (u16) (page_count - 1U);
      continue;
    }

    const i32 key = wait_key(display, revision);
    if(key == VIEWER_DISPLAY_CHANGED) {
      display_changed = true;
      break;
    }
    if(exit_key(key)) break;
    if(forward_key(key) && navigation.page + 1U < page_count) {
      navigation.page++;
    } else if(backward_key(key) && navigation.page != 0) {
      navigation.page--;
    }
  }
  if(fullscreen) display.endFullscreenBitmap();
  return result;
}

#endif // MK61_HAS_COMPILED_GRAPHICS

} // namespace

Result view_entry(MK61Display& display,
                  const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::MARKDOWN ||
     entry.data_len > program_store::MAX_MK61_TEXT_SIZE) {
    return Result::INVALID_DOCUMENT;
  }

  language_workspace::Lease workspace_lease(
      language_workspace::Owner::MARKDOWN_VIEWER,
      sizeof(ViewerWorkspace));
  if(!workspace_lease.ok()) return Result::BUSY;
  ViewerWorkspace& workspace =
      *(ViewerWorkspace*) workspace_lease.data();

  shared_scratch::Lease source(
      shared_scratch::Owner::MARKDOWN_VIEWER,
      program_store::MAX_MK61_TEXT_SIZE);
  if(!source.ok()) return Result::BUSY;
  u16 source_size = 0;
  if(!program_store::read_id(entry.id, source.data(), entry.data_len,
                             &source_size) ||
     source_size != entry.data_len) {
    return Result::READ_ERROR;
  }

  u16 compiled_size = 0;
  const markdown::Status status = markdown::compile(
      source.data(), source_size, workspace.compiled,
      sizeof(workspace.compiled), compiled_size);
  source.reset();
  if(status != markdown::Status::OK) return Result::INVALID_DOCUMENT;

  Navigation navigation = {0};
  while(true) {
    bool display_changed = false;
    Result result = Result::OK;
#if MK61_HAS_COMPILED_GRAPHICS
    if(display.graphicsMode()) {
      result = view_graphics(display, workspace, compiled_size,
                             entry.parent_id, navigation, display_changed);
    } else
#endif
    {
      result = view_plain(display, workspace, compiled_size,
                          navigation, display_changed);
    }
    if(result != Result::OK || !display_changed) return result;
  }
}

const char* result_text(Result result) {
  switch(result) {
    case Result::OK: return "ok";
    case Result::BUSY: return "workspace busy";
    case Result::READ_ERROR: return "read error";
    case Result::INVALID_DOCUMENT: return "invalid Markdown";
    case Result::DISPLAY_ERROR: return "display error";
  }
  return "unknown Markdown viewer error";
}

} // namespace markdown_viewer

#endif
