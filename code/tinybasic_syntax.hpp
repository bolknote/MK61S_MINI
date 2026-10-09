#ifndef MK61_TINYBASIC_SYNTAX_HPP
#define MK61_TINYBASIC_SYNTAX_HPP
// Shared lexical rules for both BASIC frontends. Quoted text and parentheses
// cannot contain branch markers or declarative DATA commands.
namespace tinybasic_syntax {
inline bool alpha(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
inline char upper(char c) { return c >= 'a' && c <= 'z' ? (char)(c - 'a' + 'A') : c; }
inline const char* skip(const char* p, const char* end) {
  while (p < end && (*p == ' ' || *p == '\t')) ++p;
  return p;
}
inline const char* integer(const char* p, const char* end, unsigned& value) {
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
inline const char* print_precision(const char* p, const char* end,
                                   unsigned& width, unsigned& digits) {
  if (p == end || *p != '#') return nullptr;
  p = integer(p + 1, end, width);
  if (!p || p == end || *p != ':') return nullptr;
  return integer(p + 1, end, digits);
}
inline const char* parameter_separator(const char* p, const char* end) {
  unsigned depth = 0;
  while (p < end) {
    if (*p == '(') ++depth;
    else if (*p == ')' && depth) --depth;
    else if (*p == ',' && !depth) return p;
    ++p;
  }
  return end;
}
inline bool word(const char* p, const char* end, const char* name, unsigned minimum,
                 const char** after = nullptr) {
  if (p >= end || !alpha(*p)) return false;
  const char* start = p;
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
inline const char* find(const char* p, const char* end, bool branch, const char** after = nullptr) {
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
    const char* token = p;
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
inline const char* else_at(const char* p, const char* end, const char** after = nullptr) {
  return find(p, end, true, after);
}
inline const char* data_at(const char* p, const char* end, const char** after = nullptr) {
  return find(p, end, false, after);
}
}  // namespace tinybasic_syntax
#endif
