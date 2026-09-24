#ifndef MK61_MARKDOWN_DOCUMENT_HPP
#define MK61_MARKDOWN_DOCUMENT_HPP

#include "rust_types.h"

namespace markdown {

// A compiled document is a compact, bounded event stream. Text is copied into
// the stream, so the source buffer may be released before linked images are
// opened from C6.
static constexpr u16 MAX_SOURCE_SIZE = 1536;
static constexpr u16 MAX_COMPILED_SIZE = 6144;
static constexpr u8 MAX_INLINE_DEPTH = 8;
// The shortest accepted link is "[a](b)".  This is therefore a strict
// upper bound for the number of links in one source document.
static constexpr u16 MAX_PLAIN_LINKS = MAX_SOURCE_SIZE / 6U;

enum class Status : u8 {
  OK = 0,
  INVALID_ARGUMENT,
  SOURCE_TOO_LARGE,
  OUTPUT_TOO_SMALL,
  INVALID_STREAM
};

enum Style : u8 {
  STYLE_NONE = 0,
  STYLE_BOLD = 1U << 0,
  STYLE_ITALIC = 1U << 1,
  STYLE_STRIKE = 1U << 2,
  STYLE_CODE = 1U << 3,
  STYLE_LINK = 1U << 4
};

enum class BlockKind : u8 {
  PARAGRAPH = 0,
  HEADING,
  LIST_ITEM,
  QUOTE,
  CODE,
  THEMATIC_BREAK,
  BLANK
};

enum class ListKind : u8 {
  NONE = 0,
  UNORDERED,
  ORDERED
};

enum class TaskState : u8 {
  NONE = 0,
  UNCHECKED,
  CHECKED
};

enum class EventKind : u8 {
  END = 0,
  BLOCK_BEGIN,
  BLOCK_END,
  STYLE,
  TEXT,
  HARD_BREAK,
  IMAGE,
  LINK_BEGIN,
  LINK_END
};

struct Block {
  BlockKind kind;
  u8 level;
  ListKind list_kind;
  TaskState task;
  u16 ordinal;
};

struct Event {
  EventKind kind;
  Block block;
  u8 style;
  const u8* text;
  u16 text_len;
  const u8* alt;
  u16 alt_len;
  const u8* path;
  u16 path_len;
};

struct PlainLink {
  u16 begin;
  u16 end;
};

class Reader {
 public:
  Reader(const u8* data, u16 size);

  Status next(Event& event);
  u16 position(void) const { return offset; }

 private:
  const u8* bytes;
  u16 byte_count;
  u16 offset;
  bool ended;

  bool take_u8(u8& value);
  bool take_u16(u16& value);
  bool take_bytes(u16 length, const u8*& value);
};

Status compile(const u8* source, u16 source_size,
               u8* output, u16 output_capacity, u16& output_size);

// Produces the semantic plain-text form used on LCD1602. Presentation markers
// are removed, while list prefixes, task boxes and line structure are kept.
Status to_plain_text(const u8* compiled, u16 compiled_size,
                     char* output, u16 output_capacity, u16& output_size);

// Same semantic conversion, additionally returning the byte ranges occupied
// by link labels in the plain text.  Targets stay in the compiled stream and
// are resolved only when the user opens a selected link.
Status to_plain_text_with_links(
    const u8* compiled, u16 compiled_size,
    char* output, u16 output_capacity, u16& output_size,
    PlainLink* links, u16 link_capacity, u16& link_count);

const char* status_text(Status status);

} // namespace markdown

#endif
