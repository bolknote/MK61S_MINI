// Exercise the shipping shell's streaming saves on both platform profiles.
#include <cassert>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <map>
#include <string>
#include <vector>
#define main urq_app_main
#if !defined(MK61_TARGET_PICOCALC)
#define MK61_URQ_COLD 1
#endif
#include "../examples/portable-apps/URQ/main.cpp"
#undef main
#include "../code/ecma_number.hpp"
#include "../code/ui_font.hpp"
#include "../code/builtin_font.hpp"
#include "../code/menu_source.hpp"
#include "../code/keyboard_layout.hpp"

const mk61_app_api* mk61_api = nullptr;
uint32_t mk61_app_image_crc = 1, mk61_app_current_kind = 4;
namespace {
struct File { unsigned type; std::string name; std::vector<uint8_t> bytes; };
std::map<unsigned, File> files;
bool fail_write = false;
bool fail_psram = false;
bool classic = false;
std::vector<std::vector<uint8_t>> frames;
std::vector<int> keys;
std::vector<std::string> text_rows(24);
unsigned live_leases = 0;
uint32_t file_size_mock(uint32_t id) { return files.count(id)?uint32_t(files[id].bytes.size()):UINT32_MAX; }
uint32_t file_read_mock(uint32_t id,uint32_t offset,uint8_t* out,uint32_t size) {
  if(!files.count(id) || offset>files[id].bytes.size()) return UINT32_MAX;
  const auto& bytes=files[id].bytes;size=uint32_t(std::min<size_t>(size,bytes.size()-offset));
  std::memcpy(out,bytes.data()+offset,size);return size;
}
uint32_t entry(unsigned id,void* raw) {
  if(!files.count(id)) return 0;
  auto& out=*(mk61_service_file*)raw;const auto& f=files[id];out={};
  out.id=id;out.parent=1;out.size=uint32_t(f.bytes.size());out.type=f.type;
  std::snprintf(out.name,sizeof(out.name),"%s",f.name.c_str());return 1;
}
uint32_t mock_call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* p) {
  if(op==MK61_SERVICE_FONT) {
    builtin_font::Raster g{};assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8,uint16_t(b),g));
    auto& out=*(mk61_service_glyph*)p;out.width=g.width;out.height=g.height;memcpy(out.pixels,g.data,8);return 1;
  }
  if(op==MK61_SERVICE_UI_FONT) {
    assert(a==MK61_UI_FONT_GLYPH);auto& out=*(mk61_service_ui_glyph*)p;
    const auto g=ui_font::glyph({ui_font::Family::PIXEL,ui_font::Size::PX12},b);
    out.width=g.width;out.height=g.height;out.bearing_x=g.bearing_x;out.bearing_y=g.bearing_y;out.advance=g.advance;
    memset(out.pixels,0,sizeof(out.pixels));
    for(unsigned y=0;y<g.height;++y) for(unsigned x=0;x<g.width;++x)
      if(font_glyph::pixel(g,x,y)) out.pixels[y*((g.width+7)/8)+x/8]|=uint8_t(0x80U>>(x&7));
    return 1;
  }
  if(op==MK61_SERVICE_CAPABILITIES) return fail_psram?UINT32_MAX:~uint32_t(MK61_SERVICE_CAP_EXTERNAL_BUFFERS);
  if(op==MK61_SERVICE_BUFFER) {
    auto& r=*(mk61_service_buffer*)p;
    if(a==MK61_BUFFER_ACQUIRE) { r.handle=1;r.storage=MK61_BUFFER_PSRAM;return 1; }
    return a==MK61_BUFFER_RELEASE; // simulate an unavailable external I/O bus
  }
  if(op==MK61_SERVICE_MEMORY_ACQUIRE) {
    auto& l=*(mk61_service_lease*)p;l.data=new uint8_t[c];l.size=c;l.fresh=1;++live_leases;return 1;
  }
  if(op==MK61_SERVICE_MEMORY_RELEASE) {
    auto& l=*(mk61_service_lease*)p;delete[] l.data;l.data=nullptr;--live_leases;return 1;
  }
  if(op==MK61_SERVICE_FILE_ENTRY) return entry(b,p);
  if(op==MK61_SERVICE_FILE_RESOLVE) {
    // The ARM wire argument is u32. Names in this test are shell stack locals.
    const uintptr_t high=uintptr_t(&op)&~uintptr_t(UINT32_MAX);
    const char* name=(const char*)(high|c);
    for(const auto& f:files) if(f.second.type==b && f.second.name==name) { entry(f.first,p);return 0; }
    return 4;
  }
  if(op==MK61_SERVICE_FILE_WRITE_SOURCE) {
    auto& source=*(mk61_service_write_source*)p;std::vector<uint8_t> next(source.size,0xCD);
    // Actual callback contract permits repeated and non-monotonic ranges.
    for(unsigned end=source.size;end;) {
      const unsigned n=std::min(97U,end);end-=n;
      assert(source.read(source.context,end,next.data()+end,n));
      uint8_t repeated[97];assert(source.read(source.context,end,repeated,n));
      assert(!std::memcmp(repeated,next.data()+end,n));
      if(fail_write) return 0;
    }
    const unsigned id=b==MK61_SERVICE_INVALID_ID?100:b;
    files[id]={c,std::string(source.name)+".urs",std::move(next)};source.id=id;return 1;
  }
  if(op==MK61_SERVICE_NUMBER_FORMAT) {
    auto& r=*(mk61_service_number_format*)p;
    return a==MK61_NUMBER_ECMA_FRACTIONAL?ecma_number::fractional(r.value,r.output,r.capacity):
      ecma_number::format(r.value,r.output,r.capacity);
  }
  if(op==MK61_SERVICE_NUMBER_PARSE) {
    auto& r=*(mk61_service_number_parse*)p;r.consumed=uint32_t(std::strlen(r.input));
    return ecma_number::parse(r.input,r.value);
  }
  if(op==MK61_SERVICE_DISPLAY) {
    if(a==MK61_SERVICE_DISPLAY_CLEAR) std::fill(text_rows.begin(),text_rows.end(),std::string());
    if(a==MK61_SERVICE_DISPLAY_UI_LINE) {assert(b<text_rows.size());text_rows[b]=(char*)p;}
    if(a==MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH) return 320;
    if(a==MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT) return uint32_t(std::strlen((char*)p))*5;
    return 1;
  }
  if(op==MK61_SERVICE_TEXT_INPUT) return a!=MK61_TEXT_POLL;
  if(op==MK61_SERVICE_SETUP && a==MK61_SETUP_RTC_READ) {
    auto& r=*(mk61_setup_datetime*)p;r.year=2026;r.month=11;r.day=5;return 1;
  }
  if(op==MK61_SERVICE_SETUP && a==MK61_SETUP_FEATURES) return MK61_SETUP_FEATURE_RTC_VALUE;
  if(op==MK61_SERVICE_SETUP && a==MK61_SETUP_RTC_VALUE) return b?20000:43210;
  return 0;
}
double math_mock(uint32_t,double a,double b) { return std::pow(a,b); }
int format_mock(char* p,uint32_t n,const char* f,va_list args) { return std::vsnprintf(p,n,f,args); }
mk61_app_services service_table{MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,
  sizeof(mk61_app_services),nullptr,mock_call,math_mock,format_mock,nullptr};
