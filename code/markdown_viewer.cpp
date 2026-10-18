#include "config.h"

#if MK61_MARKDOWN_VIEWER_IS_BUILTIN || defined(MK61_BUILD_MARKDOWN_MODULE)

#include "markdown_viewer.hpp"

#include "cross_hal.h"
#include "keyboard.h"
#include "language_workspace.hpp"
#include "lcd_ru.hpp"
#include "m8_view.hpp"
#include "markdown_document.hpp"
#include "mk8_codec.hpp"
#include "shared_scratch.hpp"
#include "storage_path.hpp"

#if MK61_MARKDOWN_USES_WBMP
  #include "builtin_font.hpp"
  #include "fmk_font.hpp"
  #include "markdown_scroll.hpp"
  #include "markdown_graphic_layout.hpp"
  #include "wbmp.hpp"
  #if MK61_UI_FONT_CLIENT
    #include "markdown_ui_font.hpp"
  #endif
#endif

#include <stdio.h>
#include <string.h>

extern void idle_main_process(void);

namespace markdown_viewer {
namespace {

static constexpr i32 VIEWER_DISPLAY_CHANGED = -2;
static constexpr i32 VIEWER_KEY_NONE = -1;
static constexpr u16 PLAIN_CAPACITY = 2048;
static constexpr u16 NO_LINK = 0xFFFFU;

static constexpr bool link_is_selected(u16 link, u16 selected_link) {
  return selected_link != NO_LINK && link == selected_link;
}

static_assert(!link_is_selected(NO_LINK, NO_LINK),
              "no link selection must leave ordinary text unchanged");
static_assert(link_is_selected(0, 0),
              "an explicitly selected link must be highlighted");

#if MK61_MARKDOWN_USES_WBMP

static constexpr u16 MAX_DISPLAY_WIDTH = 192;
static constexpr u8 MAX_DISPLAY_HEIGHT = 64;
static constexpr usize MAX_FRAME_BYTES =
    (usize) MAX_DISPLAY_WIDTH * MAX_DISPLAY_HEIGHT / 8U;
static constexpr u8 SCROLL_CACHE_ROWS = 16;
static constexpr usize MAX_SCROLL_CACHE_BYTES =
    (usize) MAX_DISPLAY_WIDTH * SCROLL_CACHE_ROWS / 8U;
struct GraphicBuffers {
  u8 frame[MAX_FRAME_BYTES];
  u8 incoming[MAX_SCROLL_CACHE_BYTES];
};

union OutputBuffer {
  GraphicBuffers graphics;
  char plain[PLAIN_CAPACITY];
};

struct ViewerWorkspace {
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  OutputBuffer output;
};

static_assert(sizeof(GraphicBuffers) <= PLAIN_CAPACITY,
              "Markdown scroll cache must fit the output overlay");

#else

struct ViewerWorkspace {
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  char plain[PLAIN_CAPACITY];
};

#endif

static_assert(sizeof(ViewerWorkspace) <= language_workspace::SIZE,
              "Markdown viewer must fit the shared runtime workspace");

struct Navigation {
  u16 plain_page;
  u16 graphic_y;
  u16 selected_link;
};

static i32 scan_key(void) {
  const i32 scan_code = kbd::poll_event().code();
  if(scan_code < 0) return VIEWER_KEY_NONE;

  if((scan_code & (i32) key_state::RELEASED) != 0) {
    return VIEWER_KEY_NONE;
  }
  kbd::handoff(kbd::Event(scan_code));
  return scan_code & ~(i32) key_state::RELEASED;
}

static i32 wait_key(MK61Display& display, u32 display_revision) {

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

#if MK61_MARKDOWN_USES_WBMP
static bool line_forward_key(i32 key) {
  return key == KEY_RIGHT || key == KEY_RIGHT_PRESS;
}

static bool line_backward_key(i32 key) {
  return key == KEY_LEFT || key == KEY_LEFT_PRESS;
}

static bool fast_forward_key(i32 key) {
  return key == KEY_SHG_RIGHT_PRESS;
}

static bool fast_backward_key(i32 key) {
  return key == KEY_SHG_LEFT_PRESS;
}
#endif

static bool exit_key(i32 key) {
  return key == KEY_ESC;
}

// Arrows form one continuous navigation sequence.  A visible link consumes
// a step; stepping past the last/first visible link clears the selection and
// lets the caller continue ordinary document scrolling in the same direction.
static bool step_visible_links(u16& selected, u16 first, u16 last,
                               bool forward) {
  if(first == NO_LINK || last == NO_LINK) {
    selected = NO_LINK;
    return false;
  }
  if(selected == NO_LINK) {
    selected = forward ? first : last;
    return true;
  }
  if(forward && selected < last) {
    selected++;
    return true;
  }
  if(!forward && selected > first) {
    selected--;
    return true;
  }
  selected = NO_LINK;
  return false;
}

static bool compiled_link_path(const u8* compiled, u16 compiled_size,
                               u16 selected, char* output,
                               usize capacity) {
  if(compiled == nullptr || output == nullptr || capacity == 0) return false;
  markdown::Reader reader(compiled, compiled_size);
  u16 index = 0;
  while(true) {
    markdown::Event event = {};
    if(reader.next(event) != markdown::Status::OK) return false;
    if(event.kind == markdown::EventKind::END) return false;
    if(event.kind != markdown::EventKind::LINK_BEGIN) continue;
    if(index++ != selected) continue;
    if(event.path_len == 0 || event.path_len >= capacity) return false;
    u16 length = 0;
    while(length < event.path_len && event.path[length] != '#') {
      if(event.path[length] == 0) return false;
      output[length] = (char) event.path[length];
      length++;
    }
    output[length] = 0;
    return length != 0;
  }
}

static Result compile_entry(ViewerWorkspace& workspace,
                            const program_store::Entry& entry,
                            u16& compiled_size) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::MARKDOWN ||
     entry.data_len > program_store::MAX_MK61_TEXT_SIZE) {
    return Result::INVALID_DOCUMENT;
  }
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
  compiled_size = 0;
  return markdown::compile(
      source.data(), source_size, workspace.compiled,
      sizeof(workspace.compiled), compiled_size) == markdown::Status::OK
      ? Result::OK : Result::INVALID_DOCUMENT;
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
    const u16 next = m8_view::next_offset(data, len, cursor);
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

static constexpr u16 PLAIN_ROW_BYTES = lcd_display::COLS * 4U + 1U;

static void show_plain_rows(
    MK61Display& display,
    char rows[lcd_display::RUNTIME_MAX_ROWS][PLAIN_ROW_BYTES]) {
  const u8 row_count = display.rows();
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  const char* lines[lcd_display::RUNTIME_MAX_ROWS];
  for(u8 row = 0; row < row_count; ++row) lines[row] = rows[row];
  portable_system::text_rows(lines, row_count);
#else
  lcd_ru::font_map_t map = {};
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
#endif
}

static void draw_plain_page(MK61Display& display, const u8* data, u16 len,
                            u16 top_line) {
  char rows[lcd_display::RUNTIME_MAX_ROWS][PLAIN_ROW_BYTES] = {};
  const u8 row_count = display.rows();
  for(u8 row = 0; row < row_count; row++) {
    copy_plain_line(data, len, (u16) (top_line + row),
                    rows[row], sizeof(rows[row]));
  }
  show_plain_rows(display, rows);
}

static void draw_plain_link(MK61Display& display, const u8* data, u16 len,
                            const markdown::PlainLink& link,
                            u16 selected, u16 link_count) {
  char rows[lcd_display::RUNTIME_MAX_ROWS][PLAIN_ROW_BYTES] = {};
  rows[0][0] = '>';
  rows[0][1] = ' ';
  u16 source = link.begin;
  u16 output = 2;
  u8 cells = 2;
  while(source < link.end && source < len &&
        cells < lcd_display::COLS) {
    const u16 next = m8_view::next_offset(data, len, source);
    if(next <= source || output + next - source >= PLAIN_ROW_BYTES) break;
    memcpy(rows[0] + output, data + source, next - source);
    output = (u16) (output + next - source);
    source = next;
    cells++;
  }
  rows[0][output] = 0;
  if(display.rows() > 1) {
    snprintf(rows[1], sizeof(rows[1]), "%u/%u  OK",
             (unsigned) selected + 1U, (unsigned) link_count);
  }
  show_plain_rows(display, rows);
}

static void plain_visible_links(
    const u8* data, u16 len, const markdown::PlainLink* links,
    u16 link_count, u16 top_line, u8 rows,
    u16& first, u16& last) {
  first = NO_LINK;
  last = NO_LINK;
  u16 line_offset = plain_line_offset(data, len, top_line);
  for(u8 row = 0; row < rows && line_offset < len; row++) {
    const PlainLine line = plain_line(data, len, line_offset);
    for(u16 index = 0; index < link_count; index++) {
      if(links[index].begin < line.end && links[index].end > line.begin) {
        if(first == NO_LINK) first = index;
        last = index;
      }
    }
    if(line.next <= line_offset) break;
    line_offset = line.next;
  }
}

static Result view_plain_text(MK61Display& display,
                              const char* plain, u16 plain_size,
                              const markdown::PlainLink* links,
                              u16 link_count,
                              Navigation& navigation,
                              bool& display_changed, u16& open_link,
                              bool& back_requested) {
  display_changed = false;
  open_link = NO_LINK;
  back_requested = false;
  const u8 rows = display.rows() == 0 ? 1 : display.rows();
  const u16 total_lines = plain_line_count(
      (const u8*) plain, plain_size);
  const u16 page_count =
      (u16) ((total_lines + rows - 1U) / rows);
  if(navigation.plain_page >= page_count) {
    navigation.plain_page = page_count == 0 ? 0 : (u16) (page_count - 1U);
  }

  while(true) {
    u16 first_visible = NO_LINK;
    u16 last_visible = NO_LINK;
    plain_visible_links(
        (const u8*) plain, plain_size, links, link_count,
        (u16) (navigation.plain_page * rows), rows,
        first_visible, last_visible);
    if(navigation.selected_link != NO_LINK &&
       (first_visible == NO_LINK ||
        navigation.selected_link < first_visible ||
        navigation.selected_link > last_visible)) {
      navigation.selected_link = NO_LINK;
    }

    const u32 revision = display.displayModeRevision();
    if(navigation.selected_link != NO_LINK) {
      draw_plain_link(display, (const u8*) plain, plain_size,
                      links[navigation.selected_link],
                      navigation.selected_link, link_count);
    } else {
      draw_plain_page(display, (const u8*) plain, plain_size,
                      (u16) (navigation.plain_page * rows));
    }
    const i32 key = wait_key(display, revision);
    if(key == VIEWER_DISPLAY_CHANGED) {
      display_changed = true;
      return Result::OK;
    }
    if(exit_key(key)) {
      if(navigation.selected_link != NO_LINK) {
        navigation.selected_link = NO_LINK;
        continue;
      }
      back_requested = true;
      return Result::OK;
    }
    if(key == KEY_OK || key == KEY_OK_PRESS) {
      if(navigation.selected_link != NO_LINK) {
        open_link = navigation.selected_link;
      } else {
        back_requested = true;
      }
      return Result::OK;
    }
    if(forward_key(key)) {
      if(step_visible_links(navigation.selected_link,
                            first_visible, last_visible, true)) {
        continue;
      }
      if(navigation.plain_page + 1U < page_count) {
        navigation.plain_page++;
      }
    } else if(backward_key(key)) {
      if(step_visible_links(navigation.selected_link,
                            first_visible, last_visible, false)) {
        continue;
      }
      if(navigation.plain_page != 0) {
        navigation.plain_page--;
      }
    }
  }
}

static Result view_plain(MK61Display& display, ViewerWorkspace& workspace,
                         u16 compiled_size, Navigation& navigation,
                         bool& display_changed, u16& open_link,
                         bool& back_requested) {
  markdown::PlainLink links[markdown::MAX_PLAIN_LINKS];
  u16 link_count = 0;
  u16 plain_size = 0;
  #if MK61_MARKDOWN_USES_WBMP
  char* const plain = workspace.output.plain;
  #else
  char* const plain = workspace.plain;
  #endif
  const markdown::Status status = markdown::to_plain_text_with_links(
      workspace.compiled, compiled_size, plain, PLAIN_CAPACITY, plain_size,
      links, markdown::MAX_PLAIN_LINKS, link_count);
  if(status != markdown::Status::OK) return Result::INVALID_DOCUMENT;
  return view_plain_text(display, plain, plain_size, links, link_count,
                         navigation, display_changed, open_link,
                         back_requested);
}

#if MK61_MARKDOWN_USES_WBMP

using LinkLayout = markdown_graphics::LinkLayout;

// Keep STM32's bounded scratch lease and font service unchanged.
struct GraphicPlatform {
#if MK61_UI_FONT_CLIENT
  markdown_ui_font::Source source;
  bool enabled() const { return source.enabled(); }
  u8 height() const { return source.height(); }
  u8 ascent() const { return source.ascent(); }
  u8 line_gap() const { return source.line_gap(); }
  bool glyph(u16 cp, mk61_service_ui_glyph& out) const { return source.glyph(cp, out); }
#else
  bool enabled() const { return false; }
  u8 height() const { return 0; }
  u8 ascent() const { return 0; }
  u8 line_gap() const { return 0; }
  bool glyph(u16, mk61_service_ui_glyph&) const { return false; }
#endif
  struct Image {
    shared_scratch::Lease bytes;
    u16 length = 0;
    bool valid = false;
    Image(const GraphicPlatform&, u16 parent, const char* path)
        : bytes(shared_scratch::Owner::MARKDOWN_VIEWER, program_store::MAX_IMAGE1_SIZE) {
      program_store::Entry entry = {};
      valid = bytes.ok() &&
          storage_path::resolve_file(parent, path, program_store::ProgramType::IMAGE1,
                                    entry) == storage_path::Status::OK &&
          entry.data_len && entry.data_len <= program_store::MAX_IMAGE1_SIZE &&
          program_store::read_id(entry.id, bytes.data(), entry.data_len, &length) &&
          length == entry.data_len;
    }
    bool ok() const { return valid; }
    const u8* data() { return bytes.data(); }
    u16 size() const { return length; }
  };
};
using GraphicLayout = markdown_graphics::Layout<GraphicPlatform>;

struct GraphicViewport {
  u16 width;
  u8 height;
  u8 pages;
  usize frame_bytes;
};

static bool graphic_viewport(MK61Display& display,
                             GraphicViewport& viewport) {
  const u16 width = display.fullscreenBitmapWidth();
  const u16 height = display.fullscreenBitmapHeight();
  if(width == 0 || width > MAX_DISPLAY_WIDTH || height == 0 ||
     height > MAX_DISPLAY_HEIGHT || (height & 7U) != 0) return false;
  viewport.width = width;
  viewport.height = (u8) height;
  viewport.pages = (u8) (height / 8U);
  viewport.frame_bytes = (usize) width * viewport.pages;
  return viewport.frame_bytes <= MAX_FRAME_BYTES;
}

static Result layout_graphic_region(
    ViewerWorkspace& workspace, u16 compiled_size, u16 parent_id,
    const GraphicViewport& viewport, u8* bitmap,
    u16 region_top, u8 region_height, u16 metrics_top,
    markdown_scroll::Metrics& scroll, u16 selected_link = NO_LINK,
    LinkLayout* links = nullptr) {
  markdown_scroll::Probe probe(metrics_top, viewport.height);
  GraphicLayout layout(
      bitmap, viewport.width, viewport.height,
      region_top, region_height, parent_id, probe,
      selected_link, links);
  const u16 document_height =
      layout.render(workspace.compiled, compiled_size);
  if(!layout.valid()) return Result::INVALID_DOCUMENT;
  scroll = probe.finish(document_height);
  return Result::OK;
}

static Result render_graphic_page(MK61Display& display,
                                  ViewerWorkspace& workspace,
                                  u16 compiled_size, u16 parent_id,
                                  const GraphicViewport& viewport,
                                  u16 viewport_top,
                                  markdown_scroll::Metrics& scroll,
                                  u16 selected_link,
                                  LinkLayout& links) {
  Result result = layout_graphic_region(
      workspace, compiled_size, parent_id, viewport,
      workspace.output.graphics.frame, viewport_top, viewport.height,
      viewport_top, scroll, selected_link, &links);
  if(result != Result::OK) return result;
  return display.showFullscreenBitmap(
      workspace.output.graphics.frame, viewport.frame_bytes)
      ? Result::OK : Result::DISPLAY_ERROR;
}

static Result measure_graphic_page(
    ViewerWorkspace& workspace, u16 compiled_size, u16 parent_id,
    const GraphicViewport& viewport, u16 viewport_top,
    markdown_scroll::Metrics& scroll) {
  return layout_graphic_region(
      workspace, compiled_size, parent_id, viewport, nullptr,
      viewport_top, 0, viewport_top, scroll);
}

static constexpr u16 SCROLL_FRAME_MS = 20;

static Result animate_graphic_scroll(
    MK61Display& display, ViewerWorkspace& workspace,
    u16 compiled_size, u16 parent_id, const GraphicViewport& viewport,
    Navigation& navigation,
    u16 target, u32 display_revision, markdown_scroll::Metrics& scroll,
    bool& display_changed, i32 required_key, bool& key_released) {
  key_released = false;
  while(navigation.graphic_y != target) {
    if(required_key >= 0 && !kbd::is_key_pressed(required_key)) {
      key_released = true;
      return Result::OK;
    }

    const bool forward = navigation.graphic_y < target;
    const u16 remaining = forward
        ? (u16) (target - navigation.graphic_y)
        : (u16) (navigation.graphic_y - target);
    const u8 rows = remaining < SCROLL_CACHE_ROWS
        ? (u8) remaining : SCROLL_CACHE_ROWS;
    const u16 destination = forward
        ? (u16) (navigation.graphic_y + rows)
        : (u16) (navigation.graphic_y - rows);
    const u16 region_top = forward
        ? (u16) (navigation.graphic_y + viewport.height)
        : destination;

    markdown_scroll::Metrics destination_scroll = {};
    idle_main_process();
    Result result = layout_graphic_region(
        workspace, compiled_size, parent_id, viewport,
        workspace.output.graphics.incoming,
        region_top, SCROLL_CACHE_ROWS, destination,
        destination_scroll);
    if(result != Result::OK) {
      if(display.displayModeRevision() == display_revision) return result;
      display_changed = true;
      return Result::OK;
    }
    idle_main_process();
    if(display.displayModeRevision() != display_revision) {
      display_changed = true;
      return Result::OK;
    }

    for(u8 step = 0; step < rows; step++) {
      const u32 frame_started = millis();
      if(forward) {
        markdown_scroll::shift_up_insert_row(
            workspace.output.graphics.frame, viewport.width, viewport.pages,
            workspace.output.graphics.incoming, step);
        navigation.graphic_y++;
      } else {
        const u8 source_row = (u8) (rows - step - 1U);
        markdown_scroll::shift_down_insert_row(
            workspace.output.graphics.frame, viewport.width, viewport.pages,
            workspace.output.graphics.incoming, source_row);
        navigation.graphic_y--;
      }

      if(!display.showFullscreenBitmap(
          workspace.output.graphics.frame, viewport.frame_bytes)) {
        if(display.displayModeRevision() == display_revision) {
          return Result::DISPLAY_ERROR;
        }
        display_changed = true;
        return Result::OK;
      }

      while((u32) (millis() - frame_started) < SCROLL_FRAME_MS) {
        idle_main_process();
        (void) kbd::scan();
        if(display.displayModeRevision() != display_revision) {
          display_changed = true;
          return Result::OK;
        }
        if(required_key >= 0 && !kbd::is_key_pressed(required_key)) {
          key_released = true;
          return Result::OK;
        }
        delay(1);
      }
    }
    scroll = destination_scroll;
  }
  return Result::OK;
}

static Result scroll_line(
    MK61Display& display, ViewerWorkspace& workspace,
    u16 compiled_size, u16 parent_id, const GraphicViewport& viewport,
    Navigation& navigation,
    bool forward, u32 display_revision, markdown_scroll::Metrics& scroll,
    bool& display_changed) {
  const u16 target = forward ? scroll.next_anchor
                             : scroll.previous_anchor;
  bool key_released = false;
  Result result = animate_graphic_scroll(
      display, workspace, compiled_size, parent_id, viewport, navigation,
      target, display_revision, scroll, display_changed,
      VIEWER_KEY_NONE, key_released);
  if(result != Result::OK || display_changed) return result;

  const i32 held_key = forward ? KEY_RIGHT : KEY_LEFT;
  const u16 continuous_start = navigation.graphic_y;
  if(kbd::is_key_pressed(held_key)) {
    const u16 continuous_target = forward ? scroll.maximum_top : 0;
    result = animate_graphic_scroll(
        display, workspace, compiled_size, parent_id, viewport, navigation,
        continuous_target, display_revision, scroll, display_changed,
        held_key, key_released);
    if(result != Result::OK || display_changed) return result;
  }

  const bool continuously_scrolled =
      navigation.graphic_y != continuous_start;
  if(continuously_scrolled) {
    result = measure_graphic_page(
        workspace, compiled_size, parent_id, viewport,
        navigation.graphic_y, scroll);
    if(result != Result::OK) {
      if(display.displayModeRevision() == display_revision) return result;
      display_changed = true;
      return Result::OK;
    }
  }

  if(continuously_scrolled &&
     scroll.snap_anchor != navigation.graphic_y) {
    result = animate_graphic_scroll(
        display, workspace, compiled_size, parent_id, viewport, navigation,
        scroll.snap_anchor, display_revision, scroll, display_changed,
        VIEWER_KEY_NONE, key_released);
  }
  return result;
}

static Result view_graphics(MK61Display& display, ViewerWorkspace& workspace,
                            u16 compiled_size, u16 parent_id,
                            Navigation& navigation,
                            bool& display_changed, u16& open_link,
                            bool& back_requested) {
  display_changed = false;
  open_link = NO_LINK;
  back_requested = false;
  if(!display.beginFullscreenBitmap()) return Result::DISPLAY_ERROR;
  GraphicViewport viewport = {};
  if(!graphic_viewport(display, viewport)) {
    display.endFullscreenBitmap();
    return Result::DISPLAY_ERROR;
  }
  bool fullscreen = true;
  Result result = Result::OK;
  while(true) {
    const u32 revision = display.displayModeRevision();
    markdown_scroll::Metrics scroll = {};
    LinkLayout links = {};
    result = render_graphic_page(
        display, workspace, compiled_size, parent_id,
        viewport, navigation.graphic_y, scroll,
        navigation.selected_link,
        links);
    if(result != Result::OK) {
      if(display.displayModeRevision() != revision) {
        display_changed = true;
        result = Result::OK;
      }
      break;
    }
    if(navigation.graphic_y != scroll.current_top) {
      navigation.graphic_y = scroll.current_top;
      continue;
    }

    if(navigation.selected_link != NO_LINK &&
       (navigation.selected_link >= links.count ||
        !links.selected_visible)) {
      navigation.selected_link = NO_LINK;
      continue;
    }

    const i32 key = wait_key(display, revision);
    if(key == VIEWER_DISPLAY_CHANGED) {
      display_changed = true;
      break;
    }
    if(exit_key(key)) {
      if(navigation.selected_link != NO_LINK) {
        navigation.selected_link = NO_LINK;
        continue;
      }
      back_requested = true;
      break;
    }
    if(key == KEY_OK || key == KEY_OK_PRESS) {
      if(navigation.selected_link < links.count) {
        open_link = navigation.selected_link;
        break;
      }
      back_requested = true;
      break;
    }
    if(line_forward_key(key)) {
      if(step_visible_links(navigation.selected_link,
                            links.first_visible, links.last_visible, true)) {
        continue;
      }
      result = scroll_line(
          display, workspace, compiled_size, parent_id, viewport, navigation,
          true, revision, scroll, display_changed);
      if(result != Result::OK || display_changed) break;
    } else if(line_backward_key(key)) {
      if(step_visible_links(navigation.selected_link,
                            links.first_visible, links.last_visible, false)) {
        continue;
      }
      result = scroll_line(
          display, workspace, compiled_size, parent_id, viewport, navigation,
          false, revision, scroll, display_changed);
      if(result != Result::OK || display_changed) break;
    } else if(fast_forward_key(key)) {
      navigation.selected_link = NO_LINK;
      navigation.graphic_y = scroll.fast_next_anchor;
    } else if(fast_backward_key(key)) {
      navigation.selected_link = NO_LINK;
      navigation.graphic_y = scroll.fast_previous_anchor;
    }
  }
  if(fullscreen) display.endFullscreenBitmap();
  return result;
}

#endif // MK61_MARKDOWN_USES_WBMP

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

