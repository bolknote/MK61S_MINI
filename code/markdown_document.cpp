#if defined(ARDUINO)
  #include "config.h"
#endif

#if !defined(ARDUINO) || MK61_MARKDOWN_VIEWER_IS_BUILTIN || \
    defined(MK61_BUILD_MARKDOWN_MODULE)

#include "markdown_document.hpp"

#include <string.h>

namespace markdown {
namespace {

enum class Op : u8 {
  END = 0,
  BLOCK_BEGIN = 1,
  BLOCK_END = 2,
  STYLE = 3,
  TEXT = 4,
  HARD_BREAK = 5,
  IMAGE = 6
};

struct Range {
  u16 begin;
  u16 end;
};

struct Line {
  u16 begin;
  u16 content_end;
  u16 next;
};

class Writer {
 public:
  Writer(u8* output, u16 capacity)
      : bytes(output), byte_capacity(capacity), offset(0),
        text_length_offset(0), text_active(false), failed(false),
        current_style(STYLE_NONE) {}

  bool ok(void) const { return !failed; }
  u16 size(void) const { return offset; }

  bool finish(void) {
    close_text();
    return put_u8((u8) Op::END);
  }

  bool block_begin(BlockKind kind, u8 level = 0,
                   ListKind list_kind = ListKind::NONE,
                   TaskState task = TaskState::NONE,
                   u16 ordinal = 0) {
    close_text();
    if(current_style != STYLE_NONE && !style(STYLE_NONE)) return false;
    if(!put_u8((u8) Op::BLOCK_BEGIN) || !put_u8((u8) kind)) return false;
    switch(kind) {
      case BlockKind::HEADING:
      case BlockKind::QUOTE:
        return put_u8(level);
      case BlockKind::LIST_ITEM:
        return put_u8(level) &&
               put_u8((u8) list_kind) &&
               put_u8((u8) task) &&
               put_u16(ordinal);
      case BlockKind::PARAGRAPH:
      case BlockKind::CODE:
      case BlockKind::THEMATIC_BREAK:
      case BlockKind::BLANK:
        return true;
    }
    return fail();
  }

  bool block_end(void) {
    close_text();
    if(current_style != STYLE_NONE && !style(STYLE_NONE)) return false;
    return put_u8((u8) Op::BLOCK_END);
  }

  bool style(u8 value) {
    if(value == current_style) return true;
    close_text();
    if(!put_u8((u8) Op::STYLE) || !put_u8(value)) return false;
    current_style = value;
    return true;
  }

  bool text(const u8* data, u16 length) {
    if(data == nullptr && length != 0) return fail();
    for(u16 index = 0; index < length; index++) {
      u8 value = data[index];
      // The stream can carry arbitrary UTF-8, but source control characters
      // other than tab are not useful on either display.
      if(value < 0x20 && value != '\t') value = '?';
      if(!text_byte(value)) return false;
    }
    return true;
  }

  bool text_byte(u8 value) {
    if(!text_active) {
      close_text();
      if(!put_u8((u8) Op::TEXT)) return false;
      text_length_offset = offset;
      if(!put_u16(0)) return false;
      text_active = true;
    }
    if(!put_u8(value)) return false;
    const u16 length = get_u16(text_length_offset);
    if(length == 0xFFFFU) return fail();
    set_u16(text_length_offset, (u16) (length + 1U));
    return true;
  }

  bool hard_break(void) {
    close_text();
    return put_u8((u8) Op::HARD_BREAK);
  }

  bool image(const u8* alt, u16 alt_len,
             const u8* path, u16 path_len) {
    close_text();
    return put_u8((u8) Op::IMAGE) &&
           put_u16(alt_len) && put_u16(path_len) &&
           put_bytes(alt, alt_len) && put_bytes(path, path_len);
  }

 private:
  u8* bytes;
  u16 byte_capacity;
  u16 offset;
  u16 text_length_offset;
  bool text_active;
  bool failed;
  u8 current_style;

  bool fail(void) {
    failed = true;
    return false;
  }

  void close_text(void) {
    text_active = false;
  }

  bool reserve(u16 count) {
    if(failed || count > byte_capacity - offset) return fail();
    return true;
  }

  bool put_u8(u8 value) {
    if(!reserve(1)) return false;
    bytes[offset++] = value;
    return true;
  }

