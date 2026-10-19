#include "terminal_catalog.hpp"
#include "terminal_core.hpp"
#include <cassert>
#include <cstdio>
#include <string>

static u8 linear_lookup(const std::string& line) {
  const auto end=line.find_first_of(" \t");
  const auto word=line.substr(0,end);
  if(word.size()==3 && word[0]=='R' && word[2]=='=' && end!=std::string::npos)
    return CMD_REG_SET;
  if(word.compare(0,4,"set$")==0)return CMD_SET_CODE;
  for(usize i=0;i<terminal_catalog::count();++i) {
    const auto command=terminal_catalog::at(i);
    if(word==command.name)return command.id;
  }
  return CMD_UNKNOWN;
}
static void check(const std::string& line) {
  assert(terminal_catalog::lookup((const u8*)line.c_str())==linear_lookup(line));
}
int main() {
  for(usize i=0;i<terminal_catalog::count();++i) {
    const std::string name=terminal_catalog::at(i).name;
    for(const char* suffix:{""," argument","\targument"})check(name+suffix);
    for(usize n=0;n<name.size();++n) {
      check(name.substr(0,n));
      for(char c='a';c<='z';++c) {
        std::string changed=name;changed[n]=c;check(changed);
      }
    }
    check(name+"x");check(" "+name);check(name+"\r");check(name+"\n");
  }
  // Exercise occupied hash chains and unknown tokens against an independent
  // scan of the public catalog, including names longer than the index byte.
  u32 state=0x61706963;
  for(unsigned i=0;i<20000;++i) {
    std::string word;
    for(unsigned n=0;n<i%17;++n) {
      state=state*1664525U+1013904223U;
      word+=char('a'+(state>>24)%26);
    }
    check(word);check(word+" argument");
  }
  for(usize size:{255U,256U,257U,65536U})check(std::string(size,'a'));
  for(const char* text:{"","R0= 12","RA=\t1","R0=","R= 1","set$1234",
                        "set$","SET$1234","openx file","\x80","\xff"})check(text);
  assert(terminal_catalog::lookup((const u8*)"open x")==CMD_OPEN);
  assert(terminal_catalog::lookup((const u8*)"if 0==0 ret")==CMD_IF);
  std::puts("Pico indexed catalog: names, collisions, token boundaries and long inputs PASS");
}
