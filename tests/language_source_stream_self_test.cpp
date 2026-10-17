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
  static bool read(void* raw,uint16_t at,uint8_t* out,uint16_t n) {
    auto& f=*(File*)raw;++f.calls;if(n>f.largest)f.largest=n;
    if(f.fail>=0 && at>=f.fail)return false;
    assert(at<=f.text.size() && n<=f.text.size()-at);
    memcpy(out,f.text.data()+at,n);return true;
  }
  source::Input input() {return {this,read,(uint16_t)text.size()};}
};
static void compare(Language lang,const std::string& text,const ResourceSource* resources) {
  File f{text};source::Reader input(f.input());
  std::vector<uint8_t> actual(MAX_MODULE),expected(MAX_MODULE);
  auto sized=compile_source(lang,input,nullptr,MAX_MODULE,true,resources);
  auto made=compile_source(lang,input,actual.data(),MAX_MODULE,true,resources);
  auto old=compile(lang,text.data(),(uint16_t)text.size(),expected.data(),MAX_MODULE,true,resources);
  assert(sized.error==Error::NONE && made.error==Error::NONE && old.error==Error::NONE);
  assert(sized.size==made.size && made.size==old.size);
  assert(!memcmp(actual.data(),expected.data(),made.size));
  assert(f.largest<=source::PAGE_SIZE && f.calls);
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
int main() {
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
      for(auto* resources:{(const ResourceSource*)nullptr,&external,&owned})compare(lang,text,resources);
    }
    // Every token, numeric exponent, M8 byte and CR/LF boundary can cross a page.
    for(unsigned pad=0;pad<256;++pad) {
      std::string text(pad,' ');
      text+=lang==Language::BASIC?"10 A=1.25E-3:PRINT #8:3,A\n20 END":"1.01 SET A=1.25E-3;PRINT %8.3,A;EXIT";
      compare(lang,text,nullptr);
    }
    const std::string long_literal=lang==Language::BASIC
        ? "10 PRINT \""+std::string(65030,'z')+"\"\n20 END"
        : "1.01 PRINT \""+std::string(65030,'z')+"\";EXIT";
    compare(lang,long_literal,&external);
    File bad{head+std::string(4096,'x')+tail};bad.fail=256;
    source::Reader input(bad.input());
    assert(compile_source(lang,input,nullptr,MAX_MODULE).error==Error::IO);
    File nul{head+std::string(4096,'x')+tail};nul.text[2000]=0;
    source::Reader zero(nul.input());
    assert(compile_source(lang,zero,nullptr,MAX_MODULE).error==Error::SYNTAX);
  }
  puts("Streamed BASIC/FOCAL: 64 KiB source, 256-byte reads, page boundaries, resource offsets and I/O PASS");
}