  bool put_u16(u16 value) {
    if(!reserve(2)) return false;
    bytes[offset++] = (u8) value;
    bytes[offset++] = (u8) (value >> 8);
    return true;
  }

  bool put_bytes(const u8* data, u16 length) {
    if(data == nullptr && length != 0) return fail();
    if(!reserve(length)) return false;
    if(length != 0) memcpy(bytes + offset, data, length);
    offset = (u16) (offset + length);
    return true;
  }

  u16 get_u16(u16 at) const {
    return (u16) bytes[at] | ((u16) bytes[at + 1] << 8);
  }

  void set_u16(u16 at, u16 value) {
    bytes[at] = (u8) value;
    bytes[at + 1] = (u8) (value >> 8);
  }
};

static bool ascii_space(u8 value) {
  return value == ' ' || value == '\t';
}

static Range trim(const u8* source, Range range) {
  while(range.begin < range.end && ascii_space(source[range.begin])) {
    range.begin++;
  }
  while(range.end > range.begin && ascii_space(source[range.end - 1])) {
    range.end--;
  }
  return range;
}

static Line line_at(const u8* source, u16 size, u16 offset) {
  Line line = {offset, offset, offset};
  while(line.content_end < size && source[line.content_end] != '\r' &&
        source[line.content_end] != '\n') {
    line.content_end++;
  }
  line.next = line.content_end;
  if(line.next < size && source[line.next] == '\r') line.next++;
  if(line.next < size && source[line.next] == '\n') line.next++;
  return line;
}

static bool range_equal(const u8* source, Range range, const char* text) {
  const usize length = strlen(text);
  return range.end - range.begin == length &&
         memcmp(source + range.begin, text, length) == 0;
}

static bool escaped_at(const u8* source, u16 begin, u16 offset) {
  u16 slashes = 0;
  while(offset > begin && source[offset - 1] == '\\') {
    offset--;
    slashes++;
  }
  return (slashes & 1U) != 0;
}

static u16 find_unescaped(const u8* source, u16 begin, u16 end,
                          const char* delimiter, u8 delimiter_len) {
  if(delimiter_len == 0 || begin > end) return end;
  for(u16 offset = begin; offset + delimiter_len <= end; offset++) {
    if(source[offset] == (u8) delimiter[0] &&
       memcmp(source + offset, delimiter, delimiter_len) == 0 &&
       !escaped_at(source, begin, offset)) {
      return offset;
    }
  }
  return end;
}

static bool punctuation(u8 value) {
  switch(value) {
    case '\\': case '`': case '*': case '_': case '{': case '}':
    case '[': case ']': case '<': case '>': case '(': case ')':
    case '#': case '+': case '-': case '.': case '!': case '|':
    case '~':
      return true;
    default:
      return false;
  }
}

static bool append_entity(Writer& writer, const u8* source,
                          u16 offset, u16 end, u16& consumed) {
  struct Entity {
    const char* encoded;
    const char* decoded;
  };
  static const Entity entities[] = {
    {"&amp;", "&"},
    {"&lt;", "<"},
    {"&gt;", ">"},
    {"&quot;", "\""},
    {"&#39;", "'"}
  };
  for(const Entity& entity : entities) {
    const u16 length = (u16) strlen(entity.encoded);
    if(offset + length <= end &&
       memcmp(source + offset, entity.encoded, length) == 0) {
      consumed = length;
      return writer.text((const u8*) entity.decoded,
                         (u16) strlen(entity.decoded));
    }
  }
  return false;
}

static bool compile_inline(Writer& writer, const u8* source,
                           u16 begin, u16 end, u8 style, u8 depth);

static bool compile_delimited(Writer& writer, const u8* source,
                              u16& offset, u16 end, u8 style, u8 depth,
                              const char* delimiter, u8 delimiter_len,
                              u8 added_style) {
  if(offset + delimiter_len >= end ||
     memcmp(source + offset, delimiter, delimiter_len) != 0) {
    return false;
  }
  const u16 close = find_unescaped(
      source, (u16) (offset + delimiter_len), end,
      delimiter, delimiter_len);
  if(close == end || close == offset + delimiter_len) return false;
  if(!writer.style((u8) (style | added_style)) ||
     !compile_inline(writer, source,
                     (u16) (offset + delimiter_len), close,
                     (u8) (style | added_style), (u8) (depth + 1U)) ||
     !writer.style(style)) {
    return false;
  }
  offset = (u16) (close + delimiter_len);
  return true;
}

static bool compile_code_span(Writer& writer, const u8* source,
                              u16& offset, u16 end, u8 style) {
  u8 run = 0;
  while(offset + run < end && source[offset + run] == '`' && run < 16) {
    run++;
  }
  if(run == 0) return false;
  u16 close = offset + run;
  while(close + run <= end) {
    if(source[close] == '`') {
      u8 close_run = 0;
      while(close + close_run < end && source[close + close_run] == '`' &&
            close_run < 16) {
        close_run++;
      }
      if(close_run == run) break;
      close = (u16) (close + close_run);
    } else {
      close++;
    }
  }
  if(close + run > end) return false;

  u16 content_begin = (u16) (offset + run);
  u16 content_end = close;
  if(content_end > content_begin + 1U &&
     source[content_begin] == ' ' && source[content_end - 1] == ' ') {
    content_begin++;
    content_end--;
  }
  if(!writer.style((u8) (style | STYLE_CODE))) return false;
  for(u16 index = content_begin; index < content_end; index++) {
    const u8 value = source[index] == '\n' || source[index] == '\r'
        ? (u8) ' ' : source[index];
    if(!writer.text_byte(value)) return false;
  }
  if(!writer.style(style)) return false;
  offset = (u16) (close + run);
  return true;
}

static bool compile_image(Writer& writer, const u8* source,
                          u16& offset, u16 end) {
  if(offset + 4U > end || source[offset] != '!' ||
     source[offset + 1] != '[') return false;
  const u16 close_alt =
      find_unescaped(source, (u16) (offset + 2U), end, "]", 1);
  if(close_alt == end || close_alt + 2U > end ||
     source[close_alt + 1] != '(') return false;
  const u16 close_path =
      find_unescaped(source, (u16) (close_alt + 2U), end, ")", 1);
  if(close_path == end) return false;

  Range alt = { (u16) (offset + 2U), close_alt };
  Range path = trim(source, {
      (u16) (close_alt + 2U), close_path
  });
  if(path.end > path.begin + 1U && source[path.begin] == '<' &&
     source[path.end - 1] == '>') {
    path.begin++;
    path.end--;
  }
  if(path.begin == path.end) return false;
  if(!writer.image(source + alt.begin, (u16) (alt.end - alt.begin),
                   source + path.begin, (u16) (path.end - path.begin))) {
    return false;
  }
  offset = (u16) (close_path + 1U);
  return true;
}

static bool compile_link(Writer& writer, const u8* source,
                         u16& offset, u16 end, u8 style, u8 depth) {
  if(source[offset] != '[') return false;
  const u16 close_label =
      find_unescaped(source, (u16) (offset + 1U), end, "]", 1);
  if(close_label == end || close_label + 2U > end ||
     source[close_label + 1] != '(') return false;
  const u16 close_target =
      find_unescaped(source, (u16) (close_label + 2U), end, ")", 1);
  if(close_target == end) return false;

  if(!writer.style((u8) (style | STYLE_LINK)) ||
     !compile_inline(writer, source, (u16) (offset + 1U), close_label,
                     (u8) (style | STYLE_LINK), (u8) (depth + 1U)) ||
     !writer.style(style)) {
    return false;
  }
  offset = (u16) (close_target + 1U);
  return true;
}

static bool compile_inline(Writer& writer, const u8* source,
                           u16 begin, u16 end, u8 style, u8 depth) {
  if(depth > MAX_INLINE_DEPTH) return writer.text(source + begin,
                                                  (u16) (end - begin));
  if(!writer.style(style)) return false;
  u16 offset = begin;
  while(offset < end) {
    if(source[offset] == '\\' && offset + 1U < end &&
       punctuation(source[offset + 1])) {
      if(!writer.text_byte(source[offset + 1])) return false;
      offset = (u16) (offset + 2U);
      continue;
    }
    if(source[offset] == '&') {
      u16 consumed = 0;
      if(append_entity(writer, source, offset, end, consumed)) {
        offset = (u16) (offset + consumed);
        continue;
      }
    }
    if(source[offset] == '`' &&
       compile_code_span(writer, source, offset, end, style)) {
      continue;
    }
    if(source[offset] == '!' &&
       compile_image(writer, source, offset, end)) {
      continue;
    }
    if(source[offset] == '[' &&
       compile_link(writer, source, offset, end, style, depth)) {
      continue;
    }
    if(source[offset] == '~' &&
       compile_delimited(writer, source, offset, end, style, depth,
                         "~~", 2, STYLE_STRIKE)) {
      continue;
    }
    if(source[offset] == '*' &&
       compile_delimited(writer, source, offset, end, style, depth,
                         "**", 2, STYLE_BOLD)) {
      continue;
    }
    if(source[offset] == '_' &&
       compile_delimited(writer, source, offset, end, style, depth,
                         "__", 2, STYLE_BOLD)) {
      continue;
    }
    if(source[offset] == '*' &&
       compile_delimited(writer, source, offset, end, style, depth,
                         "*", 1, STYLE_ITALIC)) {
      continue;
    }
    if(source[offset] == '_' &&
       compile_delimited(writer, source, offset, end, style, depth,
                         "_", 1, STYLE_ITALIC)) {
      continue;
    }
    if(!writer.text_byte(source[offset++])) return false;
  }
  return true;
}

static u8 leading_spaces(const u8* source, Range range) {
  u8 count = 0;
  while(range.begin + count < range.end && count < 12) {
    if(source[range.begin + count] == ' ') count++;
    else if(source[range.begin + count] == '\t') count = (u8) (count + 2U);
    else break;
  }
  return count;
}

static bool thematic_break(const u8* source, Range range) {
  range = trim(source, range);
  u8 marker = 0;
  u8 count = 0;
  for(u16 index = range.begin; index < range.end; index++) {
    const u8 value = source[index];
    if(ascii_space(value)) continue;
    if(value != '*' && value != '-' && value != '_') return false;
    if(marker == 0) marker = value;
    if(value != marker) return false;
    count++;
  }
  return count >= 3;
}

static u8 heading_level(const u8* source, Range range, Range& content) {
  const u8 spaces = leading_spaces(source, range);
  if(spaces > 3) return 0;
  u16 offset = (u16) (range.begin + spaces);
  u8 level = 0;
  while(offset < range.end && source[offset] == '#' && level < 6) {
    offset++;
    level++;
  }
  if(level == 0 || (offset < range.end && !ascii_space(source[offset]))) {
    return 0;
  }
  while(offset < range.end && ascii_space(source[offset])) offset++;
  content = {offset, range.end};
  content = trim(source, content);
  while(content.end > content.begin && source[content.end - 1] == '#') {
    content.end--;
  }
  content = trim(source, content);
  return level;
}

static bool fence_open(const u8* source, Range range,
                       u8& marker, u8& count) {
  const u8 spaces = leading_spaces(source, range);
  if(spaces > 3) return false;
  u16 offset = (u16) (range.begin + spaces);
  if(offset >= range.end ||
     (source[offset] != '`' && source[offset] != '~')) return false;
  marker = source[offset];
  count = 0;
  while(offset < range.end && source[offset] == marker) {
    offset++;
    count++;
  }
  return count >= 3;
}

static bool fence_close(const u8* source, Range range,
                        u8 marker, u8 minimum) {
  range = trim(source, range);
  u8 count = 0;
  while(range.begin + count < range.end &&
        source[range.begin + count] == marker) count++;
  if(count < minimum) return false;
  for(u16 index = (u16) (range.begin + count); index < range.end; index++) {
    if(!ascii_space(source[index])) return false;
  }
  return true;
}

struct ListPrefix {
  bool valid;
  u8 depth;
  ListKind kind;
  TaskState task;
  u16 ordinal;
  Range content;
};

static ListPrefix list_prefix(const u8* source, Range range) {
  ListPrefix result = {
    false, 0, ListKind::NONE, TaskState::NONE, 0, range
  };
  const u8 spaces = leading_spaces(source, range);
  u16 offset = (u16) (range.begin + spaces);
  if(offset >= range.end) return result;
  result.depth = spaces / 2U;
  if(result.depth > 3) result.depth = 3;

  if((source[offset] == '-' || source[offset] == '+' ||
      source[offset] == '*') &&
     offset + 1U < range.end && ascii_space(source[offset + 1])) {
    result.kind = ListKind::UNORDERED;
    offset = (u16) (offset + 2U);
  } else if(source[offset] >= '0' && source[offset] <= '9') {
    u32 ordinal = 0;
    u8 digits = 0;
    while(offset < range.end && source[offset] >= '0' &&
          source[offset] <= '9' && digits < 5) {
      ordinal = ordinal * 10U + (u8) (source[offset] - '0');
      offset++;
      digits++;
    }
    if(digits == 0 || ordinal > 0xFFFFU || offset + 1U >= range.end ||
       (source[offset] != '.' && source[offset] != ')') ||
       !ascii_space(source[offset + 1])) {
      return result;
    }
    result.kind = ListKind::ORDERED;
    result.ordinal = (u16) ordinal;
    offset = (u16) (offset + 2U);
  } else {
    return result;
  }

  while(offset < range.end && ascii_space(source[offset])) offset++;
  if(offset + 3U <= range.end && source[offset] == '[' &&
     source[offset + 2] == ']' &&
     (source[offset + 1] == ' ' || source[offset + 1] == 'x' ||
      source[offset + 1] == 'X') &&
     (offset + 3U == range.end || ascii_space(source[offset + 3]))) {
    result.task = source[offset + 1] == ' '
        ? TaskState::UNCHECKED : TaskState::CHECKED;
    offset = (u16) (offset + 3U);
    while(offset < range.end && ascii_space(source[offset])) offset++;
  }
  result.content = {offset, range.end};
  result.valid = true;
  return result;
}

static bool quote_prefix(const u8* source, Range range,
                         u8& depth, Range& content) {
  u16 offset = range.begin;
  depth = 0;
  while(offset < range.end) {
    u8 spaces = 0;
    while(offset < range.end && source[offset] == ' ' && spaces < 3) {
      offset++;
      spaces++;
    }
    if(offset >= range.end || source[offset] != '>') break;
    offset++;
    depth++;
    if(offset < range.end && source[offset] == ' ') offset++;
    if(depth == 3) break;
  }
  if(depth == 0) return false;
  content = {offset, range.end};
  return true;
}

enum class LineClass : u8 {
  BLANK,
  HEADING,
  THEMATIC_BREAK,
  QUOTE,
  LIST,
  FENCE,
  ORDINARY
};

static LineClass classify(const u8* source, Range line) {
  const Range trimmed = trim(source, line);
  if(trimmed.begin == trimmed.end) return LineClass::BLANK;
  Range ignored = {};
  if(heading_level(source, line, ignored) != 0) return LineClass::HEADING;
  u8 marker = 0;
  u8 count = 0;
  if(fence_open(source, line, marker, count)) return LineClass::FENCE;
  u8 quote_depth = 0;
  if(quote_prefix(source, line, quote_depth, ignored)) {
    return LineClass::QUOTE;
  }
  if(list_prefix(source, line).valid) return LineClass::LIST;
  if(thematic_break(source, line)) return LineClass::THEMATIC_BREAK;
  return LineClass::ORDINARY;
}

static Range without_hard_break(const u8* source, Range range,
                                bool& hard_break) {
  hard_break = false;
  u16 end = range.end;
  u8 spaces = 0;
  while(end > range.begin && source[end - 1] == ' ') {
    end--;
    spaces++;
  }
  if(spaces >= 2) {
    hard_break = true;
    range.end = end;
    return range;
  }
  if(end > range.begin && source[end - 1] == '\\' &&
     !escaped_at(source, range.begin, (u16) (end - 1U))) {
    hard_break = true;
    range.end = (u16) (end - 1U);
  }
  return range;
}

static bool emit_simple_block(Writer& writer, const u8* source,
                              BlockKind kind, Range content,
                              u8 level = 0,
                              ListKind list_kind = ListKind::NONE,
                              TaskState task = TaskState::NONE,
                              u16 ordinal = 0) {
  return writer.block_begin(kind, level, list_kind, task, ordinal) &&
         compile_inline(writer, source, content.begin, content.end,
                        STYLE_NONE, 0) &&
         writer.block_end();
}

static bool compile_document(Writer& writer,
                             const u8* source, u16 size) {
  u16 offset = 0;
  while(offset < size) {
    const Line line = line_at(source, size, offset);
    const Range whole = {line.begin, line.content_end};
    const LineClass kind = classify(source, whole);

    if(kind == LineClass::BLANK) {
      if(!writer.block_begin(BlockKind::BLANK) || !writer.block_end()) {
        return false;
      }
      offset = line.next;
      continue;
    }

    if(kind == LineClass::HEADING) {
      Range content = {};
      const u8 level = heading_level(source, whole, content);
      if(!emit_simple_block(writer, source, BlockKind::HEADING,
                            content, level)) return false;
      offset = line.next;
      continue;
    }

    if(kind == LineClass::THEMATIC_BREAK) {
      if(!writer.block_begin(BlockKind::THEMATIC_BREAK) ||
         !writer.block_end()) return false;
      offset = line.next;
      continue;
    }

    if(kind == LineClass::QUOTE) {
      u8 depth = 0;
      Range content = {};
      (void) quote_prefix(source, whole, depth, content);
      if(!emit_simple_block(writer, source, BlockKind::QUOTE,
                            content, depth)) return false;
      offset = line.next;
      continue;
    }

    if(kind == LineClass::LIST) {
      const ListPrefix prefix = list_prefix(source, whole);
      if(!emit_simple_block(writer, source, BlockKind::LIST_ITEM,
                            prefix.content, prefix.depth, prefix.kind,
                            prefix.task, prefix.ordinal)) return false;
      offset = line.next;
      continue;
    }

    if(kind == LineClass::FENCE) {
      u8 marker = 0;
      u8 count = 0;
      (void) fence_open(source, whole, marker, count);
      if(!writer.block_begin(BlockKind::CODE) ||
         !writer.style(STYLE_CODE)) return false;
      offset = line.next;
      bool first = true;
      while(offset < size) {
        const Line code_line = line_at(source, size, offset);
        const Range code_range = {code_line.begin, code_line.content_end};
        if(fence_close(source, code_range, marker, count)) {
          offset = code_line.next;
          break;
        }
        if(!first && !writer.hard_break()) return false;
        if(!writer.text(source + code_range.begin,
                        (u16) (code_range.end - code_range.begin))) {
          return false;
        }
        first = false;
        offset = code_line.next;
      }
      if(!writer.style(STYLE_NONE) || !writer.block_end()) return false;
      continue;
    }

    // Consecutive ordinary lines form one paragraph. A following setext
    // underline promotes a one-line paragraph to H1/H2.
    const Line next_line = line.next < size
        ? line_at(source, size, line.next)
        : Line{size, size, size};
    if(next_line.begin < size) {
      const Range next_range = trim(source, {
        next_line.begin, next_line.content_end
      });
      if(range_equal(source, next_range, "===") ||
         range_equal(source, next_range, "---")) {
        if(!emit_simple_block(writer, source, BlockKind::HEADING,
                              trim(source, whole),
                              range_equal(source, next_range, "===")
                                  ? 1 : 2)) {
          return false;
        }
        offset = next_line.next;
        continue;
      }
    }

    if(!writer.block_begin(BlockKind::PARAGRAPH)) return false;
    Line paragraph_line = line;
    while(true) {
      bool hard_break = false;
      Range content = without_hard_break(
          source, {paragraph_line.begin, paragraph_line.content_end},
          hard_break);
      content = trim(source, content);
      if(!compile_inline(writer, source, content.begin, content.end,
                         STYLE_NONE, 0)) return false;
      offset = paragraph_line.next;
      if(offset >= size) break;
      const Line candidate = line_at(source, size, offset);
      if(classify(source, {candidate.begin, candidate.content_end}) !=
         LineClass::ORDINARY) break;
      if(hard_break) {
        if(!writer.hard_break()) return false;
      } else {
        static const u8 SPACE = ' ';
        if(!writer.text(&SPACE, 1)) return false;
      }
      paragraph_line = candidate;
    }
    if(!writer.block_end()) return false;
  }
  return true;
}

class PlainWriter {
 public:
  PlainWriter(char* output, u16 capacity)
      : bytes(output), byte_capacity(capacity), offset(0), failed(false) {
    if(bytes != nullptr && byte_capacity != 0) bytes[0] = 0;
  }

