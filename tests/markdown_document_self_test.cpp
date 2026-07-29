#include "../code/markdown_document.hpp"
#include "../code/markdown_scroll.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

static void compile_plain(const char* source, char* output, u16 capacity) {
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  u16 compiled_size = 0;
  assert(markdown::compile(
      (const u8*) source, (u16) strlen(source),
      compiled, sizeof(compiled), compiled_size) == markdown::Status::OK);
  u16 output_size = 0;
  assert(markdown::to_plain_text(
      compiled, compiled_size, output, capacity, output_size) ==
      markdown::Status::OK);
  assert(output_size == strlen(output));
}

static void expect_plain(const char* source, const char* expected) {
  char output[2048];
  compile_plain(source, output, sizeof(output));
  if(strcmp(output, expected) != 0) {
    fprintf(stderr, "source:\n%s\nexpected:\n%s\nactual:\n%s\n",
            source, expected, output);
    assert(false);
  }
}

static void test_plain_text_profile(void) {
  expect_plain(
      "# Заголовок\n\n"
      "**жирный**, *курсив*, ~~зачёркнутый~~ и `код`.\n"
      "[ссылка](https://example.test)\n",
      "Заголовок\n"
      "\n"
      "жирный, курсив, зачёркнутый и код. ссылка");

  expect_plain(
      "- первый\n"
      "  - [ ] второй\n"
      "3. [x] третий\n"
      "> цитата\n"
      "---\n",
      "- первый\n"
      "  - [ ] второй\n"
      "3. [x] третий\n"
      "цитата");

  expect_plain(
      "До ![схема](images/scheme.wbmp) после\n"
      "![](../img/photo.wbmp)\n",
      "До схема после photo.wbmp");

  expect_plain(
      "строка один\nстрока два  \nстрока три\n"
      "\n"
      "```\n"
      "  x = 1;\n"
      "  y = 2;\n"
      "```\n",
      "строка один строка два\n"
      "строка три\n"
      "\n"
      "  x = 1;\n"
      "  y = 2;");
}

static void test_heading_forms_and_escapes(void) {
  expect_plain(
      "Setext\n===\n"
      "## ATX ##\n"
      "\\*literal\\* &amp; &lt;x&gt;\n",
      "Setext\n"
      "ATX\n"
      "*literal* & <x>");
}

static void test_event_styles_and_image(void) {
  const char source[] =
      "### **bold _italic_** ~~gone~~ [link](url) "
      "![alt](pic.wbmp)";
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  u16 compiled_size = 0;
  assert(markdown::compile(
      (const u8*) source, sizeof(source) - 1,
      compiled, sizeof(compiled), compiled_size) == markdown::Status::OK);

  markdown::Reader reader(compiled, compiled_size);
  bool heading = false;
  bool bold = false;
  bool italic = false;
  bool strike = false;
  bool link = false;
  bool image = false;
  for(;;) {
    markdown::Event event = {};
    assert(reader.next(event) == markdown::Status::OK);
    if(event.kind == markdown::EventKind::END) break;
    if(event.kind == markdown::EventKind::BLOCK_BEGIN) {
      heading = event.block.kind == markdown::BlockKind::HEADING &&
                event.block.level == 3;
    } else if(event.kind == markdown::EventKind::STYLE) {
      bold = bold || (event.style & markdown::STYLE_BOLD) != 0;
      italic = italic || (event.style & markdown::STYLE_ITALIC) != 0;
      strike = strike || (event.style & markdown::STYLE_STRIKE) != 0;
      link = link || (event.style & markdown::STYLE_LINK) != 0;
    } else if(event.kind == markdown::EventKind::IMAGE) {
      image = event.alt_len == 3 &&
              memcmp(event.alt, "alt", 3) == 0 &&
              event.path_len == 8 &&
              memcmp(event.path, "pic.wbmp", 8) == 0;
    }
  }
  assert(heading && bold && italic && strike && link && image);
}

