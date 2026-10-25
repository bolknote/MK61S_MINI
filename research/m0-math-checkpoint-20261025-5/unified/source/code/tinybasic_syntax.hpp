#ifndef MK61_TINYBASIC_SYNTAX_HPP
#define MK61_TINYBASIC_SYNTAX_HPP
// Shared lexical rules for both BASIC frontends. Quoted text and parentheses
// cannot contain branch markers or declarative DATA commands.
namespace tinybasic_syntax {
inline bool alpha(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
inline char upper(char c) { return c >= 'a' && c <= 'z' ? (char)(c - 'a' + 'A') : c; }
template <typename Cursor>
inline Cursor skip(Cursor p, Cursor end) {
  while (p < end && (*p == ' ' || *p == '\t')) ++p;
  return p;
}
template <typename Cursor>
inline Cursor integer(Cursor p, Cursor end, unsigned& value) {
  p = skip(p, end); value = 0;
  if (p == end || *p < '0' || *p > '9') return nullptr;
  do {
    if (value < 65536) value = value * 10 + unsigned(*p - '0');
    ++p;
  } while (p < end && *p >= '0' && *p <= '9');
  return skip(p, end);
}
// A literal #width:digits is distinct from the existing #expression. In
// particular #8:A=3 still ends PRINT at the ordinary command separator.
template <typename Cursor>
inline Cursor print_precision(Cursor p, Cursor end,
                                   unsigned& width, unsigned& digits) {
  if (p == end || *p != '#') return nullptr;
  p = integer(p + 1, end, width);
  if (!p || p == end || *p != ':') return nullptr;
  return integer(p + 1, end, digits);
}
template <typename Cursor>
inline Cursor parameter_separator(Cursor p, Cursor end) {
  unsigned depth = 0;
  while (p < end) {
    if (*p == '(') ++depth;
    else if (*p == ')' && depth) --depth;
    else if (*p == ',' && !depth) return p;
    ++p;
  }
  return end;
}
template <typename Cursor>
inline bool word(Cursor p, Cursor end, const char* name, unsigned minimum,
                 Cursor* after = nullptr) {
  if (p >= end || !alpha(*p)) return false;
  Cursor start = p;
  while (p < end && alpha(*p)) ++p;
  const unsigned length = (unsigned)(p - start);
  unsigned full = 0;
  while (name[full]) ++full;
  const bool dotted = p < end && *p == '.';
  if ((!dotted && length != full) || (dotted && (length < minimum || length > full))) return false;
  for (unsigned i = 0; i < length; ++i)
    if (upper(start[i]) != name[i]) return false;
  if (after) *after = p + (dotted ? 1 : 0);
  return true;
}
template <typename Cursor>
inline Cursor find(Cursor p, Cursor end, bool branch, Cursor* after = nullptr) {
  unsigned nested = 0, parentheses = 0;
  char quote = 0;
  while (p < end) {
    if (quote) {
      if (*p == quote) quote = 0;
      ++p;
      continue;
    }
    if (*p == '"' || *p == '\'') {
      quote = *p++;
      continue;
    }
    if (*p == '(') {
      ++parentheses;
      ++p;
      continue;
    }
    if (*p == ')') {
      if (parentheses) --parentheses;
      ++p;
      continue;
    }
    if (parentheses || !alpha(*p)) {
      ++p;
      continue;
    }
    Cursor token = p;
    while (p < end && alpha(*p)) ++p;
    if (p < end && *p == '.') ++p;
    if (word(token, end, "REM", 3) || word(token, end, "REMARK", 3)) return end;
    if (!branch) {
      if (word(token, end, "DATA", 2, after)) return token;
    } else if (word(token, end, "IF", 1)) {
      ++nested;
    } else if (word(token, end, "ELSE", 2, after)) {
      if (!nested) return token;
      --nested;
    }
  }
  return end;
}
template <typename Cursor>
inline Cursor else_at(Cursor p, Cursor end, Cursor* after = nullptr) {
  return find(p, end, true, after);
}
template <typename Cursor>
inline Cursor data_at(Cursor p, Cursor end, Cursor* after = nullptr) {
  return find(p, end, false, after);
}
}  // namespace tinybasic_syntax
#endif
