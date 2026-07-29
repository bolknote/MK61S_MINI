#if defined(ARDUINO)
  #include "config.h"
#endif

#if !defined(ARDUINO) || \
    ((!MK61_HAS_COMPILED_GRAPHICS) && \
     (MK61_MARKDOWN_VIEWER_IS_BUILTIN || \
      defined(MK61_BUILD_MARKDOWN_MODULE)))

#include "markdown_plain.hpp"

#include <string.h>

namespace markdown_plain {
namespace {

struct Range {
  u16 begin;
  u16 end;
};

struct Line {
  u16 begin;
  u16 end;
  u16 next;
};

class Writer {
 public:
  Writer(char* output, u16 capacity)
      : bytes(output), byte_capacity(capacity), offset(0), failed(false) {}

  bool ok(void) const { return !failed; }
  u16 size(void) const { return offset; }

  bool text(const u8* data, u16 length) {
    if(data == nullptr && length != 0) return fail();
    if(offset + length >= byte_capacity) return fail();
    for(u16 index = 0; index < length; index++) {
      const u8 value = data[index];
      bytes[offset++] = value < 0x20 && value != '\t'
          ? '?' : (char) value;
    }
    return true;
  }

  bool literal(const char* value) {
    const u16 length = (u16) strlen(value);
    if(offset + length >= byte_capacity) return fail();
    if(length != 0) memcpy(bytes + offset, value, length);
    offset = (u16) (offset + length);
    return true;
  }

  bool character(char value) {
    if(offset + 1U >= byte_capacity) return fail();
    bytes[offset++] = value;
    return true;
  }

  bool newline(void) {
    return offset != 0 && bytes[offset - 1U] == '\n'
        ? true : character('\n');
  }

  bool paragraph_gap(void) {
    if(offset == 0) return true;
    if(bytes[offset - 1U] != '\n' && !character('\n')) return false;
    return character('\n');
  }