static void test_bounds_and_malformed_stream(void) {
  static u8 source[markdown::MAX_SOURCE_SIZE + 1];
  memset(source, 'a', sizeof(source));
  u8 compiled[markdown::MAX_COMPILED_SIZE];
  u16 size = 123;
  assert(markdown::compile(source, sizeof(source), compiled,
                           sizeof(compiled), size) ==
         markdown::Status::SOURCE_TOO_LARGE);
  assert(size == 0);

  assert(markdown::compile(source, markdown::MAX_SOURCE_SIZE,
                           compiled, 8, size) ==
         markdown::Status::OUTPUT_TOO_SMALL);

  const u8 bad[] = {4, 5, 0, 'x', 0};
  markdown::Reader reader(bad, sizeof(bad));
  markdown::Event event = {};
  assert(reader.next(event) == markdown::Status::INVALID_STREAM);
}

static void test_adversarial_inline_density_fits(void) {
  char source[markdown::MAX_SOURCE_SIZE + 1];
  u16 used = 0;
  while(used + 4 <= markdown::MAX_SOURCE_SIZE) {
    memcpy(source + used, "*a* ", 4);
    used = (u16) (used + 4);
  }
  source[used] = 0;

  u8 compiled[markdown::MAX_COMPILED_SIZE];
  u16 compiled_size = 0;
  assert(markdown::compile(
      (const u8*) source, used, compiled, sizeof(compiled), compiled_size) ==
      markdown::Status::OK);
  assert(compiled_size <= sizeof(compiled));
}

static void test_adversarial_block_density_fits(void) {
  char source[markdown::MAX_SOURCE_SIZE];
  u16 used = 0;
  while(used + 3U <= sizeof(source)) {
    source[used++] = 'a';
    source[used++] = '\n';
    source[used++] = '\n';
  }

  u8 compiled[markdown::MAX_COMPILED_SIZE];
  u16 compiled_size = 0;
  assert(markdown::compile(
      (const u8*) source, used, compiled, sizeof(compiled), compiled_size) ==
      markdown::Status::OK);
  assert(compiled_size <= sizeof(compiled));
}

static markdown_scroll::Metrics scroll_metrics(
    u16 current, const u16* anchors, usize anchor_count,
    u16 document_height) {
  markdown_scroll::Probe probe(current);
  for(usize index = 0; index < anchor_count; index++) {
    probe.note(anchors[index]);
  }
  return probe.finish(document_height);
}

static bool bitmap_pixel(
    const u8* bitmap, u16 width, u16 x, u16 y) {
  return (bitmap[(usize) (y / 8U) * width + x] &
          (u8) (1U << (y & 7U))) != 0;
}

static void set_bitmap_pixel(
    u8* bitmap, u16 width, u16 x, u16 y) {
  bitmap[(usize) (y / 8U) * width + x] |=
      (u8) (1U << (y & 7U));
}

static void test_graphic_scroll_frame_shift(void) {
  static constexpr u16 WIDTH = 3;
  static constexpr u8 PAGES = 2;
  u8 original[WIDTH * PAGES] = {};
  u8 incoming[WIDTH * PAGES] = {};
  for(u16 x = 0; x < WIDTH; x++) {
    for(u16 y = 0; y < PAGES * 8U; y++) {
      if(((x * 5U + y * 3U) % 7U) < 3U) {
        set_bitmap_pixel(original, WIDTH, x, y);
      }
      if(((x * 2U + y * 5U) % 11U) < 4U) {
        set_bitmap_pixel(incoming, WIDTH, x, y);
      }
    }
  }

  u8 shifted[sizeof(original)] = {};
  memcpy(shifted, original, sizeof(shifted));
  markdown_scroll::shift_up_insert_row(
      shifted, WIDTH, PAGES, incoming, 5);
  for(u16 x = 0; x < WIDTH; x++) {
    for(u16 y = 0; y + 1U < PAGES * 8U; y++) {
      assert(bitmap_pixel(shifted, WIDTH, x, y) ==
             bitmap_pixel(original, WIDTH, x, (u16) (y + 1U)));
    }
    assert(bitmap_pixel(shifted, WIDTH, x, PAGES * 8U - 1U) ==
           bitmap_pixel(incoming, WIDTH, x, 5));
  }

  memcpy(shifted, original, sizeof(shifted));
  markdown_scroll::shift_down_insert_row(
      shifted, WIDTH, PAGES, incoming, 9);
  for(u16 x = 0; x < WIDTH; x++) {
    assert(bitmap_pixel(shifted, WIDTH, x, 0) ==
           bitmap_pixel(incoming, WIDTH, x, 9));
    for(u16 y = 1; y < PAGES * 8U; y++) {
      assert(bitmap_pixel(shifted, WIDTH, x, y) ==
             bitmap_pixel(original, WIDTH, x, (u16) (y - 1U)));
    }
  }
}

