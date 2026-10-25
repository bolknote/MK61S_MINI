#ifndef MK61_FOCAL_TEXT_HPP
#define MK61_FOCAL_TEXT_HPP
#include "focal_syntax.hpp"
#include <string.h>
namespace focal_text {
// Recognize only statement positions. Quoted text, function arguments and the
// complete tail of COMMENT are never rewritten. Invalid drafts remain editable.
struct InitialLine {
  bool fragment=false,statement=false,comment=false;
  char quote=0;
  unsigned depth=0;
};
template<class Cursor>
inline Cursor resume(Cursor p,Cursor end,InitialLine state,bool* statement=nullptr) {
  if(statement)*statement=state.statement;
  if(state.statement)return p;
  if(state.comment)return end;
  while(p<end) {
    const char ch=*p++;
    if(state.quote) {if(ch==state.quote)state.quote=0;}
    else if(ch=='\"'||ch=='\'')state.quote=ch;
    else if(ch=='(')++state.depth;
    else if(ch==')' && state.depth)--state.depth;
    else if(ch==';' && !state.depth) {if(statement)*statement=true;return p;}
  }
  return end;
}
template<class Cursor>
inline InitialLine initial_line(Cursor source,unsigned offset) {
  InitialLine state;
  unsigned start=offset;
  while(start && source[start-1]!='\n' && source[start-1]!='\r')--start;
  if(start==offset)return state;
  state.fragment=true;
  auto p=source+start,end=source+offset;
  focal_next::Address label;
  if(!focal_next::address(p,end,label) || !label.exact)return state;
  for(;;) {
    p=focal_next::skip(p,end);
    if(p==end) {state.statement=true;return state;}
    const auto command=focal_next::command(p,end);
    if(command==focal_next::Command::NONE)return state;
    if(command==focal_next::Command::COMMENT) {state.comment=true;return state;}
    state.statement=false;
    while(p<end) {
      const char ch=*p++;
      if(state.quote) {if(ch==state.quote)state.quote=0;}
      else if(ch=='\"'||ch=='\'')state.quote=ch;
      else if(ch=='(')++state.depth;
      else if(ch==')' && state.depth)--state.depth;
      else if(ch==';' && !state.depth)break;
    }
    if(p==end) {state.statement=offset && source[offset-1]==';' && !state.quote && !state.depth;return state;}
  }
}
struct Token {
  unsigned begin, end;
  focal_next::Command command;
};
template <class Visitor>
inline bool visit(const char *source, unsigned length, Visitor visitor,const InitialLine* initial=nullptr) {
  const char *p = source;
  const char *end = source + length;
  while (p < end) {
    const char *line_end = p;
    while (line_end < end && *line_end != '\n' && *line_end != '\r')
      ++line_end;
    const char *word = p;
    focal_next::Address address;
    if (p==source && initial && initial->fragment
          ? (word=resume(p,line_end,*initial),true)
          : focal_next::address(word, line_end, address) && address.exact) {
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
                          bool expand = true,const InitialLine* initial=nullptr) {
  result = length;
  return visit(source, length,
               [&](Token t) {
                 char short_name[2];
                 unsigned n =
                     (unsigned)strlen(spelling(t.command, expand, short_name));
                 result = result - (t.end - t.begin) + n;
                 return result < capacity;
               },initial) &&
         result < capacity;
}
inline bool transform(char *source, unsigned capacity, bool expand,const InitialLine* initial=nullptr) {
  if (!source || !capacity)
    return false;
  unsigned length = 0;
  while (length < capacity && source[length])
    ++length;
  if (length == capacity)
    return false;
  unsigned needed;
  if (!expanded_size(source, length, capacity, needed, expand,initial))
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
    },initial);
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
inline bool editor_copy(const char *source, char *output, unsigned capacity,const InitialLine* initial=nullptr) {
  if (!source || !output || !capacity)
    return false;
  unsigned length = (unsigned)strlen(source), needed;
  if (!expanded_size(source, length, capacity, needed,true,initial))
    return false;
  memmove(output, source, length + 1);
  return transform(output, capacity, true,initial);
}
} // namespace focal_text
#endif
