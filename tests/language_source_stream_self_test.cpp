#include "language_bytecode.hpp"
#include "language_resources.hpp"
#include "focal_source.hpp"
#include <assert.h>
#include <stdio.h>
#include <string>
#include <vector>
using namespace language_vm;
struct File {
  std::string text;
  unsigned calls=0, largest=0;
  int fail=-1;
  bool late_failure=false;
  static bool read(void* raw,uint16_t at,uint8_t* out,uint16_t n) {
    auto& f=*(File*)raw;++f.calls;if(n>f.largest)f.largest=n;
    assert(at<=f.text.size() && n<=f.text.size()-at);
    if(f.fail>=0 && at>=f.fail) {
      if(f.late_failure)memcpy(out,f.text.data()+at,n);
      return false;
    }
    memcpy(out,f.text.data()+at,n);return true;
  }
  source::Input input() {return {this,read,(uint16_t)text.size()};}
};
static void compare(Language lang,const std::string& text,const ResourceSource* resources,unsigned loan=0) {
  std::vector<uint8_t> storage(loan+2,0x5A);
  File f{text};source::Reader input(f.input(),loan?storage.data()+1:nullptr,loan);
  std::vector<uint8_t> actual(MAX_MODULE),expected(MAX_MODULE);
  auto sized=compile_source(lang,input,nullptr,MAX_MODULE,true,resources);
  auto made=compile_source(lang,input,actual.data(),MAX_MODULE,true,resources);
  auto old=compile(lang,text.data(),(uint16_t)text.size(),expected.data(),MAX_MODULE,true,resources);
  assert(sized.error==Error::NONE && made.error==Error::NONE && old.error==Error::NONE);
  assert(sized.size==made.size && made.size==old.size);
  assert(!memcmp(actual.data(),expected.data(),made.size));
  assert(f.largest<=(loan?loan:source::PAGE_SIZE) && f.calls);
  assert(storage.front()==0x5A && storage.back()==0x5A);
  if(text.size()>60000 && resources && resources->mode==ResourceMode::SOURCE)
    assert(f.calls<32000); // Repeated 4-KiB resources must compare in bounded spans.
  View v;assert(inspect(actual.data(),made.size,v)==Error::NONE);
  assert(v.source_size==text.size());
  if(resources && resources->mode==ResourceMode::SOURCE) {
    bool found=false;
    for(unsigned at=v.end;at<made.size;) {
      const auto* r=actual.data()+at;
      assert(valid_resource_recipe(r,(uint16_t)(made.size-at),v.source_size));
      for(unsigned i=0;i<r[2];++i)if(r[5+i*3] && resource_word(r+3+i*3)>32767)found=true;
      at+=3+3*r[2];
    }
    if(text.size()>40000)assert(found);
  }
}
static void compact_source() {
  for(unsigned pad:{0U,250U,16000U,60000U}) {
    File file{"1.01 COMMENT "+std::string(pad,'x')+"\r\n1.02 SET A=1;PRINT \"SET; RETURN\";EXIT\n"};
    std::string expected=file.text;expected.resize(expected.size()+1);
    assert(focal_text::transform(expected.data(),unsigned(expected.size()),false));
    expected.resize(strlen(expected.c_str()));
    source::Reader reader(file.input());focal_text::CompactSource compact(reader);
    assert(compact.good() && compact.size()==expected.size());
    auto input=compact.input();std::string actual(expected.size(),' ');
    for(unsigned step:{1U,63U,256U}) {
      for(unsigned at=0;at<actual.size();at+=step) {
        unsigned n=unsigned(actual.size())-at;if(n>step)n=step;
        assert(input.read(input.context,(uint16_t)at,(uint8_t*)actual.data()+at,(uint16_t)n));
      }
      assert(actual==expected);
    }
  }
}
static void distant_equal_spans() {
  File file{std::string(65534,'x')};
  source::Reader input(file.input());source::CursorScope scope(input);
  const source::Cursor begin(input);
  // Resource interning compares repeated chunks from distant source pages.
  // A single cache must not bounce once for each byte in those two spans.
  assert(source::equal(begin+32760,begin+40000,4096));
  assert(file.calls<400);
  file.text[44095]='y';
  source::Reader changed(file.input());source::CursorScope changed_scope(changed);
  assert(!source::equal(source::Cursor(changed,32760),source::Cursor(changed,40000),4096));
  file.fail=40000;
  source::Reader failed(file.input());source::CursorScope failed_scope(failed);
  assert(!source::equal(source::Cursor(failed,32760),source::Cursor(failed,40000),4096));
  assert(!failed.good());
}
static void borrowed_source() {
  // Guard the retained runtime/value banks on either side of the loan.
  uint8_t storage[1026];memset(storage,0x5A,sizeof(storage));
  for(auto lang:{Language::BASIC,Language::FOCAL}) {
    const std::string head=lang==Language::BASIC?"10 REM ":"1.01 COMMENT ";
    const std::string tail=lang==Language::BASIC?"\n20 A=42\n30 END\n":"\n1.02 SET A=42;EXIT\n";
    for(unsigned length:{1023U,1024U,1025U}) {
      File file{head+std::string(length-head.size()-tail.size(),'x')+tail};
      source::Reader input(file.input(),storage+1,1024);
      std::vector<uint8_t> actual(MAX_MODULE),expected(MAX_MODULE);
      const auto size=compile_source(lang,input,nullptr,MAX_MODULE);
      const auto made=compile_source(lang,input,actual.data(),MAX_MODULE);
      const auto old=compile(lang,file.text.data(),uint16_t(length),expected.data(),MAX_MODULE);
      assert(size.error==Error::NONE && made.error==Error::NONE && old.error==Error::NONE);
      assert(size.size==made.size && made.size==old.size);
      assert(!memcmp(actual.data(),expected.data(),made.size));
      if(length<=1024)assert(file.calls==1 && file.largest==length);
      else assert(file.calls>1 && file.largest==1024);
      assert(storage[0]==0x5A && storage[1025]==0x5A);
    }
    File failed{head+tail};failed.fail=0;
    source::Reader bad(failed.input(),storage+1,1024);
    assert(!bad.good() && failed.calls==1);
    assert(compile_source(lang,bad,nullptr,MAX_MODULE).error==Error::IO);
    assert(failed.calls==1); // Failed CRC/I/O must not retry via paging.
    File unloaned{head+tail};source::Reader paged(unloaned.input(),nullptr,1024);
    assert(compile_source(lang,paged,nullptr,MAX_MODULE).error==Error::NONE);
    assert(unloaned.calls && unloaned.largest<=source::PAGE_SIZE);
    // A second reader must revalidate the source; the loan is not a cache
    // that can survive a different revision, APP lifetime or workspace owner.
    File changed{head+tail};
    {source::Reader first(changed.input(),storage+1,1024);assert(first.good());}
    changed.fail=0;
    {source::Reader second(changed.input(),storage+1,1024);assert(!second.good());}
    assert(changed.calls==2);
    source::Input partial={nullptr,[](void*,uint16_t,uint8_t* out,uint16_t n){
      memset(out,'x',n);return false;},64};
    source::Reader late_failure(partial,storage+1,1024);
    assert(!late_failure.good());
    assert(compile_source(lang,late_failure,nullptr,MAX_MODULE).error==Error::IO);
  }
}
static void borrowed_window() {
  // The window pointer reuses memory_, and its size fits existing padding.
  // No larger Reader frame or second source-sized buffer is permitted.
  struct PreviousReader {
    source::Input input;
    const char* memory;
    uint8_t page[source::PAGE_SIZE];
    uint16_t begin,count;
    bool good;
  };
  static_assert(sizeof(source::Reader)==sizeof(PreviousReader),"Source window grew the reader");
  for(unsigned capacity:{257U,1024U,3784U,4004U}) {
    std::vector<uint8_t> storage(capacity+2,0x5A);
    for(unsigned length:{capacity+1,capacity*2+1,65534U}) {
      File file{std::string(length,'x')};
      for(unsigned i=0;i<length;++i)file.text[i]=char(1+i%251);
      source::Reader input(file.input(),storage.data()+1,capacity);
      assert(input.good() && !file.calls); // Oversized sources fill lazily.
      std::vector<uint8_t> output(length);
      assert(input.read(0,output.data(),length));
      assert(!memcmp(output.data(),file.text.data(),length));
      const unsigned stride=capacity/source::PAGE_SIZE*source::PAGE_SIZE;
      assert(file.calls==1+(length-capacity+stride-1)/stride && file.largest==capacity);
      for(unsigned at:{length-1,capacity,0U,capacity-1,capacity+1}) {
        const unsigned n=length-at<17?length-at:17;
        assert(input.read(uint16_t(at),output.data(),n));
        assert(!memcmp(output.data(),file.text.data()+at,n));
      }
      source::Reader direct(file.text.data(),uint16_t(length));
      assert(input.checksum()==direct.checksum());
      assert(!input.contains_nul());
      const auto reads=file.calls;
      assert(input.read(uint16_t(length),nullptr,0));
      assert(!input.read(uint16_t(length),output.data(),1));
      assert(!input.read(0,nullptr,1) && file.calls==reads && input.good());
      assert(storage.front()==0x5A && storage.back()==0x5A);
    }
    for(bool late:{false,true}) {
      File file{std::string(capacity+1,'x')};
      file.fail=int(capacity/source::PAGE_SIZE*source::PAGE_SIZE);file.late_failure=late;
      source::Reader input(file.input(),storage.data()+1,capacity);
      std::vector<uint8_t> output(file.text.size());
      assert(!input.read(0,output.data(),output.size()) && !input.good() && file.calls==2);
      assert(!input.read(0,output.data(),1) && file.calls==2);
      for(auto language:{Language::BASIC,Language::FOCAL})
        assert(compile_source(language,input,nullptr,MAX_MODULE).error==Error::IO && file.calls==2);
      assert(storage.front()==0x5A && storage.back()==0x5A);
    }
  }
  for(unsigned capacity:{0U,1U,255U,256U}) {
    uint8_t storage[258];memset(storage,0x5A,sizeof(storage));
    File file{std::string(1025,'x')};source::Reader input(file.input(),storage+1,capacity);
    uint8_t output[1025];assert(input.read(0,output,sizeof(output)));
    assert(file.calls==5 && file.largest==source::PAGE_SIZE);
    for(auto byte:storage)assert(byte==0x5A); // Too-small loans stay untouched.
  }
  File invalid{std::string(65535,'x')};uint8_t storage[1024];
  source::Reader too_large(invalid.input(),storage,sizeof(storage));
  assert(!too_large.good() && !invalid.calls);
  source::Reader no_callback({nullptr,nullptr,1025},storage,sizeof(storage));
  assert(!no_callback.good());
}
int main() {
  borrowed_source();
  borrowed_window();
  distant_equal_spans();
  compact_source();
  // Keyword matching must not wrap at 256 letters after lifting the file cap.
  const std::string bad_keyword="10 END"+std::string(256,'A')+"\n";
  File bad_command{bad_keyword};source::Reader bad_reader(bad_command.input());
  assert(compile_source(Language::BASIC,bad_reader,nullptr,MAX_MODULE).error!=Error::NONE);
  const ResourceSource external={42,9,ResourceMode::SOURCE},owned={42,9,ResourceMode::EMBEDDED};
  for(auto lang:{Language::BASIC,Language::FOCAL}) {
    const std::string head=lang==Language::BASIC?"10 REM ":"1.01 COMMENT ";
    const std::string tail=lang==Language::BASIC?"\r\n20 A=CALL(100,7):PRINT \"\x80 streamed\";A\n30 END\n100 RETURN ARG(1)*6\n":
        "\r\n1.02 SET A=CALL(2,7);PRINT \"\x80 streamed\",A;EXIT\n2.01 RETURN ARG(1)*6\n";
    for(unsigned length:{3585U,16384U,40000U,65534U}) {
      std::string text=head+std::string(length-head.size()-tail.size(),'x')+tail;
      for(auto* resources:{(const ResourceSource*)nullptr,&external,&owned}) {
        compare(lang,text,resources);
        compare(lang,text,resources,lang==Language::BASIC?3784:4004);
      }
    }
    // Every token, numeric exponent, M8 byte and CR/LF boundary can cross a page.
    for(unsigned pad=0;pad<256;++pad) {
      std::string text(pad,' ');
      text+=lang==Language::BASIC?"10 A=1.25E-3:PRINT #8:3,A\n20 END":"1.01 SET A=1.25E-3;PRINT %8.3,A;EXIT";
      compare(lang,text,nullptr);
      compare(lang,text,nullptr,257);
    }
    const std::string long_literal=lang==Language::BASIC
        ? "10 PRINT \""+std::string(65030,'z')+"\"\n20 END"
        : "1.01 PRINT \""+std::string(65030,'z')+"\";EXIT";
    compare(lang,long_literal,&external);
    compare(lang,long_literal,&external,lang==Language::BASIC?3784:4004);
    File bad{head+std::string(4096,'x')+tail};bad.fail=256;
    source::Reader input(bad.input());
    assert(compile_source(lang,input,nullptr,MAX_MODULE).error==Error::IO);
    File nul{head+std::string(4096,'x')+tail};nul.text[2000]=0;
    source::Reader zero(nul.input());
    assert(compile_source(lang,zero,nullptr,MAX_MODULE).error==Error::SYNTAX);
  }
  puts("Streamed BASIC/FOCAL: 64 KiB, full loans/windows/256-byte fallback, unchanged Reader size, boundaries, resource offsets and sticky I/O PASS");
}