  bool ok(void) const { return !failed; }
  u16 size(void) const { return offset; }

  bool append(const u8* data, u16 length) {
    if(data == nullptr && length != 0) return fail();
    if(byte_capacity == 0 || length > byte_capacity - 1U - offset) {
      return fail();
    }
    if(length != 0) memcpy(bytes + offset, data, length);
    offset = (u16) (offset + length);
    bytes[offset] = 0;
    return true;
  }

  bool append(const char* text) {
    return append((const u8*) text, (u16) strlen(text));
  }

  bool append_char(char value) {
    return append((const u8*) &value, 1);
  }

  bool newline(void) {
    if(offset != 0 && bytes[offset - 1] == '\n') return true;
    return append_char('\n');
  }

  bool paragraph_gap(void) {
    if(offset == 0) return true;
    if(bytes[offset - 1] != '\n' && !append_char('\n')) return false;
    return append_char('\n');
  }

  void trim_end(void) {
    while(offset != 0 &&
          (bytes[offset - 1] == '\n' || bytes[offset - 1] == ' ' ||
           bytes[offset - 1] == '\t')) {
      offset--;
    }
    if(byte_capacity != 0) bytes[offset] = 0;
  }

 private:
  char* bytes;
  u16 byte_capacity;
  u16 offset;
  bool failed;

