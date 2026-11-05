// Exercise the shipping shell's streaming saves on both platform profiles.
#include <cassert>
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

const mk61_app_api* mk61_api = nullptr;
uint32_t mk61_app_image_crc = 1, mk61_app_current_kind = 4;
namespace {
struct File { unsigned type; std::string name; std::vector<uint8_t> bytes; };
std::map<unsigned, File> files;
bool fail_write = false;
bool fail_psram = false;
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
int32_t no_key() { return -1; }
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
  api.key_wait=no_key;api.key_poll=no_key;api.service=idle;mk61_api=&api;
  files[2]={MK61_SERVICE_FILE_URQ,"game.urq",read_file(std::string(argv[1])+"/game.urq")};
  files[3]={MK61_SERVICE_FILE_URQ_DATA,"p0000.uqd",read_file(std::string(argv[1])+"/p0000.uqd")};
  assert(begin_session(2)==MK61_APP_OK);app.body=12;app.rows=20;
  auto& engine=app.engine;engine.run();assert(engine.state().status==urq::Status::INPUT);
  assert(!app.history.external.handle && app.history.end>=2);
  assert(engine.state().depth==2);
  begin_typing(false);
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
  finish_session();assert(!live_leases);
  std::puts("URQ shell: nested input, edited draft, non-monotonic streamed save, atomic write failure, CRC rejection and cross-profile restore PASS");
}