  void finish(void) {
    while(offset != 0 &&
          (bytes[offset - 1U] == '\n' || bytes[offset - 1U] == ' ' ||
           bytes[offset - 1U] == '\t')) {
      offset--;
    }
    bytes[offset] = 0;
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

static bool ascii_space(u8 value) {
  return value == ' ' || value == '\t';
}

static Range trim(const u8* source, Range range) {
  while(range.begin < range.end && ascii_space(source[range.begin])) {
    range.begin++;
  }
  while(range.end > range.begin && ascii_space(source[range.end - 1U])) {
    range.end--;
  }
  return range;
}

static Line line_at(const u8* source, u16 size, u16 offset) {
  Line line = {offset, offset, offset};
  while(line.end < size && source[line.end] != '\r' &&
        source[line.end] != '\n') {
    line.end++;
  }
  line.next = line.end;
  if(line.next < size && source[line.next] == '\r') line.next++;
  if(line.next < size && source[line.next] == '\n') line.next++;
  return line;
}

static u16 find_token(const u8* source, u16 begin, u16 end,
                      const char* token, u8 length) {
  for(u16 offset = begin; offset + length <= end; offset++) {
    if(source[offset] == (u8) token[0] &&
       memcmp(source + offset, token, length) == 0) {
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
    const char* text;
    char value;
  };
  static const Entity entities[] = {
    {"&amp;", '&'}, {"&lt;", '<'}, {"&gt;", '>'}
  };
  for(const Entity& entity : entities) {
    const u16 length = (u16) strlen(entity.text);
    if(offset + length <= end &&
       memcmp(source + offset, entity.text, length) == 0) {
      consumed = length;
      return writer.character(entity.value);
    }
  }
  return false;
}

static bool strip_inline(Writer& writer, const u8* source,
                         u16 begin, u16 end, u8 depth);

static bool strip_code(Writer& writer, const u8* source,
                       u16& offset, u16 end) {
  u8 run = 0;
  while(offset + run < end && source[offset + run] == '`' && run < 8) {
    run++;
  }
  const u16 close = find_token(
      source, (u16) (offset + run), end, (const char*) source + offset, run);
  if(run == 0 || close == end) return false;
  Range content = {(u16) (offset + run), close};
  if(content.end > content.begin + 1U &&
     source[content.begin] == ' ' && source[content.end - 1U] == ' ') {
    content.begin++;
    content.end--;
  }
  if(!writer.text(source + content.begin,
                  (u16) (content.end - content.begin))) {
    return false;
  }
  offset = (u16) (close + run);
  return true;
}

static bool strip_link(Writer& writer, const u8* source,
                       u16& offset, u16 end, u8 depth, bool image) {
  const u16 open = image ? (u16) (offset + 1U) : offset;
  if(open >= end || source[open] != '[') return false;
  const u16 close_label = find_token(
      source, (u16) (open + 1U), end, "]", 1);
  if(close_label == end || close_label + 1U >= end ||
     source[close_label + 1U] != '(') {
    return false;
  }
  const u16 close_path = find_token(
      source, (u16) (close_label + 2U), end, ")", 1);
  if(close_path == end) return false;

  Range path = trim(source, {(u16) (close_label + 2U), close_path});
  if(path.end > path.begin + 1U && source[path.begin] == '<' &&
     source[path.end - 1U] == '>') {
    path.begin++;
    path.end--;
  }
  if(path.begin == path.end) return false;

  const Range label = {(u16) (open + 1U), close_label};
  if(image) {
    if(label.begin != label.end) {
      if(!writer.text(source + label.begin,
                      (u16) (label.end - label.begin))) {
        return false;
      }
    } else {
      u16 name = path.begin;
      for(u16 index = path.begin; index < path.end; index++) {
        if(source[index] == '/' || source[index] == '\\') {
          name = (u16) (index + 1U);
        }
      }
      if(!writer.text(source + name, (u16) (path.end - name))) return false;
    }
  } else if(!strip_inline(
                writer, source, label.begin, label.end,
                (u8) (depth + 1U))) {
    return false;
  }
  offset = (u16) (close_path + 1U);
  return true;
}

static bool strip_delimited(Writer& writer, const u8* source,
                            u16& offset, u16 end, u8 depth,
                            const char* delimiter, u8 length) {
  if(offset + length >= end ||
     memcmp(source + offset, delimiter, length) != 0) {
    return false;
  }
  const u16 close = find_token(
      source, (u16) (offset + length), end, delimiter, length);
  if(close == end || close == offset + length) return false;
  if(!strip_inline(writer, source, (u16) (offset + length), close,
                   (u8) (depth + 1U))) {
    return false;
  }
  offset = (u16) (close + length);
  return true;
}

static bool strip_inline(Writer& writer, const u8* source,
                         u16 begin, u16 end, u8 depth) {
  if(depth > 6) return writer.text(source + begin, (u16) (end - begin));
  u16 offset = begin;
  while(offset < end) {
    if(source[offset] == '\\' && offset + 1U < end &&
       punctuation(source[offset + 1U])) {
      if(!writer.text(source + offset + 1U, 1)) return false;
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
       strip_code(writer, source, offset, end)) {
      continue;
    }
    if(source[offset] == '!' &&
       strip_link(writer, source, offset, end, depth, true)) {
      continue;
    }
    if(source[offset] == '[' &&
       strip_link(writer, source, offset, end, depth, false)) {
      continue;
    }
    const char* delimiter = nullptr;
    u8 length = 0;
    if(offset + 1U < end &&
       ((source[offset] == '*' && source[offset + 1U] == '*') ||
        (source[offset] == '_' && source[offset + 1U] == '_') ||
        (source[offset] == '~' && source[offset + 1U] == '~'))) {
      delimiter = (const char*) source + offset;
      length = 2;
    } else if(source[offset] == '*' || source[offset] == '_') {
      delimiter = (const char*) source + offset;
      length = 1;
    }
    if(delimiter != nullptr &&
       strip_delimited(writer, source, offset, end, depth,
                       delimiter, length)) {
      continue;
    }
    if(!writer.text(source + offset, 1)) return false;
    offset++;
  }
  return true;
}

enum class LineKind : u8 {
  BLANK,
  PLAIN,
  HEADING,
  QUOTE,
  LIST,
  RULE,
  FENCE
};

struct LineInfo {
  LineKind kind;
  Range content;
  u8 marker;
  u8 marker_count;
  u8 depth;
  bool ordered;
  u16 ordinal;
};

static LineInfo inspect_line(const u8* source, Range whole) {
  LineInfo result = {
    LineKind::PLAIN, trim(source, whole), 0, 0, 0, false, 0
  };
  if(result.content.begin == result.content.end) {
    result.kind = LineKind::BLANK;
    return result;
  }

  u16 offset = whole.begin;
  u8 leading = 0;
  while(offset < whole.end && ascii_space(source[offset]) && leading < 12) {
    offset++;
    leading++;
  }

  if(offset < whole.end &&
     (source[offset] == '`' || source[offset] == '~')) {
    result.marker = source[offset];
    while(offset + result.marker_count < whole.end &&
          source[offset + result.marker_count] == result.marker) {
      result.marker_count++;
    }
    if(result.marker_count >= 3) {
      result.kind = LineKind::FENCE;
      return result;
    }
  }

  u16 cursor = offset;
  u8 hashes = 0;
  while(cursor < whole.end && source[cursor] == '#' && hashes < 6) {
    cursor++;
    hashes++;
  }
  if(hashes != 0 &&
     (cursor == whole.end || ascii_space(source[cursor]))) {
    while(cursor < whole.end && ascii_space(source[cursor])) cursor++;
    result.content = trim(source, {cursor, whole.end});
    while(result.content.end > result.content.begin &&
          source[result.content.end - 1U] == '#') {
      result.content.end--;
    }
    result.content = trim(source, result.content);
    result.kind = LineKind::HEADING;
    return result;
  }

  cursor = whole.begin;
  u8 quote_depth = 0;
  while(cursor < whole.end && quote_depth < 3) {
    u8 spaces = 0;
    while(cursor < whole.end && source[cursor] == ' ' && spaces < 3) {
      cursor++;
      spaces++;
    }
    if(cursor >= whole.end || source[cursor] != '>') break;
    cursor++;
    quote_depth++;
    if(cursor < whole.end && source[cursor] == ' ') cursor++;
  }
  if(quote_depth != 0) {
    result.kind = LineKind::QUOTE;
    result.content = {cursor, whole.end};
    return result;
  }

  result.depth = leading / 2U;
  if(result.depth > 3) result.depth = 3;
  cursor = offset;
  if((source[cursor] == '-' || source[cursor] == '+' ||
      source[cursor] == '*') &&
     cursor + 1U < whole.end && ascii_space(source[cursor + 1U])) {
    cursor = (u16) (cursor + 2U);
    result.kind = LineKind::LIST;
  } else if(source[cursor] >= '0' && source[cursor] <= '9') {
    u32 ordinal = 0;
    u8 digits = 0;
    while(cursor < whole.end && source[cursor] >= '0' &&
          source[cursor] <= '9' && digits < 5) {
      ordinal = ordinal * 10U + (u8) (source[cursor] - '0');
      cursor++;
      digits++;
    }
    if(ordinal <= 0xFFFFU && cursor + 1U < whole.end &&
       (source[cursor] == '.' || source[cursor] == ')') &&
       ascii_space(source[cursor + 1U])) {
      cursor = (u16) (cursor + 2U);
      result.kind = LineKind::LIST;
      result.ordered = true;
      result.ordinal = (u16) ordinal;
    }
  }
  if(result.kind == LineKind::LIST) {
    while(cursor < whole.end && ascii_space(source[cursor])) cursor++;
    result.content = {cursor, whole.end};
    return result;
  }

  u8 rule_marker = 0;
  u8 rule_count = 0;
  bool rule = true;
  for(u16 index = result.content.begin; index < result.content.end; index++) {
    const u8 value = source[index];
    if(ascii_space(value)) continue;
    if(value != '*' && value != '-' && value != '_') {
      rule = false;
      break;
    }
    if(rule_marker == 0) rule_marker = value;
    if(value != rule_marker) {
      rule = false;
      break;
    }
    rule_count++;
  }
  if(rule && rule_count >= 3) result.kind = LineKind::RULE;
  return result;
}

static bool setext_line(const u8* source, Range whole) {
  const Range value = trim(source, whole);
  if(value.end - value.begin != 3) return false;
  const u8 marker = source[value.begin];
  return (marker == '=' || marker == '-') &&
         source[value.begin + 1U] == marker &&
         source[value.begin + 2U] == marker;
}

static bool closes_fence(const u8* source, Range whole,
                         u8 marker, u8 minimum) {
  const Range value = trim(source, whole);
  u8 count = 0;
  while(value.begin + count < value.end &&
        source[value.begin + count] == marker) {
    count++;
  }
  if(count < minimum) return false;
  for(u16 index = (u16) (value.begin + count);
      index < value.end; index++) {
    if(!ascii_space(source[index])) return false;
  }
  return true;
}

static Range hard_break_content(const u8* source, Range whole,
                                bool& hard_break) {
  hard_break = false;
  u16 end = whole.end;
  u8 spaces = 0;
  while(end > whole.begin && source[end - 1U] == ' ') {
    end--;
    spaces++;
  }
  if(spaces >= 2) {
    hard_break = true;
  } else if(end > whole.begin && source[end - 1U] == '\\') {
    hard_break = true;
    end--;
  }
  return trim(source, {whole.begin, end});
}

static bool append_number(Writer& writer, u16 value) {
  char digits[6];
  u8 count = 0;
  do {
    digits[count++] = (char) ('0' + value % 10U);
    value /= 10U;
  } while(value != 0);
  while(count != 0) {
    if(!writer.character(digits[--count])) return false;
  }
  return true;
}

static bool emit_inline(Writer& writer, const u8* source, Range content) {
  return strip_inline(writer, source, content.begin, content.end, 0) &&
         writer.newline();
}

static bool convert_document(Writer& writer,
                             const u8* source, u16 size) {
  u16 offset = 0;
  while(offset < size) {
    const Line line = line_at(source, size, offset);
    const Range whole = {line.begin, line.end};
    const LineInfo info = inspect_line(source, whole);

    if(info.kind == LineKind::BLANK || info.kind == LineKind::RULE) {
      if(!writer.paragraph_gap() || !writer.newline()) return false;
      offset = line.next;
      continue;
    }
    if(info.kind == LineKind::HEADING ||
       info.kind == LineKind::QUOTE) {
      if(!emit_inline(writer, source, info.content)) return false;
      offset = line.next;
      continue;
    }
    if(info.kind == LineKind::LIST) {
      for(u8 depth = 0; depth < info.depth; depth++) {
        if(!writer.literal("  ")) return false;
      }
      if(info.ordered) {
        if(!append_number(writer, info.ordinal) ||
           !writer.literal(". ")) {
          return false;
        }
      } else if(!writer.literal("- ")) {
        return false;
      }
      if(!emit_inline(writer, source, info.content)) return false;
      offset = line.next;
      continue;
    }
    if(info.kind == LineKind::FENCE) {
      offset = line.next;
      bool first = true;
      while(offset < size) {
        const Line code = line_at(source, size, offset);
        const Range code_range = {code.begin, code.end};
        if(closes_fence(
             source, code_range, info.marker, info.marker_count)) {
          offset = code.next;
          break;
        }
        if(!first && !writer.newline()) return false;
        if(!writer.text(source + code.begin,
                        (u16) (code.end - code.begin))) {
          return false;
        }
        first = false;
        offset = code.next;
      }
      if(!writer.newline()) return false;
      continue;
    }

    const Line next = line.next < size
        ? line_at(source, size, line.next)
        : Line{size, size, size};
    if(next.begin < size &&
       setext_line(source, {next.begin, next.end})) {
      if(!emit_inline(writer, source, trim(source, whole))) return false;
      offset = next.next;
      continue;
    }

    Line paragraph = line;
    while(true) {
      bool hard_break = false;
      const Range content = hard_break_content(
          source, {paragraph.begin, paragraph.end}, hard_break);
      if(!strip_inline(writer, source, content.begin, content.end, 0)) {
        return false;
      }
      offset = paragraph.next;
      if(offset >= size) break;
      const Line candidate = line_at(source, size, offset);
      if(inspect_line(
           source, {candidate.begin, candidate.end}).kind !=
         LineKind::PLAIN) {
        break;
      }
      if(hard_break ? !writer.newline() : !writer.character(' ')) {
        return false;
      }
      paragraph = candidate;
    }
    if(!writer.newline()) return false;
  }
  return true;
}

} // namespace

Status convert(const u8* source, u16 source_size,
               char* output, u16 output_capacity, u16& output_size) {
  output_size = 0;
  if(source == nullptr || output == nullptr || output_capacity == 0) {
    return Status::INVALID_ARGUMENT;
  }
  if(source_size > MAX_SOURCE_SIZE) return Status::SOURCE_TOO_LARGE;

  Writer writer(output, output_capacity);
  if(!convert_document(writer, source, source_size) || !writer.ok()) {
    return Status::OUTPUT_TOO_SMALL;
  }
  writer.finish();
  output_size = writer.size();
  return Status::OK;
}

} // namespace markdown_plain

#endif
