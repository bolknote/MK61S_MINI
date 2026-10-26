#ifndef MK61_COMPACT_FOCAL_EDITOR_HPP
#define MK61_COMPACT_FOCAL_EDITOR_HPP
#include "focal_syntax.hpp"
#include "focal_text.hpp"
#include "language_bytecode.hpp"
#include "text_editor.hpp"
#include <stdio.h>
namespace focal_editor {
using namespace text_editor;
struct Context {focal_text::InitialLine initial;bool field;bool macro_blocked=false;};
template<class Text>
inline bool operator_field(Text s, u16 cursor) {
  unsigned start = cursor;
  while (start && s[start-1]!='\n' && s[start-1]!='\r')
    --start;
  Text p = s + start;
  Text e = s + cursor;
  focal_next::Address a;
  if (focal_next::address(p, e, a))
    p = focal_next::skip(p, e);
  else
    p = s + start;
  while (p < e) {
    Text token = p;
    if (focal_next::command(token, e) == focal_next::Command::COMMENT)
      return false;
    auto next = focal_next::delimiter(p, e, ';');
    if (next == e)
      break;
    p = next + 1;
  }
  return focal_next::skip(p, e) == e;
}
inline bool context_field(const char* source,u16 cursor,const focal_text::InitialLine& initial) {
  const char* end=source+cursor;
  if(!initial.fragment || memchr(source,'\n',cursor) || memchr(source,'\r',cursor))return operator_field(source,cursor);
  bool statement=false;
  const char* p=focal_text::resume(source,end,initial,&statement);
  if(!statement)return false;
  while(p<end) {
    const char* token=p;
    if(focal_next::command(token,end)==focal_next::Command::COMMENT)return false;
    const char* next=focal_next::delimiter(p,end,';');if(next==end)break;
    p=next+1;
  }
  return focal_next::skip(p,end)==end;
}
inline bool context_literal(const char* source,u16 cursor,const focal_text::InitialLine& initial) {
  bool comment=initial.comment;
  char quote=initial.quote;
  for(unsigned i=0;i<cursor;++i) {
    const char ch=source[i];
    if(ch=='\n'||ch=='\r') {comment=false;quote=0;}
    else if(!comment) {
      if(quote) {if(ch==quote)quote=0;}
      else if(ch=='\"'||ch=='\'')quote=ch;
    }
  }
  return comment || quote;
}
inline const char *insert(Shift shift, i32 code, const char *source, u16 cursor,
                          void *context) {
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
      (shift == Shift::NONE && (context?((Context*)context)->field:operator_field(source, cursor)))) {
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
inline bool token_at(const char *s,u16 len,u16 pos,Token& token,const Context* context=nullptr) {
  bool found=false;
  focal_text::visit(s,len,[&](focal_text::Token word){
    unsigned end=word.end;
    while(end<len && focal_next::space(s[end]) && s[end]!='\r' && s[end]!='\n')++end;
    if(pos>=word.begin && pos<=end) {token={u16(word.begin),u16(end)};found=true;return false;}
    return true;
  },context?&context->initial:nullptr);
  return found;
}
inline bool move(const char *source, u16 length, u16 &cursor, int delta,
                 void *context) {
  Token token;
  if (token_at(source, length, cursor, token,(Context*)context)) {
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
                  void *context) {
  Token token;
  if (token_at(source, length, cursor, token,(Context*)context) && cursor > token.begin &&
      cursor <= token.end)
    return replace_range(source, length, cursor, capacity, token.begin,
                         token.end, "");
  return backspace(source, length, cursor);
}
// A macro wraps the complete current expression item before the cursor.
// Commas inside calls and the IF condition do not split that expression.
inline bool macro(char *s, u16 &len, u16 &cursor, u16 capacity, i32 code,
                  void *context) {
  if(context && ((Context*)context)->macro_blocked)return false;
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
    auto next = focal_next::delimiter(p, e, ';');
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
inline KeyResult handle(Buffer &editor, const char *enter, i32 code, u32 now,Context* context=nullptr) {
  const auto &k = keyboard_layout::active();
  if ((code == k.left) && editor.shift == Shift::ALPHA) {
    editor.shift = Shift::NONE;
    sms_reset(editor.sms);
    return KeyResult::DIRTY;
  }
  // Insert missing separator after a manually typed line number before a word.
  if (editor.shift != Shift::ALPHA &&
      (context?context->field:operator_field(editor.source, editor.cursor)) && editor.cursor &&
      focal_next::digit(editor.source[editor.cursor - 1])) {
    const char *text =
        insert(editor.shift, code, editor.source, editor.cursor, context);
    if (text && focal_next::alpha(*text) &&
        !insert_text(editor.source, editor.len, editor.cursor, editor.capacity,
                     " "))
      return KeyResult::NONE;
  }
  const KeyMap keys = {k.left, k.left,  k.right, k.right,    k.ok,
                       k.ok,   k.esc,   k.esc,   k.shg_left, k.shg_right,
                       k.k,    k.alpha, k.pp};
  const Hooks hooks = {insert, macro, move, erase, context};
  const Options options = {enter, true, true, true, true, k.cx};
  return handle_key(editor, keys, hooks, options, code, now);
}
} // namespace focal_editor
#endif