const void* query(uint32_t,uint32_t) { return &service_table; }
uint32_t columns() { return 64; }
uint32_t rows() { return 20; }
uint32_t milliseconds() { return 1000; }
int32_t poll_key() { if(keys.empty()) return -1;int key=keys.front();keys.erase(keys.begin());return key; }
int32_t wait_key() { assert(!keys.empty());int key=keys.front();keys.erase(keys.begin());return key; }
uint32_t available_graphics() { return classic; }
uint32_t graph_width() {return 192;}
uint32_t graph_height() {return 64;}
uint32_t graph_begin() {return 1;}
uint32_t present(const uint8_t* pixels,uint32_t size) {
  assert(size==1536);frames.emplace_back(pixels,pixels+size);return 1;
}
void idle() {}
std::vector<uint8_t> read_file(const std::string& path) {
  std::ifstream input(path,std::ios::binary);assert(input);
  return {std::istreambuf_iterator<char>(input),{}};
}
}
int main(int argc,char** argv) {
  assert(argc>=3);fail_psram=std::getenv("URQ_TEST_PSRAM")!=nullptr;mk61_app_api api{};
  api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);
  api.query_service=query;api.file_size=file_size_mock;api.file_read=file_read_mock;
  api.millis_ms=milliseconds;api.display_columns=columns;api.display_rows=rows;
  classic=std::getenv("URQ_TEST_CLASSIC")!=nullptr;
  api.key_wait=wait_key;api.key_poll=poll_key;api.service=idle;api.delay_ms=[](uint32_t){};mk61_api=&api;
  api.graphics_available=available_graphics;api.graphics_width=graph_width;api.graphics_height=graph_height;
  api.graphics_begin=graph_begin;api.graphics_present=present;api.graphics_end=idle;
  files[2]={MK61_SERVICE_FILE_URQ,"game.urq",read_file(std::string(argv[1])+"/game.urq")};
  files[3]={MK61_SERVICE_FILE_URQ_DATA,"p0000.uqd",read_file(std::string(argv[1])+"/p0000.uqd")};
  assert(begin_session(2)==MK61_APP_OK);app.body=12;app.rows=20;
  auto& engine=app.engine;engine.run();assert(engine.state().status==urq::Status::INPUT);
  assert(!app.history.external.handle && app.history.end>=2);
  assert(engine.state().depth==2);
  begin_typing(false);
  if(classic) {
#if !defined(MK61_TARGET_PICOCALC)
    classic_view::Canvas canvas{app.services,nullptr};
    const auto dash=canvas.glyph(0x97),minus=canvas.glyph('-');
    assert(dash.advance==minus.advance && !memcmp(dash.pixels,minus.pixels,sizeof(dash.pixels)));
#endif
    draw_game();assert(app.rows==5 && app.body==3 && !frames.empty());
    const auto input=frames.back();
    keys={MK61_APP_KEY_RIGHT,MK61_APP_KEY_SHIFT_RIGHT,MK61_APP_KEY_LEFT,MK61_APP_KEY_OK};
    assert(menu_choose(Screen::MENU,6)==1 && keys.empty());
    assert(frames.back()!=input);
    draw_game();assert(frames.back()==input); // restoring the input frame keeps the draft
    keys={MK61_APP_KEY_SHIFT_RIGHT,MK61_APP_KEY_ESC};assert(menu_choose(Screen::MENU,6)==-1 && keys.empty());
    for(const auto& mapping:{keyboard_layout::CLASSIC,keyboard_layout::MINI}) {
      keys={keyboard_layout::logical_key(mapping,mapping.right),keyboard_layout::logical_key(mapping,mapping.shg_right),
            keyboard_layout::logical_key(mapping,mapping.left),MK61_APP_KEY_OK};
      mk61_service_menu_source request{M8("МЕНЮ"),nullptr,6,0,
        [](void*,uint32_t i,char* label,uint32_t)->int {label[0]=char('1'+i);label[1]=0;return 1;}};
      assert(menu_source::run(request,api,[](uint32_t,uint32_t,uint32_t,void*){return 1;}));
      assert(request.selected==1 && keys.empty());
    }
  }
  for(unsigned char ch:std::string(M8("Ёж 12,!"))) input_event(MK61_TEXT_CHAR,ch);
  input_event(MK61_TEXT_LEFT);input_event(MK61_TEXT_BACKSPACE);input_event(MK61_TEXT_CHAR,'?');
  assert(!std::strcmp(app.draft,M8("Ёж 12?!")));
  assert(save_slot(0));const auto saved=files[100].bytes;
  input_event(MK61_TEXT_CHAR,'X');assert(load_slot(0));
  assert(!std::strcmp(app.draft,M8("Ёж 12?!")) && app.cursor==6);
  assert(engine.state().depth==2 && engine.state().status==urq::Status::INPUT);
  fail_write=true;input_event(MK61_TEXT_CHAR,'Y');assert(!save_slot(0));
  assert(files[100].bytes==saved);fail_write=false;assert(load_slot(0));
  // Corruption is rejected before changing the running game or input draft.
  files[100].bytes.back()^=1;const auto old_pc=engine.state().pc;
  assert(!load_slot(0));assert(engine.state().pc==old_pc && engine.state().depth==2);
  files[100].bytes=saved;
  if(argc>3) { files[100].bytes=read_file(argv[3]);assert(load_slot(0));assert(engine.state().depth==2); }
  std::ofstream output(argv[2],std::ios::binary);
  assert(save_slot(0));const auto& image=files[100].bytes;output.write((const char*)image.data(),image.size());output.close();
  input_event(MK61_TEXT_SUBMIT);engine.run();assert(engine.state().status==urq::Status::ANYKEY);
  game_key(MK61_APP_KEY_LEFT);game_key(MK61_APP_KEY_RIGHT);
  assert(engine.state().status==urq::Status::ANYKEY);
  game_key(MK61_APP_KEY_OK);engine.run();assert(engine.state().status==urq::Status::CHOICE);
  assert(engine.get("answer").type==1 && !std::strcmp(engine.get("answer").text,M8("Ёж 12?!")));
