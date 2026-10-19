#include "rust_types.h"
class MK61Display {
 public:
  u8 rows()const{return 2;} void clear(){} void setCursor(u8,u8){} void write(u8){}
  bool supportsCursor()const{return true;} void cursorOn(){}
};
class MK61DisplayUpdate { public: explicit MK61DisplayUpdate(MK61Display&){} };
#define TEXT_EDITOR_HOST_TEST
#include "text_editor.hpp"
#include "builtin_font.hpp"
#include "number_format.hpp"
#if defined(MK61_TARGET_PICOCALC)
#include "ui_font.hpp"
#endif
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#define main sheet_app_entry
#include "../examples/portable-apps/SHEET/main.cpp"
#undef main
extern "C" { const mk61_app_api* mk61_api; }
namespace {
mk61_app_api api;
mk61_app_services services;
std::vector<int32_t> inputs;
size_t input_index;
uint32_t ticks,revision,starts,ends,writes,acquires,releases;
#if defined(MK61_TARGET_PICOCALC)
uint8_t borrowed_frame[12800];
bool framebuffer_ok=true,expose_ui_font=true;
#else
uint8_t scratch[1600];
#endif
bool leased,available=true,present_ok=true,save_ok=true,target_ok=true;
struct File { uint32_t id,parent; std::string name; std::vector<uint8_t> data; };
std::vector<File> files;
std::vector<std::vector<uint8_t>> frames;
uint32_t choose_id;
uint32_t now(){return ticks++;}
void idle(){assert(++ticks<1000000);}
void pause(uint32_t n){ticks+=n;}
int32_t poll(){assert(input_index<inputs.size());return inputs[input_index++];}
uint32_t graphics_available(){return available;}
uint32_t width(){return FRAME_WIDTH;} uint32_t height(){return FRAME_HEIGHT;}
uint32_t rev(){return revision;}
uint32_t begin(){++starts;return 1;} void end(){++ends;}
uint32_t present(const uint8_t* data,uint32_t size){
#if defined(MK61_TARGET_PICOCALC)
  assert(!leased && data==borrowed_frame);
#else
  assert(leased);
#endif
  assert(size==FRAME_BYTES);frames.emplace_back(data,data+size);return present_ok;
}
File* file(uint32_t id){for(auto& f:files)if(f.id==id)return &f;return nullptr;}
uint32_t file_size(uint32_t id){const File* f=file(id);return f?(uint32_t)f->data.size():UINT32_MAX;}
uint32_t file_read(uint32_t id,uint32_t offset,uint8_t* out,uint32_t size){
  assert(!leased);const File* f=file(id);if(!f || offset>f->data.size() || size>f->data.size()-offset)return UINT32_MAX;
  memcpy(out,f->data.data()+offset,size);return size;
}
void export_file(const File& f,mk61_service_file& out){out={};out.id=f.id;out.parent=f.parent;out.type=MK61_SERVICE_FILE_SHEET;out.size=(uint32_t)f.data.size();copy_text(out.name,f.name.c_str(),sizeof(out.name));}
uint32_t call(uint32_t operation,uint32_t a,uint32_t b,uint32_t c,void* payload){
  if(operation==MK61_SERVICE_CAPABILITIES)return MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_DIALOGS|
      MK61_SERVICE_CAP_EDITOR|MK61_SERVICE_CAP_FONT|MK61_SERVICE_CAP_MATH|MK61_SERVICE_CAP_NUMBER_IO|MK61_SERVICE_CAP_MEMORY
#if defined(MK61_TARGET_PICOCALC)
      |(expose_ui_font?MK61_SERVICE_CAP_UI_FONT:0U)
#endif
      ;
#if defined(MK61_TARGET_PICOCALC)
  if(operation==MK61_SERVICE_DISPLAY){
    assert(a==MK61_SERVICE_DISPLAY_FRAMEBUFFER && b==sizeof(mk61_service_framebuffer));
    auto& f=*(mk61_service_framebuffer*)payload;f={};
    f.width=320;f.height=320;f.bytes=12800;if(framebuffer_ok)f.pixels=borrowed_frame;
    return 1;
  }
  if(operation==MK61_SERVICE_UI_FONT){
    assert(!leased && expose_ui_font && a==MK61_UI_FONT_GLYPH && c==sizeof(mk61_service_ui_glyph));
    auto& g=*(mk61_service_ui_glyph*)payload;assert(g.family==1 && (g.size==12 || g.size==16));
    const auto source=ui_font::glyph({ui_font::Family::PIXEL,g.size==12?ui_font::Size::PX12:ui_font::Size::PX16},b);
    g.bearing_x=source.bearing_x;g.bearing_y=source.bearing_y;g.advance=source.advance;
    g.width=source.width;g.height=source.height;
    const unsigned stride=(g.width+7)/8;assert(stride*g.height<=sizeof(g.pixels));
    for(unsigned y=0;y<source.height;++y)for(unsigned x=0;x<source.width;++x)
      if(font_glyph::pixel(source,x,y))g.pixels[y*stride+x/8]|=0x80>>(x%8);
    return 1;
  }
#endif
  if(operation==MK61_SERVICE_MEMORY_ACQUIRE){
#if defined(MK61_TARGET_PICOCALC)
    assert(false);return 0;
#else
    assert(a==MK61_SERVICE_SCRATCH && b==MK61_SERVICE_OWNER_APP && c==1536 && !leased);
    auto& lease=*(mk61_service_lease*)payload;lease.data=scratch;lease.size=sizeof(scratch);leased=true;++acquires;return 1;
#endif
  }
  if(operation==MK61_SERVICE_MEMORY_RELEASE){assert(a==MK61_SERVICE_SCRATCH && leased);leased=false;++releases;return 1;}
  if(operation==MK61_SERVICE_FONT){
    assert(leased);auto& glyph=*(mk61_service_glyph*)payload;builtin_font::Raster raster={};
    if(!builtin_font::decode((builtin_font::FaceId)a,(uint16_t)b,raster))return 0;
    glyph.width=raster.width;glyph.height=raster.height;memcpy(glyph.pixels,raster.data,8);return 1;
  }
  if(operation==MK61_SERVICE_NUMBER_PARSE){auto& r=*(mk61_service_number_parse*)payload;const char* endptr=nullptr;r.value=mk_math::strtod(r.input,&endptr);r.consumed=(uint32_t)(endptr-r.input);return r.consumed!=0;}
  if(operation==MK61_SERVICE_NUMBER_FORMAT){auto& r=*(mk61_service_number_format*)payload;return number_format::general(r.value,(uint8_t)r.significant_digits,r.output,r.capacity);}
  if(operation==MK61_SERVICE_FILE_ENTRY){
    File* f=a==0?file(b):(b<files.size()?&files[b]:nullptr);if(!f)return 0;export_file(*f,*(mk61_service_file*)payload);return 1;
  }
  if(operation==MK61_SERVICE_FILE_COUNT)return (uint32_t)files.size();
  if(operation==MK61_SERVICE_FILE_SAVE_TARGET){assert(!leased && a==MK61_SERVICE_FILE_SHEET && c==32);return target_ok;}
  if(operation==MK61_SERVICE_FILE_WRITE){
    assert(!leased && c==MK61_SERVICE_FILE_SHEET);++writes;if(!save_ok)return 0;
    auto& write=*(mk61_service_write*)payload;
    if(b==MK61_SERVICE_INVALID_ID){files.push_back({42+(uint32_t)files.size(),a,write.name,{}});b=files.back().id;}
    File* f=file(b);assert(f);f->data.assign(write.data,write.data+write.size);write.id=b;return 1;
  }
  if(operation==MK61_SERVICE_FILE_CHOOSE){assert(!leased && a==MK61_SERVICE_FILE_SHEET);if(!choose_id)return 0;File* f=file(choose_id);assert(f);export_file(*f,((mk61_service_choice*)payload)->file);return 1;}
  if(operation==MK61_SERVICE_EDITOR_KEY){
    auto& request=*(mk61_service_edit_key*)payload;
    const auto& k=keyboard_layout::ACTIVE;
    text_editor::Buffer buffer={request.source,(u16)request.capacity,(u16)request.length,(u16)request.cursor,0,
      (text_editor::Shift)request.shift,{request.sms_active!=0,request.sms_key,(u8)request.sms_index,request.sms_deadline}};
    text_editor::KeyMap map={k.left,k.left,k.right,k.right,k.ok,k.ok,k.esc,k.esc,k.shg_left,k.shg_right,k.k,k.alpha,k.pp};
    text_editor::Hooks hooks={};
    text_editor::Options options={"",true,true,true,true,k.cx};
    const auto result=text_editor::handle_key(buffer,map,hooks,options,request.key,request.now);
    request.length=buffer.len;request.cursor=buffer.cursor;request.shift=(uint32_t)buffer.shift;
    request.sms_active=buffer.sms.active;request.sms_key=buffer.sms.key_code;request.sms_index=buffer.sms.index;request.sms_deadline=buffer.sms.deadline_ms;
    return (uint32_t)result;
  }
  assert(false);return 0;
}
double math_service(uint32_t operation,double x,double y){
  assert(!leased);switch(operation){
    case MK61_SERVICE_SIN:return std::sin(x);case MK61_SERVICE_COS:return std::cos(x);case MK61_SERVICE_TAN:return std::tan(x);
    case MK61_SERVICE_ASIN:return std::asin(x);case MK61_SERVICE_ACOS:return std::acos(x);case MK61_SERVICE_ATAN:return std::atan(x);
    case MK61_SERVICE_LN:return std::log(x);case MK61_SERVICE_LOG10:return std::log10(x);case MK61_SERVICE_EXP:return std::exp(x);
    case MK61_SERVICE_SQRT:return std::sqrt(x);case MK61_SERVICE_POW:return std::pow(x,y);
  }assert(false);return 0;
}
const void* query(uint32_t id,uint32_t version){return id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION?&services:nullptr;}
void reset(){
  input_index=ticks=starts=ends=writes=acquires=releases=0;leased=false;frames.clear();
  available=present_ok=save_ok=target_ok=true;choose_id=0;
#if defined(MK61_TARGET_PICOCALC)
  framebuffer_ok=expose_ui_font=true;
#endif
  services={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(services),&keyboard_layout::ACTIVE,call,math_service,nullptr,nullptr};
  api={};api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);
  api.capabilities=MK61_APP_CAP_TIME|MK61_APP_CAP_FILES|MK61_APP_CAP_GRAPHICS|MK61_APP_CAP_KEYBOARD;
  api.millis_ms=now;api.service=idle;api.delay_ms=pause;api.key_poll=poll;api.file_size=file_size;api.file_read=file_read;
  api.graphics_available=graphics_available;api.graphics_width=width;api.graphics_height=height;
  api.graphics_revision=rev;api.graphics_begin=begin;api.graphics_end=end;api.graphics_present=present;api.query_service=query;mk61_api=&api;
}
constexpr int OK=MK61_APP_KEY_OK, ESC=MK61_APP_KEY_ESC, USER=MK61_APP_KEY_USER,
  RIGHT=MK61_APP_KEY_RIGHT, LEFT=MK61_APP_KEY_LEFT, DOWN=MK61_APP_KEY_SHIFT_RIGHT, UP=MK61_APP_KEY_SHIFT_LEFT;
