#include "../code/markdown_document.hpp"

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

} // namespace

int main(void) {
  test_plain_text_profile();
  test_heading_forms_and_escapes();
  test_event_styles_and_image();
  test_bounds_and_malformed_stream();
  test_adversarial_inline_density_fits();
  test_adversarial_block_density_fits();
  printf("markdown_document_self_test: ok\n");
  return 0;
}