#if defined(MK61_TARGET_PICOCALC)
  draw_game();std::string displayed;
  for(unsigned row=app.body;row+1<app.rows;++row) {
    auto text=text_rows[row];if(text.rfind("2 ",0)==0) break;
    if(text.rfind("1 ",0)==0) text.erase(0,2);
    displayed+=text;
  }
  auto without_spaces=[](std::string value) {value.erase(std::remove(value.begin(),value.end(),' '),value.end());return value;};
  assert(without_spaces(displayed)==without_spaces(engine.text(engine.state().actions[0].caption)));
  game_key(MK61_APP_KEY_SHIFT_RIGHT);draw_game();assert(app.selected==1 && !app.menu);
  assert(text_rows[app.body].find(M8("Второе действие"))!=std::string::npos);
#endif
#if !defined(MK61_TARGET_PICOCALC)
  if(classic) {
    draw_game();assert(!app.actions);
    const auto reading=frames.back();
    game_key(MK61_APP_KEY_DIGIT_2);assert(engine.state().status==urq::Status::CHOICE && !app.actions);
    game_key(MK61_APP_KEY_OK);draw_game();assert(app.actions && app.selected==0 && app.action_next);
    const auto choices=frames.back();
    game_key(MK61_APP_KEY_RIGHT);draw_game();assert(app.menu && app.selected==0 && frames.back()!=choices);
    game_key(MK61_APP_KEY_LEFT);draw_game();assert(!app.menu && frames.back()==choices);
    for(unsigned i=0;app.selected==0 && i<20;++i) {game_key(MK61_APP_KEY_RIGHT);draw_game();}
    assert(app.selected==1);game_key(MK61_APP_KEY_LEFT);draw_game();assert(app.selected==0);
    game_key(MK61_APP_KEY_ESC);draw_game();assert(!app.actions && frames.back()==reading);
  }
#endif
  finish_session();assert(!live_leases);
  std::puts("URQ shell: nested input, edited draft, non-monotonic streamed save, atomic write failure, CRC rejection and cross-profile restore PASS");
}
