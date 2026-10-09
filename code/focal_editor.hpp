#ifndef MK61_COMPACT_FOCAL_EDITOR_HPP
#define MK61_COMPACT_FOCAL_EDITOR_HPP
#include "focal_syntax.hpp"
#include "language_bytecode.hpp"
#include "text_editor.hpp"
#include <stdio.h>
namespace focal_editor {
using namespace text_editor;
inline bool operator_field(const char *s, u16 cursor) {
  unsigned start = cursor;
  while (start && s[start - 1] != '\n')
    --start;
  const char *p = s + start;
  const char *e = s + cursor;
  focal_next::Address a;
  if (focal_next::address(p, e, a))
    p = focal_next::skip(p, e);
  else
    p = s + start;
  while (p < e) {
    const char *token = p;
    if (focal_next::command(token, e) == focal_next::Command::COMMENT)
      return false;
    const char *next = focal_next::delimiter(p, e, ';');
    if (next == e)
      break;
    p = next + 1;
  }
  return focal_next::skip(p, e) == e;
}
inline const char *insert(Shift shift, i32 code, const char *source, u16 cursor,
                          void *) {
  const auto &k = keyboard_layout::active();
  // The shared punctuation map takes priority over K+operator shortcuts.
  if (shift == Shift::NONE && code == k.dot) {
    unsigned start = cursor;
    while (start && source[start - 1] != '\n' && source[start - 1] != '\r')
      --start;
    const char *p = source + start;
    const char *e = source + cursor;
    focal_next::Address a;
    if (focal_next::address(p, e, a) && !a.exact && p == e)
      return ".";
  }
  if (shift == Shift::K) {
    const char *punctuation = kshift_text_for_key(code);
    if (punctuation)
      return punctuation;
  }
  if (shift == Shift::K ||
      (shift == Shift::NONE && operator_field(source, cursor))) {
    if (code == k.dot)
      return "ASK ";
    if (code == k.neg)
      return "IF ";
    if (code == k.power)
      return "COMMENT ";
    if (code == k.bx)
      return "EXIT";
    if (code == k.mul)
      return "FOR ";
    if (code == k.degree)
      return "GOTO ";
    if (code == k.radian)
      return "PRINT ";
    if (code == k.x_to_p)
      return "SET ";
    if (code == k.ret)
      return "RETURN";
    if (shift == Shift::K && code == k.cx)
      return "DO ";
  }
  if (shift == Shift::NONE)
    return plain_text_for_key(code);
  return nullptr;
}
struct Token {
  u16 begin, end;
};
inline bool token_at(const char *s, u16 len, u16 pos, Token &token) {
  const char *p = s;
  const char *e = s + len;
  while (p < e) {
    const char *line_end = p;
    while (line_end < e && *line_end != '\n')
      ++line_end;
    const char *b = p;
    focal_next::Address a;
    if (focal_next::address(b, line_end, a) && a.exact) {
      while (b < line_end) {
        b = focal_next::skip(b, line_end);
        const char *word = b;
        auto c = focal_next::command(b, line_end);
        if (c == focal_next::Command::NONE)
          break;
        const char *token_end = b;
        while (token_end < line_end && focal_next::space(*token_end))
          ++token_end;
        if (pos >= unsigned(word - s) && pos <= unsigned(token_end - s)) {
          const char *tail = b;
          while (tail < line_end && focal_next::space(*tail))
            ++tail;
          token = {u16(word - s), u16(tail - s)};
          return true;
        }
        if (c == focal_next::Command::COMMENT)
          break;
        b = focal_next::delimiter(b, line_end, ';');
        if (b < line_end)
          ++b;
      }
    }
    p = line_end + (line_end < e);
  }
  return false;
}
inline bool move(const char *source, u16 length, u16 &cursor, int delta,
                 void *) {
  Token token;
  if (token_at(source, length, cursor, token)) {
    if (delta < 0 && cursor > token.begin && cursor <= token.end) {
      cursor = token.begin;
      return true;
    }
    if (delta > 0 && cursor >= token.begin && cursor < token.end) {
      cursor = token.end;
      return true;
    }
  }
  return delta < 0 ? move_cursor_left(source, cursor)
                   : move_cursor_right(source, length, cursor);
}
inline bool erase(char *source, u16 &length, u16 &cursor, u16 capacity,
                  void *) {
  Token token;
  if (token_at(source, length, cursor, token) && cursor > token.begin &&
      cursor <= token.end)
    return replace_range(source, length, cursor, capacity, token.begin,
                         token.end, "");
  return backspace(source, length, cursor);
}
// A macro wraps the complete current expression item before the cursor.
// Commas inside calls and the IF condition do not split that expression.
inline bool macro(char *s, u16 &len, u16 &cursor, u16 capacity, i32 code,
                  void *) {
  const auto &k = keyboard_layout::active();
  int digit = keyboard_layout::digit_from_key(k, code);
  const char *name = nullptr;
  bool square = code == k.mul, inverse = code == k.div, power10 = digit == 0;
  if (code == k.sub)
    name = "SQRT";
  else if (code == k.neg)
    name = "ABS";
  else if (digit >= 1 && digit <= 9) {
    static const char *names[] = {"EXP", "LG",  "LN",  "ASIN", "ACOS",
                                  "ATG", "SIN", "COS", "TG"};
    name = names[digit - 1];
  }
  if (!name && !square && !inverse && !power10)
    return false;
  unsigned end = cursor;
  while (end && focal_next::space(s[end - 1]))
    --end;
  if (!end)
    return false;
  unsigned begin = end;
  while (begin && s[begin - 1] != '\n' && s[begin - 1] != '\r')
    --begin;
  const char *p = s + begin;
  const char *e = s + end;
  focal_next::Address address;
  const char *after_address = p;
  bool numbered =
      focal_next::address(after_address, e, address) && address.exact;
  if (numbered)
    p = focal_next::skip(after_address, e);
  bool after_statement = false;
  while (p < e) {
    const char *next = focal_next::delimiter(p, e, ';');
    if (next == e)
      break;
    p = next + 1;
    after_statement = true;
  }
  const char *word = focal_next::skip(p, e);
  const char *after = word;
  auto command = focal_next::command(after, e);
  const bool explicit_command = numbered || after_statement || after - word > 1;
  if (explicit_command && command != focal_next::Command::NONE)
    p = focal_next::skip(after, e);
  else {
    if (numbered)
      return false;
    p = word;
    command = focal_next::Command::NONE;
  }
  if (command == focal_next::Command::COMMENT ||
      command == focal_next::Command::ASK ||
      command == focal_next::Command::GOTO ||
      command == focal_next::Command::EXIT)
    return false;
  unsigned atoms[32] = {unsigned(p - s)}, depth = 0;
  char quote = 0;
  for (const char *n = p; n < e; ++n) {
    if (quote) {
      if (*n == quote)
        quote = 0;
      continue;
    }
    if (*n == '"' || *n == '\'') {
      quote = *n;
      continue;
    }
    if (*n == '(') {
      if (depth == 31)
        return false;
      atoms[++depth] = unsigned(n - s) + 1;
    } else if (*n == ')') {
      if (!depth)
        return false;
      --depth;
    } else if (*n == '=' || *n == ',')
      atoms[depth] = unsigned(n - s) + 1;
  }
  if (quote)
    return false;
  unsigned atom = atoms[depth];
  while (atom < end && focal_next::space(s[atom]))
    ++atom;
  if (atom == end || end - atom >= 112)
    return false;
  char expression[112], replacement[120];
  memcpy(expression, s + atom, end - atom);
  expression[end - atom] = 0;
  if (!language_vm::validate_focal_expression(expression,
                                              (uint16_t)(end - atom)))
    return false;
  // Reject an operator or a quoted item: F+digit must then insert a symbol.
  bool compound = false;
  unsigned nesting = 0;
  for (const char *n = expression; *n; ++n) {
    if (*n == '(')
      ++nesting;
    else if (*n == ')' && nesting)
      --nesting;
    else if (!nesting &&
             (*n == '+' || *n == '-' || *n == '*' || *n == '/' || *n == '^'))
      compound = true;
  }
  if (square)
    snprintf(replacement, sizeof(replacement), compound ? "(%s)^2" : "%s^2",
             expression);
  else if (inverse)
    snprintf(replacement, sizeof(replacement), compound ? "1/(%s)" : "1/%s",
             expression);
  else if (power10)
    snprintf(replacement, sizeof(replacement), compound ? "10^(%s)" : "10^%s",
             expression);
  else
    snprintf(replacement, sizeof(replacement), "%s(%s)", name, expression);
  return replace_range(s, len, cursor, capacity, u16(atom), u16(end),
                       replacement);
}
inline KeyResult handle(Buffer &editor, const char *enter, i32 code, u32 now) {
  const auto &k = keyboard_layout::active();
  if ((code == k.left) && editor.shift == Shift::ALPHA) {
    editor.shift = Shift::NONE;
    sms_reset(editor.sms);
    return KeyResult::DIRTY;
  }
  // Insert missing separator after a manually typed line number before a word.
  if (editor.shift != Shift::ALPHA &&
      operator_field(editor.source, editor.cursor) && editor.cursor &&
      focal_next::digit(editor.source[editor.cursor - 1])) {
    const char *text =
        insert(editor.shift, code, editor.source, editor.cursor, nullptr);
    if (text && focal_next::alpha(*text) &&
        !insert_text(editor.source, editor.len, editor.cursor, editor.capacity,
                     " "))
      return KeyResult::NONE;
  }
  const KeyMap keys = {k.left, k.left,  k.right, k.right,    k.ok,
                       k.ok,   k.esc,   k.esc,   k.shg_left, k.shg_right,
                       k.k,    k.alpha, k.pp};
  const Hooks hooks = {insert, macro, move, erase, nullptr};
  const Options options = {enter, true, true, true, true, k.cx};
  return handle_key(editor, keys, hooks, options, code, now);
}
} // namespace focal_editor
#endif