static void test_graphic_scroll_navigation(void) {
  const u16 regular_anchors[] = {
      0, 10, 20, 30, 40, 50, 60, 70, 80, 90,
      100, 110, 120, 130, 140, 150
  };

  markdown_scroll::Metrics metrics = scroll_metrics(
      0, regular_anchors,
      sizeof(regular_anchors) / sizeof(regular_anchors[0]), 200);
  assert(metrics.document_height == 200);
  assert(metrics.current_top == 0);
  assert(metrics.maximum_top == 136);
  assert(metrics.previous_anchor == 0);
  assert(metrics.next_anchor == 10);
  assert(metrics.fast_previous_anchor == 0);
  assert(metrics.fast_next_anchor == 50);
  assert(metrics.snap_anchor == 0);

  metrics = scroll_metrics(
      35, regular_anchors,
      sizeof(regular_anchors) / sizeof(regular_anchors[0]), 200);
  assert(metrics.previous_anchor == 30);
  assert(metrics.next_anchor == 40);
  assert(metrics.fast_previous_anchor == 0);
  assert(metrics.fast_next_anchor == 90);
  assert(metrics.snap_anchor == 30);

  metrics = scroll_metrics(
      100, regular_anchors,
      sizeof(regular_anchors) / sizeof(regular_anchors[0]), 200);
  assert(metrics.previous_anchor == 90);
  assert(metrics.next_anchor == 110);
  assert(metrics.fast_previous_anchor == 50);
  assert(metrics.fast_next_anchor == 136);
  assert(metrics.snap_anchor == 100);

  const u16 sparse_anchors[] = {0, 64, 128};
  metrics = scroll_metrics(
      0, sparse_anchors,
      sizeof(sparse_anchors) / sizeof(sparse_anchors[0]), 192);
  assert(metrics.maximum_top == 128);
  assert(metrics.next_anchor == 64);
  assert(metrics.fast_next_anchor == 56);

  const u16 large_gap_anchors[] = {0, 160};
  metrics = scroll_metrics(
      100, large_gap_anchors,
      sizeof(large_gap_anchors) / sizeof(large_gap_anchors[0]), 228);
  assert(metrics.previous_anchor == 0);
  assert(metrics.next_anchor == 160);
  assert(metrics.fast_previous_anchor == 44);
  assert(metrics.fast_next_anchor == 156);

  metrics = scroll_metrics(
      20, regular_anchors,
      sizeof(regular_anchors) / sizeof(regular_anchors[0]), 50);
  assert(metrics.current_top == 0);
  assert(metrics.maximum_top == 0);
  assert(metrics.previous_anchor == 0);
  assert(metrics.next_anchor == 0);
  assert(metrics.fast_previous_anchor == 0);
  assert(metrics.fast_next_anchor == 0);
  assert(metrics.snap_anchor == 0);

  assert(markdown_scroll::pixel_toward(10, 15) == 11);
  assert(markdown_scroll::pixel_toward(15, 10) == 14);
  assert(markdown_scroll::pixel_toward(10, 15, 3) == 13);
  assert(markdown_scroll::pixel_toward(10, 12, 3) == 12);
  assert(markdown_scroll::pixel_toward(15, 10, 0) == 15);
}

} // namespace

int main(void) {
  test_plain_text_profile();
  test_heading_forms_and_escapes();
  test_event_styles_and_image();
  test_bounds_and_malformed_stream();
  test_adversarial_inline_density_fits();
  test_adversarial_block_density_fits();
  test_graphic_scroll_frame_shift();
  test_graphic_scroll_navigation();
  printf("markdown_document_self_test: ok\n");
  return 0;
}