  bool fail(void) {
    failed = true;
    return false;
  }
};

static bool append_unsigned(PlainWriter& writer, u16 value) {
  char digits[6];
  u8 count = 0;
  do {
    digits[count++] = (char) ('0' + value % 10U);
    value /= 10U;
  } while(value != 0 && count < sizeof(digits));
  while(count != 0) {
    if(!writer.append_char(digits[--count])) return false;
  }
  return true;
}

static bool append_image_fallback(PlainWriter& writer,
                                  const Event& event) {
  if(event.alt_len != 0) return writer.append(event.alt, event.alt_len);
  u16 begin = 0;
  for(u16 index = 0; index < event.path_len; index++) {
    if(event.path[index] == '/' || event.path[index] == '\\') {
      begin = (u16) (index + 1U);
    }
  }
  return writer.append(event.path + begin, (u16) (event.path_len - begin));
}

} // namespace

Reader::Reader(const u8* data, u16 size)
    : bytes(data), byte_count(size), offset(0), ended(false) {}

bool Reader::take_u8(u8& value) {
  if(bytes == nullptr || offset >= byte_count) return false;
  value = bytes[offset++];
  return true;
}

bool Reader::take_u16(u16& value) {
  u8 low = 0;
  u8 high = 0;
  if(!take_u8(low) || !take_u8(high)) return false;
  value = (u16) low | ((u16) high << 8);
  return true;
}

bool Reader::take_bytes(u16 length, const u8*& value) {
  if(bytes == nullptr || length > byte_count - offset) return false;
  value = bytes + offset;
  offset = (u16) (offset + length);
  return true;
}

Status Reader::next(Event& event) {
  memset(&event, 0, sizeof(event));
  event.kind = EventKind::END;
  if(ended) return Status::OK;
  u8 raw = 0;
  if(!take_u8(raw)) return Status::INVALID_STREAM;
  const Op op = (Op) raw;
  switch(op) {
    case Op::END:
      ended = true;
      event.kind = EventKind::END;
      return offset == byte_count ? Status::OK : Status::INVALID_STREAM;
    case Op::BLOCK_BEGIN: {
      u8 kind = 0;
      if(!take_u8(kind) || kind > (u8) BlockKind::BLANK) {
        return Status::INVALID_STREAM;
      }
      event.kind = EventKind::BLOCK_BEGIN;
      event.block.kind = (BlockKind) kind;
      if(event.block.kind == BlockKind::HEADING ||
         event.block.kind == BlockKind::QUOTE) {
        if(!take_u8(event.block.level)) return Status::INVALID_STREAM;
      } else if(event.block.kind == BlockKind::LIST_ITEM) {
        u8 list = 0;
        u8 task = 0;
        if(!take_u8(event.block.level) ||
           !take_u8(list) || !take_u8(task) ||
           !take_u16(event.block.ordinal) ||
           list > (u8) ListKind::ORDERED ||
           task > (u8) TaskState::CHECKED) {
          return Status::INVALID_STREAM;
        }
        event.block.list_kind = (ListKind) list;
        event.block.task = (TaskState) task;
      }
      return Status::OK;
    }
    case Op::BLOCK_END:
      event.kind = EventKind::BLOCK_END;
      return Status::OK;
    case Op::STYLE:
      if(!take_u8(event.style) ||
         (event.style & (u8) ~(STYLE_BOLD | STYLE_ITALIC |
                              STYLE_STRIKE | STYLE_CODE |
                              STYLE_LINK)) != 0) {
        return Status::INVALID_STREAM;
      }
      event.kind = EventKind::STYLE;
      return Status::OK;
    case Op::TEXT:
      if(!take_u16(event.text_len) ||
         !take_bytes(event.text_len, event.text)) {
        return Status::INVALID_STREAM;
      }
      event.kind = EventKind::TEXT;
      return Status::OK;
    case Op::HARD_BREAK:
      event.kind = EventKind::HARD_BREAK;
      return Status::OK;
    case Op::IMAGE:
      if(!take_u16(event.alt_len) || !take_u16(event.path_len) ||
         !take_bytes(event.alt_len, event.alt) ||
         !take_bytes(event.path_len, event.path)) {
        return Status::INVALID_STREAM;
      }
      event.kind = EventKind::IMAGE;
      return Status::OK;
  }
  return Status::INVALID_STREAM;
}

Status compile(const u8* source, u16 source_size,
               u8* output, u16 output_capacity, u16& output_size) {
  output_size = 0;
  if((source == nullptr && source_size != 0) || output == nullptr ||
     output_capacity == 0) {
    return Status::INVALID_ARGUMENT;
  }
  if(source_size > MAX_SOURCE_SIZE) return Status::SOURCE_TOO_LARGE;
  Writer writer(output, output_capacity);
  if(!compile_document(writer, source, source_size) || !writer.finish()) {
    return Status::OUTPUT_TOO_SMALL;
  }
  output_size = writer.size();
  return Status::OK;
}

Status to_plain_text(const u8* compiled, u16 compiled_size,
                     char* output, u16 output_capacity, u16& output_size) {
  output_size = 0;
  if(compiled == nullptr || compiled_size == 0 || output == nullptr ||
     output_capacity == 0) {
    return Status::INVALID_ARGUMENT;
  }
  PlainWriter writer(output, output_capacity);
  Reader reader(compiled, compiled_size);
  bool block_open = false;
  while(true) {
    Event event = {};
    const Status status = reader.next(event);
    if(status != Status::OK) return status;
    if(event.kind == EventKind::END) break;
    switch(event.kind) {
      case EventKind::BLOCK_BEGIN:
        if(block_open && !writer.newline()) return Status::OUTPUT_TOO_SMALL;
        block_open = true;
        if(event.block.kind == BlockKind::BLANK ||
           event.block.kind == BlockKind::THEMATIC_BREAK) {
          if(!writer.paragraph_gap()) return Status::OUTPUT_TOO_SMALL;
        } else if(event.block.kind == BlockKind::LIST_ITEM) {
          for(u8 depth = 0; depth < event.block.level; depth++) {
            if(!writer.append("  ")) return Status::OUTPUT_TOO_SMALL;
          }
          if(event.block.list_kind == ListKind::ORDERED) {
            if(!append_unsigned(writer, event.block.ordinal) ||
               !writer.append(". ")) return Status::OUTPUT_TOO_SMALL;
          } else {
            if(!writer.append("- ")) return Status::OUTPUT_TOO_SMALL;
          }
          if(event.block.task != TaskState::NONE) {
            if(!writer.append(event.block.task == TaskState::CHECKED
                                  ? "[x] " : "[ ] ")) {
              return Status::OUTPUT_TOO_SMALL;
            }
          }
        }
        break;
      case EventKind::BLOCK_END:
        if(!writer.newline()) return Status::OUTPUT_TOO_SMALL;
        block_open = false;
        break;
      case EventKind::STYLE:
        break;
      case EventKind::TEXT:
        if(!writer.append(event.text, event.text_len)) {
          return Status::OUTPUT_TOO_SMALL;
        }
        break;
      case EventKind::HARD_BREAK:
        if(!writer.newline()) return Status::OUTPUT_TOO_SMALL;
        break;
      case EventKind::IMAGE:
        if(!append_image_fallback(writer, event)) {
          return Status::OUTPUT_TOO_SMALL;
        }
        break;
      case EventKind::END:
        break;
    }
  }
  writer.trim_end();
  if(!writer.ok()) return Status::OUTPUT_TOO_SMALL;
  output_size = writer.size();
  return Status::OK;
}

const char* status_text(Status status) {
  switch(status) {
    case Status::OK: return "ok";
    case Status::INVALID_ARGUMENT: return "invalid argument";
    case Status::SOURCE_TOO_LARGE: return "source too large";
    case Status::OUTPUT_TOO_SMALL: return "output too small";
    case Status::INVALID_STREAM: return "invalid compiled stream";
  }
  return "unknown markdown error";
}

} // namespace markdown

#endif
