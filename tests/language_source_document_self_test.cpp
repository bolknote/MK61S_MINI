#include "rust_types.h"

class MK61Display {
  public:
    u8 rows(void) const { return 2; }
    void clear(void) {}
    void setCursor(u8, u8) {}
    void write(u8) {}
    bool supportsCursor(void) const { return true; }
    void cursorOn(void) {}
};

class MK61DisplayUpdate {
  public:
    explicit MK61DisplayUpdate(MK61Display&) {}
};

#define TEXT_EDITOR_HOST_TEST
#include "language_source_document.hpp"
#include "focal_editor.hpp"
#include <assert.h>
#include <map>
#include <array>
#include <string>
#include <stdio.h>
using namespace language_vm::source;
struct Disk {
  std::string original;
  std::map<uint32_t,std::array<uint8_t,512>> pages;
  int writes=0,fail=-1;
  unsigned reads=0;
  bool locked=false;
  static bool read_file(void* raw,uint16_t at,uint8_t* out,uint16_t n) {
    auto& d=*(Disk*)raw;++d.reads;assert(n<=256);memcpy(out,d.original.data()+at,n);return true;
  }
  static bool begin(void* raw,uint32_t*,uint16_t) {auto& d=*(Disk*)raw;assert(!d.locked);d.locked=true;return true;}
  static bool read(void* raw,uint32_t key,uint8_t* out) {
    auto& d=*(Disk*)raw;auto at=d.pages.find(key);if(at==d.pages.end())return false;
    memcpy(out,at->second.data(),512);return true;
  }
  static bool write(void* raw,uint32_t key,const uint8_t* bytes) {
    auto& d=*(Disk*)raw;
    if(d.fail>=0 && d.writes++==d.fail)return false;
    memcpy(d.pages[key].data(),bytes,512);return true;
  }
  static bool forget(void* raw,uint32_t key,uint16_t n) {auto& d=*(Disk*)raw;for(unsigned i=0;i<n;++i)d.pages.erase(key+i);return true;}
  static void end(void* raw) {((Disk*)raw)->locked=false;}
  DraftIO io() {return {this,begin,read,write,forget,end};}
};
static std::string contents(Document& doc) {
  std::string text(doc.size(),' ');
  for(unsigned at=0;at<text.size();at+=137) {
    unsigned n=text.size()-at;if(n>137)n=137;
    assert(doc.read((uint16_t)at,(uint8_t*)text.data()+at,(uint16_t)n));
  }
  return text;
}
static void focal_page_context() {
  using namespace language_vm;
  for(bool comment:{false,true}) {
    const std::string full=comment?"1.01 C "+std::string(400,'x')+";S A=1;E":
        "1.01 P \""+std::string(400,'x')+";S X=2\";S A=3;E";
    const unsigned start=300;
    source::Reader input(full.data(),(uint16_t)full.size());source::CursorScope scope(input);
    const auto initial=focal_text::initial_line(source::Cursor(input),start);
    assert(initial.fragment && (comment?initial.comment:initial.quote=='\"'));
    char window[1025];strcpy(window,full.c_str()+start);
    const std::string original=window;
    assert(focal_text::transform(window,sizeof(window),true,&initial));
    if(comment)assert(original==window);
    else {
      assert(std::string(window).find(";S X=2\";SET A=3;EXIT")!=std::string::npos);
      focal_editor::Context context{initial,false};
      const u16 token=(u16)std::string(window).find("SET A=3");
      u16 cursor=token+4,len=(u16)strlen(window);
      assert(focal_editor::move(window,len,cursor,-1,&context) && cursor==token);
      cursor=token;
      assert(focal_editor::move(window,len,cursor,1,&context) && cursor==token+4);
      char copy[1025];strcpy(copy,window);u16 copy_len=len;
      assert(focal_editor::erase(copy,copy_len,cursor,sizeof(copy),&context));
      assert(std::string(copy).find(";A=3;EXIT")!=std::string::npos);
    }
    assert(focal_text::transform(window,sizeof(window),false,&initial));assert(original==window);
    assert(!focal_editor::operator_field(source::Cursor(input),(u16)full.size()));
  }
}
int main() {
  focal_page_context();
  {
    Disk disk;disk.original=std::string(65534,'x');
    Document doc({&disk,Disk::read_file,65534},disk.io());assert(doc.open());
    text_editor::Buffer editor{};assert(doc.seek(editor,33000));
    assert(disk.reads<=5); // lookback and window, including operator lookahead
  }
  {
    Disk disk;disk.original=std::string(34000,'x');
    Document doc({&disk,Disk::read_file,34000},disk.io(),256);assert(doc.open());
    text_editor::Buffer editor{};assert(doc.seek(editor,33000));
    const auto generation=doc.generation();
    for(unsigned i=0;i<10;++i)assert(doc.prepare(editor));
    assert(doc.generation()==generation); // idle frames must not repage
  }
  for(bool at_end:{false,true}) {
    Disk disk;disk.original="1.01 S A=1;";disk.original.resize(1300,' ');
    const unsigned token=at_end?253:1000;
    disk.original.replace(token,6,"RETURN");
    Document doc({&disk,Disk::read_file,1300},disk.io(),256);assert(doc.open());
    text_editor::Buffer editor{};assert(doc.seek(editor,at_end?0:1088));
    assert(std::string(doc.window).find("RETURN")!=std::string::npos);
    assert(!at_end || doc.used()==259);
    assert(at_end || doc.start()==1000);
  }
  static_assert(sizeof(Document)<3072,"editor must not acquire a source-sized RAM buffer");
  for(unsigned n:{0U,3585U,16384U,65534U}) {
    Disk disk;disk.original=std::string(n,'x');
    for(unsigned i=39;i<n;i+=40)disk.original[i]='\n';
    const std::string original=disk.original;
    std::string expected=original;
    {
      Document doc({&disk,Disk::read_file,(uint16_t)n},disk.io());assert(doc.open());
      text_editor::Buffer editor{};assert(doc.seek(editor,0));
      assert(contents(doc)==expected);
      for(unsigned target:{0U,n/2,n}) {
        assert(doc.seek(editor,(uint16_t)target));
        const unsigned pos=doc.start()+editor.cursor;
        assert(doc.prepare(editor));
        const bool room=expected.size()+3<=MAX_SIZE;
        assert(text_editor::insert_text(editor.source,editor.len,editor.cursor,editor.capacity,"ABC")==room);
        if(room) {
          expected.insert(pos,"ABC");assert(doc.accept(editor.len));
          assert(contents(doc)==expected);assert(doc.flush());assert(contents(doc)==expected);
        }
      }
      assert(disk.original==original); // original never rewritten by a draft
      assert(doc.seek(editor,doc.size()/2));
      const unsigned pos=doc.start()+editor.cursor;
      if(pos) {
        assert(text_editor::backspace(editor.source,editor.len,editor.cursor));
        expected.erase(pos-1,1);assert(doc.accept(editor.len));
        assert(contents(doc)==expected);
        disk.fail=0;disk.writes=0;
        assert(!doc.flush());assert(contents(doc)==expected);
        disk.fail=-1;assert(doc.flush());assert(contents(doc)==expected);
      }
    }
    assert(!disk.locked && disk.pages.empty());
  }
  puts("Paged source editor: bounded RAM, cross-page edits, 64 KiB files, cancel and failed writes PASS");
}