  static constexpr u8 HISTORY_DEPTH = 8;
  struct HistoryItem {
    u16 entry_id;
    Navigation navigation;
  };
  HistoryItem history[HISTORY_DEPTH] = {};
  u8 history_depth = 0;
  program_store::Entry current = entry;
  Navigation navigation = {};
  navigation.selected_link = NO_LINK;
  u16 compiled_size = 0;
  Result result = compile_entry(workspace, current, compiled_size);
  if(result != Result::OK) return result;

  while(true) {
    bool display_changed = false;
    u16 open_link = NO_LINK;
    bool back_requested = false;
#if MK61_MARKDOWN_USES_WBMP
    if(display.supportsFullscreenBitmap()) {
      result = view_graphics(display, workspace, compiled_size,
                             current.parent_id, navigation, display_changed,
                             open_link, back_requested);
    } else {
#endif
      result = view_plain(display, workspace, compiled_size,
                          navigation, display_changed, open_link,
                          back_requested);
#if MK61_MARKDOWN_USES_WBMP
    }
#endif
    if(result != Result::OK) return result;
    if(display_changed) continue;

    if(open_link != NO_LINK) {
#if MK61_MARKDOWN_USES_WBMP
      char* const path = workspace.output.plain;
#else
      char* const path = workspace.plain;
#endif
      if(!compiled_link_path(workspace.compiled, compiled_size,
                             open_link, path, PLAIN_CAPACITY)) {
        continue;
      }
      program_store::Entry target = {};
      if(history_depth >= HISTORY_DEPTH ||
         storage_path::resolve_file(
             current.parent_id, path,
             program_store::ProgramType::MARKDOWN,
             target) != storage_path::Status::OK) {
        continue;
      }
      history[history_depth++] = {current.id, navigation};
      current = target;
      navigation = {};
      navigation.selected_link = NO_LINK;
      result = compile_entry(workspace, current, compiled_size);
      if(result != Result::OK) return result;
      continue;
    }

    if(back_requested) {
      if(history_depth == 0) return Result::OK;
      const HistoryItem previous = history[--history_depth];
      if(!program_store::entry_by_id(previous.entry_id, current)) {
        return Result::READ_ERROR;
      }
      navigation = previous.navigation;
      navigation.selected_link = NO_LINK;
      result = compile_entry(workspace, current, compiled_size);
      if(result != Result::OK) return result;
      continue;
    }
    return Result::OK;
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
