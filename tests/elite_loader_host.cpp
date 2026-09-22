// Host storage/terminal adapters for the actual M61 runner and calculator core.
// Only file I/O and the Markdown viewer are replaced; nested calls and clears
// execute code/m61_text.cpp and MK61Emu_ClearCodePage from the real core.
#include "m61_text.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "terminal_script.hpp"
#include <algorithm>
#include <cassert>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

namespace {
struct File { std::string name, text; };
std::vector<File> files;
std::filesystem::path directory;
unsigned elapsed = 0;
unsigned written_bytes = 0;

void press(int x, int y) {
  core_61::clear_displayed();
  for(unsigned i=0; i<4; ++i) {
    MK61Emu_SetKeyPress(x,y); core_61::step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0,0);
  for(unsigned i=0; i<64; ++i) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }
}
}

namespace program_store {
int count(ProgramType type) { return type==ProgramType::MK61 ? files.size() : 0; }
bool entry(ProgramType type, int index, Entry& out) {
  if(type!=ProgramType::MK61 || index<0 || size_t(index)>=files.size()) return false;
  out={}; out.type=type; out.kind=NodeKind::FILE;
  out.id=index; out.parent_id=ROOT_ID; out.data_len=files[index].text.size();
  std::strncpy(out.name,files[index].name.c_str(),NAME_SIZE-1);
  return true;
}
bool entry_by_id(u16 id, Entry& out) { return entry(ProgramType::MK61,id,out); }
int child_count(u16 parent) { return parent==ROOT_ID ? files.size() : 0; }
bool child(u16 parent, int index, Entry& out) {
  return parent==ROOT_ID && entry(ProgramType::MK61,index,out);
}
bool read_range_id(u16 id, u16 offset, u8* data, u16 length, u16* got) {
  if(got) *got=0;
  if(id>=files.size()) return false;
  const auto& source=files[id].text;
  if(offset>=source.size()) return true;
  auto size=std::min<size_t>(length,source.size()-offset);
  std::memcpy(data,source.data()+offset,size);
  if(got) *got=size;
  return true;
}
}

bool OpenStoredFile(const char* name) {
  // Alternate the production name/id entry points to exercise both.
  if(std::string(name)=="part01.m61") {
    for(size_t i=0;i<files.size();++i)
      if(files[i].name==name) return m61_text::open_program(u16(i));
    return false;
  }
  return m61_text::open_program(name);
}
u8 m61_text_host_open_file(const char* name) {
  if(std::filesystem::path(name).extension()==".md")
    return std::filesystem::is_regular_file(directory/name) ? 0 : 2;
  return OpenStoredFile(name) ? 0 : 2;
}
void hidden_start_loaded_program() { core_61::set_IP(0); press(2,9); }
void reinit_mk61_calculator_state() {
  core_61::clear_extended_program_banks(); core_61::enable();
}
void lcd_std_display_redraw() {}
u32 m61_text_host_millis() { return elapsed; }
i32 program_store_text_font_begin() { return -1; }
i32 program_store_text_font_load_from(const char*,u16) { return -1; }
i32 program_store_text_font_restore() { return 1; }
i32 program_store_text_font_end() { return 1; }

namespace terminal_script {
void reset() {}
terminal_protocol::Result execute(const char* line, bool) {
  using namespace terminal_protocol;
  if(std::strncmp(line,"open ",5)==0) return Result::action(ResultKind::OPEN_FILE,line+5);
  if(std::strcmp(line,"reinit")==0) return Result::action(ResultKind::REINIT_CALCULATOR,"");
  if(std::strcmp(line,"run")==0) return Result::action(ResultKind::RUN_PROGRAM,"");
  std::istringstream input(line);
  std::string op, hex, extra; unsigned address;
  if(!(input>>op>>address>>hex) || op!="hin" || input>>extra || hex.size()%2) return Result::error();
  for(size_t i=0;i<hex.size();i+=2) {
    if(!core_61::write_absolute_program(address+i/2,std::stoul(hex.substr(i,2),nullptr,16)))
      return Result::error();
    ++written_bytes;
  }
  return Result::ok();
}
}

unsigned elite_load_game(const char* path) {
  directory=path;
  for(const auto& p:std::filesystem::directory_iterator(directory)) {
    if(p.path().extension()!=".m61") continue;
    std::ifstream f(p.path());
    files.push_back({p.path().filename().string(),{std::istreambuf_iterator<char>(f),{}}});
  }
  core_61::set_expanded_program_mode(true); core_61::enable();
  // A previous program must be discarded by the new root loader.
  assert(core_61::write_absolute_program(0,0xEE));
  if(!m61_text::load_program("autoexec.m61")) std::exit(5);
  while(m61_text::active() && elapsed<20000) {
    if(core_61::is_RUN()) core_61::step();
    m61_text::service(); ++elapsed;
  }
  m61_text::Error error={};
  if(m61_text::last_error(error)) {
    std::cerr<<error.script<<':'<<error.line<<": "<<error.message<<'\n'; std::exit(6);
  }
  if(m61_text::active() || core_61::is_RUN() || written_bytes!=32*112) {
    std::cerr<<"ELITE loader failed to reach the title stop; bytes="<<written_bytes<<'\n';
    std::exit(7);
  }
  return elapsed;
}