int enter(){return MK61_APP_KEY_RAW_BASE+keyboard_layout::ACTIVE.bx;}
void done(){assert(!leased && starts==ends && acquires==releases && input_index==inputs.size());}
double result(uint16_t pos){const int index=sheet::find(app.book,pos);assert(index>=0 && app.book.cells[index].error==0);return app.book.cells[index].value;}
void dump(const char* path,const std::vector<uint8_t>& frame){
  FILE* out=std::fopen(path,"wb");assert(out);std::fprintf(out,"P1\n%u %u\n",FRAME_WIDTH,FRAME_HEIGHT);
  for(unsigned y=0;y<FRAME_HEIGHT;++y){for(unsigned x=0;x<FRAME_WIDTH;++x)std::fprintf(out,"%u ",(frame[(y/8)*FRAME_WIDTH+x]>>(y%8))&1);std::fputc('\n',out);}std::fclose(out);
}
#if defined(MK61_TARGET_PICOCALC)
void native_checks(){
  reset();inputs={MK61_APP_KEY_FORWARD,7,OK,MK61_APP_KEY_BACKWARD,
      MK61_APP_KEY_RAW_BASE+'\t',ESC,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(result(16)==7 && app.selected==0);
  reset();memset(&app,0,sizeof(app));app.api=&api;app.services=&services;app.frame=borrowed_frame;
  sheet::number_io(parse_number,format_number);
  char long_label[sheet::SOURCE_BYTES];memset(long_label,(unsigned char)M8("Ж")[0],95);long_label[95]=0;
  assert(sheet::set(app.book,0,Kind::TEXT,long_label,95)==Error::OK);
  assert(sheet::set(app.book,1,Kind::NUMBER,"12345678",8)==Error::OK);recalc();
  assert(pico_sheet::width(M8("ЖЖ"))>20); // The old logical 6-pixel step overlapped Cyrillic ink.
  char fitted[sheet::SOURCE_BYTES];copy_text(fitted,long_label,sizeof(fitted));
  pico_sheet::fit(fitted,88,16);assert(pico_sheet::width(fitted)<=88 && fitted[length(fitted)-1]=='>');
  // Native viewports stay inside P32, including a density switch at the corner.
  app.selected=sheet::ROWS*sheet::COLUMNS-1;visible();assert(app.top_row==24 && app.left_column==13);
  memset(app.frame,0,FRAME_BYTES);table();
  app.book.compact=1;visible();assert(app.top_row==21 && app.left_column==12);
  assert(pico_sheet::rows()==11 && pico_sheet::columns()==4);
  memset(app.frame,0,FRAME_BYTES);table();
  app.book.compact=0;app.selected=0;app.mode=Mode::EDIT;app.edit_kind=Kind::TEXT;
  copy_text(app.edit,long_label,sizeof(app.edit));app.edit_length=app.cursor=95;
  key(MK61_APP_KEY_BACKWARD);assert(app.cursor==0);
  key(MK61_APP_KEY_FORWARD);assert(app.cursor==95);
  memset(app.frame,0,FRAME_BYTES);editor();
  // The entire 95-byte wide-glyph draft and its end caret fit in the native panel.
  int x=8,row=0;
  for(unsigned i=0;i<=95;++i){const int step=pico_sheet::width(i==95?" ":M8("Ж"));if(x+step>312){x=8;++row;}if(i<95)x+=step;}
  assert(row<6);const int caret_y=44+row*24+18;
  assert(app.frame[caret_y/8*320+x]&(1U<<(caret_y%8)));
  // Ink is clipped by the actual cell boundary; nothing can bleed into its neighbour.
  memset(app.frame,0,FRAME_BYTES);pico_sheet::text(8,40,long_label,false,16,80);
  for(int y=40;y<60;++y)for(int column=80;column<320;++column)
    assert(!(app.frame[y/8*320+column]&(1U<<(y%8))));
  app.frame=nullptr;
  std::puts("SHEET native: measured Cyrillic, clipping, 3x8/4x11 corner scrolling and full 95-byte editor PASS");
}
#endif
}
int main(int argc,char** argv){
  reset();files.clear();
  inputs={2,OK,RIGHT,1,2,5,OK,RIGHT,OK,USER,LEFT,LEFT,OK,enter(),USER,LEFT,OK,MK61_APP_KEY_MULTIPLY,OK,ESC,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(writes==1 && files.size()==1 && result(2)==250);
  char source_text[sheet::SOURCE_BYTES];sheet::source(app.book,2,source_text);assert(strcmp(source_text,"A1 ENT B1 *")==0);
  if(argc==2)dump(argv[1],frames[frames.size()-2]);
  const auto saved=files[0].data;
  reset();inputs={RIGHT,2,OK,ESC,RIGHT,OK};
  assert(mk61_app_open_file(42)==MK61_APP_OK);done();assert(result(2)==4 && writes==0 && files[0].data==saved);
  reset();inputs={ESC};assert(mk61_app_open_file(42)==MK61_APP_OK);done();assert(result(2)==250);

  // A self-reference is finite and saved as an error, rather than hanging.
  reset();inputs={OK,USER,OK,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(app.book.cells[0].error==(uint8_t)Error::CYCLE);

  // Reference cycling uses USER only; no keyboard dollar character is needed.
  reset();inputs={RIGHT,RIGHT,RIGHT,OK,USER,LEFT,LEFT,LEFT,USER,USER,USER,OK,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();sheet::source(app.book,3,source_text);assert(strcmp(source_text,"$A$1")==0);

  // Copy/fill use translated references; the entire fill operation is undoable.
  reset();inputs={RIGHT,RIGHT,USER,RIGHT,OK,DOWN,OK,UP,USER,RIGHT,RIGHT,OK,DOWN,DOWN,OK,USER,OK,ESC,RIGHT,OK};
  assert(mk61_app_open_file(42)==MK61_APP_OK);done();sheet::source(app.book,18,source_text);assert(strcmp(source_text,"A2 ENT B2 *")==0);assert(sheet::find(app.book,34)<0);

  // Save failure and save-dialog cancellation preserve the dirty sheet.
  reset();save_ok=false;inputs={8,OK,ESC,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(app.modified && result(0)==8 && writes==1);
  reset();target_ok=false;inputs={9,OK,ESC,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(app.modified && result(0)==9 && writes==0);

  // All graphic failure paths release the scratch lease and end the session.
  reset();present_ok=false;inputs={};assert(sheet_app_entry()==MK61_APP_RUNTIME_ERROR);done();
  reset();available=false;inputs={};assert(sheet_app_entry()==MK61_APP_UNSUPPORTED_DISPLAY);done();
#if defined(MK61_TARGET_PICOCALC)
  reset();framebuffer_ok=false;inputs={};assert(sheet_app_entry()==MK61_APP_UNSUPPORTED_DISPLAY);done();
  reset();expose_ui_font=false;inputs={};assert(sheet_app_entry()==MK61_APP_UNSUPPORTED_DISPLAY);done();
#endif
  reset();inputs={};files[0].data[0]^=1;assert(mk61_app_open_file(42)==MK61_APP_INVALID_FILE);assert(starts==0);files[0].data=saved;

  // Pure functions are evaluated before leasing the framebuffer (CORE uses SCRATCH).
  reset();inputs={9,0,MK61_APP_KEY_F,7,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(std::fabs(result(0)-1)<1e-12);
  reset();inputs={2,enter(),3,MK61_APP_KEY_F,MK61_APP_KEY_RAW_BASE+keyboard_layout::ACTIVE.xy,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(result(0)==9);
  // The palette makes every supported operation accessible on both boards.
  reset();inputs={2,enter(),3,MK61_APP_KEY_F,USER,RIGHT,RIGHT,RIGHT,RIGHT,RIGHT,RIGHT,RIGHT,OK,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();assert(result(0)==2);
  sheet::source(app.book,0,source_text);assert(strcmp(source_text,"2 ENT 3 ROLL")==0);

  // Phone text mode begins in Russian; numeric text needs the 123 layout.
  reset();inputs={USER,RIGHT,RIGHT,RIGHT,RIGHT,OK,RIGHT,OK,MK61_APP_KEY_K,MK61_APP_KEY_K,1,2,3,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();sheet::source(app.book,0,source_text);assert(strcmp(source_text,"123")==0 && app.book.cells[0].kind==(uint8_t)Kind::TEXT);
  reset();files.clear();inputs={USER,RIGHT,RIGHT,RIGHT,RIGHT,OK,RIGHT,OK,
      6,5,5,5,6,6,RIGHT,6,6,6,OK,ESC,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();sheet::source(app.book,0,source_text);assert(strcmp(source_text,M8("РОСТ"))==0);
  reset();inputs={ESC};assert(mk61_app_open_file(42)==MK61_APP_OK);done();sheet::source(app.book,0,source_text);assert(strcmp(source_text,M8("РОСТ"))==0);
  reset();inputs={USER,RIGHT,RIGHT,RIGHT,RIGHT,OK,RIGHT,OK,
      3,3,3,RIGHT,MK61_APP_KEY_F,3,3,3,3,0,MK61_APP_KEY_K,MK61_APP_KEY_F,
      2,RIGHT,2,2,RIGHT,2,2,2,0,MK61_APP_KEY_K,1,2,3,MK61_APP_KEY_CLEAR,3,OK,ESC,RIGHT,OK};
  assert(sheet_app_entry()==MK61_APP_OK);done();sheet::source(app.book,0,source_text);assert(strcmp(source_text,M8("Ёж ABC 123"))==0);
  // Idle timeout confirms a glyph even when the next key repeats its group.
  reset();inputs={USER,RIGHT,RIGHT,RIGHT,RIGHT,OK,RIGHT,OK,2};
  for(int i=0;i<250;++i) inputs.push_back(MK61_APP_KEY_NONE);
  inputs.insert(inputs.end(),{2,OK,ESC,RIGHT,OK});
  assert(sheet_app_entry()==MK61_APP_OK);done();sheet::source(app.book,0,source_text);assert(strcmp(source_text,M8("АА"))==0);
#if defined(MK61_TARGET_PICOCALC)
  native_checks();
#endif
  std::puts("SHEET UI: actual glyphs, keystrokes, anchors, copy/fill/undo, save/reopen/failures, math and scratch lifetime PASS");
}
