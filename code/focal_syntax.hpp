#ifndef MK61_COMPACT_FOCAL_SYNTAX_HPP
#define MK61_COMPACT_FOCAL_SYNTAX_HPP
// Shared lexical rules for the new VM frontend and keyboard editor.
// No dependence on the previous FOCAL implementation.
#include "mk_math.hpp"
#include <stdint.h>
#include <string.h>
namespace focal_next {
enum class Error : uint8_t {
  NONE,
  SYNTAX,
  LINE,
  FULL,
  VAR,
  FUNC,
  FOR,
  RETURN,
  STACK,
  MATH,
  IO,
  STOPPED
};
enum class Command : uint8_t {
  NONE,
  ASK,
  IF,
  COMMENT,
  DO,
  EXIT,
  FOR,
  GOTO,
  PRINT,
  RETURN,
  SET,
  EXEC,
  CLS
};
enum class Function : uint8_t {
  SIN,
  COS,
  TG,
  ASIN,
  ACOS,
  ATG,
  LN,
  LG,
  EXP,
  SQRT,
  ABS,
  INT,
  FRAC,
  ROUND,
  SGN,
  MAX,
  MIN,
  MOD,
  RND,
  PI_VALUE,
  CALL,
  ARG
};
struct Word {
  const char *name;
  uint8_t id;
  char short_name;
};
static const Word commands[] = {
    {"ASK", 1, 'A'},  {"IF", 2, 'B'},    {"COMMENT", 3, 'C'},
    {"DO", 4, 'D'},   {"EXIT", 5, 'E'},  {"FOR", 6, 'F'},
    {"GOTO", 7, 'G'}, {"PRINT", 8, 'P'}, {"RETURN", 9, 'R'},
    {"SET", 10, 'S'}, {"EXEC", 11, 'X'}, {"CLS", 12, 0}};
static const Word functions[] = {
    {"SIN", 0, 0},   {"COS", 1, 0},    {"TG", 2, 0},   {"ASIN", 3, 0},
    {"ACOS", 4, 0},  {"ATG", 5, 0},    {"LN", 6, 0},   {"LG", 7, 0},
    {"EXP", 8, 0},   {"SQRT", 9, 0},   {"ABS", 10, 0}, {"INT", 11, 0},
    {"FRAC", 12, 0}, {"ROUND", 13, 0}, {"SGN", 14, 0}, {"MAX", 15, 0},
    {"MIN", 16, 0},  {"MOD", 17, 0},   {"RND", 18, 0}, {"PI", 19, 0},
    {"CALL", 20, 0}, {"ARG", 21, 0}};
inline char upper(char c) {
  return c >= 'a' && c <= 'z' ? char(c - 'a' + 'A') : c;
}
inline bool alpha(char c) {
  c = upper(c);
  return c >= 'A' && c <= 'Z';
}
inline bool digit(char c) { return c >= '0' && c <= '9'; }
inline bool space(char c) { return c == ' ' || c == '\t' || c == '\r'; }
inline const char *skip(const char *p, const char *e) {
  while (p < e && space(*p))
    ++p;
  return p;
}
inline bool equal(const char *p, const char *e, const char *word) {
  while (p < e && *word && upper(*p) == *word) {
    ++p;
    ++word;
  }
  return p == e && !*word;
}
inline Command command(const char *&p, const char *e) {
  p = skip(p, e);
  const char *b = p;
  while (p < e && alpha(*p))
    ++p;
  for (const auto &w : commands)
    if (equal(b, p, w.name) || (p - b == 1 && upper(*b) == w.short_name))
      return Command(w.id);
  return Command::NONE;
}
inline const char *command_name(Command c) {
  return c == Command::NONE ? "" : commands[unsigned(c) - 1].name;
}
// Top-level delimiters, never delimiters inside a literal or an expression.
inline const char *delimiter(const char *p, const char *e, char c) {
  unsigned depth = 0;
  char quote = 0;
  for (; p < e; ++p) {
    if (quote) {
      if (*p == quote)
        quote = 0;
      continue;
    }
    if (*p == '"' || *p == '\'') {
      quote = *p;
      continue;
    }
    if (*p == '(')
      ++depth;
    else if (*p == ')' && depth)
      --depth;
    else if (!depth && *p == c)
      return p;
  }
  return e;
}
struct Address {
  uint16_t major, minor;
  bool exact;
};
inline uint32_t key(Address a) { return uint32_t(a.major) * 1000 + a.minor; }
inline bool address(const char *&p, const char *e, Address &a) {
  p = skip(p, e);
  a = {0, 0, false};
  if (p == e || !digit(*p))
    return false;
  unsigned n = 0;
  do {
    n = n * 10 + unsigned(*p++ - '0');
    if (n > 999)
      return false;
  } while (p < e && digit(*p));
  a.major = uint16_t(n);
  if (p < e && *p == '.') {
    ++p;
    a.exact = true;
    if (p == e || !digit(*p))
      return false;
    n = 0;
    do {
      n = n * 10 + unsigned(*p++ - '0');
      if (n > 999)
        return false;
    } while (p < e && digit(*p));
    a.minor = uint16_t(n);
  }
  return a.major != 0;
}
} // namespace focal_next
#endif
