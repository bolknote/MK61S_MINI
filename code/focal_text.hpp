#ifndef MK61_FOCAL_TEXT_HPP
#define MK61_FOCAL_TEXT_HPP
#include "focal_syntax.hpp"
#include <string.h>
namespace focal_text {
// Recognize only statement positions. Quoted text, function arguments and the
// complete tail of COMMENT are never rewritten. Invalid drafts remain editable.
struct Token {
  unsigned begin, end;
  focal_next::Command command;
};
template <class Visitor>
inline bool visit(const char *source, unsigned length, Visitor visitor) {
  const char *p = source;
  const char *end = source + length;
  while (p < end) {
    const char *line_end = p;
    while (line_end < end && *line_end != '\n' && *line_end != '\r')
      ++line_end;
    const char *word = p;
    focal_next::Address address;
    if (focal_next::address(word, line_end, address) && address.exact) {
      while (word < line_end) {
        word = focal_next::skip(word, line_end);
        const char *begin = word;
        auto command = focal_next::command(word, line_end);
        if (command == focal_next::Command::NONE)
          break;
        if (!visitor(Token{unsigned(begin - source), unsigned(word - source),
                           command}))
          return false;
        if (command == focal_next::Command::COMMENT)
          break;
        word = focal_next::delimiter(word, line_end, ';');
        if (word < line_end)
          ++word;
      }
    }
    p = line_end;
    while (p < end && (*p == '\n' || *p == '\r'))
      ++p;
  }
  return true;
}
inline const char *spelling(focal_next::Command command, bool expand,
                            char (&short_name)[2]) {
  const auto &word = focal_next::commands[unsigned(command) - 1];
  if (expand || !word.short_name)
    return word.name;
  short_name[0] = word.short_name;
  short_name[1] = 0;
  return short_name;
}
inline bool expanded_size(const char *source, unsigned length,
                          unsigned capacity, unsigned &result,
                          bool expand = true) {
  result = length;
  return visit(source, length,
               [&](Token t) {
                 char short_name[2];
                 unsigned n =
                     (unsigned)strlen(spelling(t.command, expand, short_name));
                 result = result - (t.end - t.begin) + n;
                 return result < capacity;
               }) &&
         result < capacity;
}
inline bool transform(char *source, unsigned capacity, bool expand) {
  if (!source || !capacity)
    return false;
  unsigned length = 0;
  while (length < capacity && source[length])
    ++length;
  if (length == capacity)
    return false;
  unsigned needed;
  if (!expanded_size(source, length, capacity, needed, expand))
    return false;
  // Preflight above makes failure atomic. A bounded token directory is not
  // retained: each edit resumes scanning past the replaced word.
  unsigned search = 0;
  while (search < length) {
    Token found = {};
    bool have = false;
    visit(source, length, [&](Token t) {
      if (t.begin < search)
        return true;
      found = t;
      have = true;
      return false;
    });
    if (!have)
      break;
    char short_name[2];
    const char *replacement = spelling(found.command, expand, short_name);
    unsigned n = (unsigned)strlen(replacement), old = found.end - found.begin;
    memmove(source + found.begin + n, source + found.end,
            length - found.end + 1);
    memcpy(source + found.begin, replacement, n);
    length = length - old + n;
    search = found.begin + n;
  }
  return true;
}
inline bool editor_copy(const char *source, char *output, unsigned capacity) {
  if (!source || !output || !capacity)
    return false;
  unsigned length = (unsigned)strlen(source), needed;
  if (!expanded_size(source, length, capacity, needed))
    return false;
  memmove(output, source, length + 1);
  return transform(output, capacity, true);
}
} // namespace focal_text
#endif
