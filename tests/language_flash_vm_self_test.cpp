#include "language_flash_fixture.hpp"
#include "language_vm_abi.hpp"
#include <string>
#include <vector>
#include <cmath>
#include <cstdio>
using namespace language_vm;
static unsigned compare_hits=0;
namespace language_vm {void compare_block_applied(uint16_t){++compare_hits;}}
struct Fixture {
  Disk disk;
  CompileResult compiled{};
  ExecutionState state{};
  Value variables[26]{},array[385]{};
  double refs[20]{};
  std::string printed;
  std::vector<double> numbers;
  unsigned inputs=0;
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
  // Hot APPs require the resident lookup service. The fixture's independent
  // ordered maps model that service; the actual C9 binary search has separate
  // storage/ARM tests. No full map is added to production RAM.
  std::map<uint32_t,uint32_t> pcs,lines;
#endif
  void bind_lookup(View& view) {
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
    view.lookup_context=this;
    view.lookup=[](void* raw,uint32_t key,bool number,uint32_t* out) {
      auto& f=*(Fixture*)raw;
      if(number) {
        auto it=f.pcs.find(key);*out=it==f.pcs.end()?UINT32_MAX:it->second;
      } else {
        auto it=f.lines.upper_bound(key);*out=it==f.lines.begin()?0:(--it)->second;
      }
      return true;
    };
#else
    (void)view;
#endif
  }
  flash::Input input() {return {&disk,[](void* raw,uint32_t at,uint8_t* out,uint16_t n){return Disk::read(raw,IMAGE,at,out,n);},compiled.size};}
  View view(flash::Reader& reader) {
    View result{};const auto e=inspect_flash(reader,disk.io(),result);
    if(e!=Error::NONE)fprintf(stderr,"inspect: %s\n",error_name(e));
    assert(e==Error::NONE);bind_lookup(result);return result;
  }
  void compile(Language language,const std::string& source) {
    language_vm::source::Reader text(source.data(),uint16_t(source.size()));
    compiled=compile_flash_source(language,text,disk.io());
    if(compiled.error!=Error::NONE)fprintf(stderr,"compile: %s at %u: %.100s\n",error_name(compiled.error),compiled.source_offset,source.c_str());
    assert(compiled.error==Error::NONE);
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
    uint8_t header[32],row[8];pcs.clear();lines.clear();
    assert(Disk::read(&disk,IMAGE,0,header,sizeof(header)));
    for(unsigned i=0;i<flash::word(header+18);++i) {
      assert(Disk::read(&disk,IMAGE,32+i*8,row,sizeof(row)));
      const uint32_t number=flash::dword(row),pc=flash::dword(row+4);
      pcs[number]=pc;lines[pc]=number;
    }
#endif
  }
  Bindings bindings() {return {variables,array,385,state.stack,MAX_STACK};}
  std::vector<uint8_t> bytes() {
    std::vector<uint8_t> raw(compiled.size);
    for(uint32_t at=0;at<compiled.size;) {
      const uint16_t n=uint16_t(std::min<uint32_t>(256,compiled.size-at));
      assert(Disk::read(&disk,IMAGE,at,raw.data()+at,n));at+=n;
    }
    return raw;
  }
  Services services(bool yield=false) {
    return {this,[](void*){return true;},
      [](void*,Function f,double a,double b){switch(f){case Function::ABS:return fabs(a);case Function::SQRT:return sqrt(a);default:return pow(a,b);}},
      nullptr,nullptr,
      [](void* raw,bool write,uint8_t id,double& value){auto& f=*(Fixture*)raw;if(write)f.refs[id]=value;else value=f.refs[id];return true;},
      [](void* raw,Event e,const char* text,uint16_t n,double& value){auto& f=*(Fixture*)raw;
        if(e==Event::TEXT || e==Event::TEXT_CONTINUE)f.printed.append(text,n);
        if(e==Event::NUMBER)f.numbers.push_back(value);
        if(e==Event::READ_INPUT){++f.inputs;value=7;}
        return true;
      },yield,false};
  }
  RunResult run(bool contiguous=false) {
    flash::Reader image(input());View v=view(image);std::vector<uint8_t> raw;
    if(contiguous){raw=bytes();v.reader=nullptr;v.bytes=raw.data();}
    auto result=language_vm::run(v,state.control,bindings(),services(),100000);
    if(result.error!=Error::NONE)fprintf(stderr,"run: %s at %u/%u\n",error_name(result.error),result.line,result.pc);
    assert(result.error==Error::NONE);return result;
  }
};
static void small_contiguous() {
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    const std::string text(1500,'x');
    const std::string source=language==Language::BASIC
      ? "10 DATA -.1,2,3;READ A;INPUT \"value?\",B;READ C;RESTORE 10;READ D\n"
        "20 FOR I=1 TO 3;@(I)=I*2;S=S+@(I);NEXT I\n"
        "30 S=S+CALL(100,4,5);IF S=21 .RA=S\n40 PRINT \""+text+"\";A;B;C;D;END\n100 RETURN ARG(1)+ARG(2)\n"
      : "1.0 S S=0;F I=1,3;D 2\n1.1 S S=S+CALL(3,4,5);S .RA=S;P \""+text+"\";P S;E\n"
        "2.0 A \"value?\",B;S S=S+B+I;R\n3.0 R ARG(1)+ARG(2)\n";
    Fixture paged,raw;paged.compile(language,source);raw.compile(language,source);
    assert(raw.compiled.size<=8192);
    const auto a=paged.run(),b=raw.run(true);
    assert(a.error==b.error && a.pc==b.pc && a.line==b.line && a.steps==b.steps);
    assert(paged.printed==raw.printed && paged.numbers==raw.numbers && paged.inputs==raw.inputs);
    for(unsigned i=0;i<26;++i)assert(paged.variables[i]==raw.variables[i]);
    for(unsigned i=0;i<385;++i)assert(paged.array[i]==raw.array[i]);
    assert(paged.refs[14]==(language==Language::BASIC?21:36) && raw.refs[14]==paged.refs[14]);
  }
  puts("Flash VM: small contiguous/paged LBV2 differential, arrays/CALL/DATA/INPUT/strings/steps PASS");
}
static std::string large(Language language,const char* tail) {
  const bool basic=language==Language::BASIC;
  std::string source=basic?"1 GOTO 30000\n":"1.0 G 9.0\n";
  for(unsigned i=0;i<5000;++i) {
    char line[48];if(basic)snprintf(line,sizeof(line),"%u A=1\n",i+2);
    else snprintf(line,sizeof(line),"%u.%u S A=1\n",2+i/1000,i%1000);
    source+=line;
  }
  source+=tail;assert(source.size()<source::MAX_SIZE);return source;
}
static void storage_descriptor() {
  ExecutionState state{};state.language=Language::BASIC;
  ValidatedImage certificate{};Value variables[26]{};uint8_t raw[HEADER_SIZE]{};
  ExecuteRequest request{};request.size=sizeof(request);request.version=REQUEST_VERSION;
  request.image=raw;request.image_size=sizeof(raw);request.variables=variables;
  OverlayRequest overlay{};overlay.size=sizeof(overlay);overlay.version=REQUEST_VERSION;
  overlay.execution=&request;overlay.state=&state;overlay.validated=&certificate;
  assert(execution_compatible(&overlay));
  request.paged={nullptr,[](void*,uint32_t,uint8_t*,uint16_t){return true;},sizeof(raw)};
  // A raw image must not hide a missing or mismatched Flash descriptor.
  assert(!execution_compatible(&overlay));
  flash::IO io{};request.storage=&io;assert(execution_compatible(&overlay));
  ++request.paged.size;assert(!execution_compatible(&overlay));
}
static void controls() {
  Fixture editor;
  editor.compile(Language::FOCAL,"1.10 B (0)1.20,1.20,1.20\n1.20 S .RB=42\n1.30 E\n");
  editor.run();assert(editor.refs[15]==42);
  Fixture basic;
  basic.compile(Language::BASIC,large(Language::BASIC,
    "30000 S=0;FOR I=1 TO 3;GOSUB 31000;NEXT I\n"
    "30010 IF S<>6 GOTO 9999\n30020 S=S+CALL(32000,4,5);.RA=S;END\n"
    "31000 S=S+I;RETURN\n32000 RETURN ARG(1)+ARG(2)\n"));
  assert(basic.run().pc>65536 && basic.refs[14]==15);
  Fixture focal;
  focal.compile(Language::FOCAL,large(Language::FOCAL,
    "9.0 S S=0;F I=1,1,3;D 10,I\n9.1 S S=S+CALL(11,4,5);S .RA=S;E\n"
    "10.0 S S=S+ARG(1);R\n11.0 R ARG(1)+ARG(2)\n"));
  assert(focal.run().pc>65536 && focal.refs[14]==15);
  // Reverse physical source order exercises the external merge in both
  // compilers, including the final map and all forward references.
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    std::string source=language==Language::BASIC?"999 END\n":"9.0 E\n";
    for(int i=500;i>0;--i) {
      char line[64];if(language==Language::BASIC)snprintf(line,sizeof(line),"%d A=A+1\n",i);
      else snprintf(line,sizeof(line),"%u.%u S A=A+1\n",1+unsigned(i)/100,unsigned(i)%100);
      source+=line;
    }
    Fixture f;f.compile(language,source);f.run();assert(f.variables[0]==500);
  }
}
static void focal_if_paths() {
  for(bool wide:{false,true}) {
    Fixture f;
    const char* tail=wide
        ? "9.0 B (A)9.1,9.2,9.3\n9.1 S .RB=-1;E\n9.2 S .RB=0;E\n9.3 S .RB=1;E\n"
        : "1.10 B (A)1.20,1.30,1.40\n1.20 S .RB=-1;E\n1.30 S .RB=0;E\n1.40 S .RB=1;E\n";
    f.compile(Language::FOCAL,wide?large(Language::FOCAL,tail):std::string(tail));
    for(int value:{-1,0,1}) {
      f.variables[0]=value;
      const auto result=f.run();assert(f.refs[15]==value && (!wide || result.pc>65536));
    }
  }
}
static void on_tables() {
  for(bool sub:{false,true})for(unsigned count:{1U,5U,6U,9U}) {
    std::string tail="30000 S=0;ON A "+std::string(sub?"GOSUB ":"GOTO ");
    for(unsigned i=0;i<count;++i)tail+=(i?",":"")+std::to_string(31000+i*10);
    tail+="\n30010 GOTO 32000\n";
    for(unsigned i=0;i<count;++i)
      tail+=std::to_string(31000+i*10)+" S="+std::to_string(i+1)+(sub?";RETURN\n":";GOTO 32000\n");
    tail+="32000 .RA=S;END\n";
    Fixture f;f.compile(Language::BASIC,large(Language::BASIC,tail.c_str()));
    for(unsigned selected=0;selected<=count+1;++selected) {
      f.variables[0]=selected;
      const auto result=f.run();
      assert(result.pc>65536 && f.refs[14]==(selected<=count?selected:0));
    }
  }
}
static void input_resume() {
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    Fixture f;
    f.compile(language,large(language,language==Language::BASIC
      ?"30000 S=0;FOR I=1 TO 2;GOSUB 31000;NEXT I;.RA=S;END\n31000 INPUT \"value?\",B;S=S+B;RETURN\n"
      :"9.0 S S=0;F I=1,2;D 10\n9.1 S .RA=S;E\n10.0 A \"value?\",B;S S=S+B;R\n"));
    bool resume=false;unsigned count=0;
    for(;;) {
      // Replacing APPs invalidates all native reader/cursor instances.
      flash::Reader image(f.input());const View v=f.view(image);
      auto result=language_vm::run(v,f.state.control,f.bindings(),f.services(true),10000,resume);
      if(result.error==Error::NONE)break;
      assert(result.error==Error::YIELDED && result.pc>65536 && ++count<=2);
      char prompt[96]={};const auto length=flash::word(v.at(result.pc+1));
      assert(length==6 && v.at(result.pc+3).read(prompt,length) && !strcmp(prompt,"value?"));
      uint8_t expression[INPUT_IMAGE_CAPACITY];
      auto compiled=compile_expression(language,"2+3",3,expression,sizeof(expression));View expression_view;
      assert(compiled.error==Error::NONE && inspect(expression,uint16_t(compiled.size),expression_view)==Error::NONE);
      auto evaluated=evaluate_input(expression_view,f.state,f.bindings(),f.services());
      assert(evaluated.error==Error::NONE && f.state.input_value==5);
      f.state.stack[f.state.control.sp++]=f.state.input_value;resume=true;
    }
    assert(count==2 && f.refs[14]==10 && !f.state.control.call_count && !f.state.control.loop_count);
  }
}
static void arithmetic_hints() {
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    for(bool short_block:{false,true}) {
      Fixture f;
      f.compile(language,large(language,language==Language::BASIC
        ?(short_block?"30000 B=-7;A=ABS(B);.RA=A;END\n":"30000 B=2;C=3;D=4;E=5;A=B+C+D+E;.RA=A;END\n")
        :(short_block?"9.0 S B=-7;S A=ABS(B);S .RA=A;E\n":"9.0 S B=2;S C=3;S D=4;S E=5;S A=B+C+D+E;S .RA=A;E\n")));
      bool found=false;
      {flash::Reader image(f.input());const View view=f.view(image);
        for(uint32_t pc=view.code;pc<view.end;pc=instruction_end(view,pc)) {
          if(Op(view.byte(pc))==(short_block?Op::INTEGER_SHORT:Op::INTEGER_SPAN)) {
            assert(pc>65536);found=true;
          }
        }
      }
      assert(found);f.run();assert(f.refs[14]==(short_block?7:14));
    }
  }
}
static void wide_compare_layout() {
  for(double value:{2.0,4.0,3.5,2147483647.0}) {
    Fixture f;f.compile(Language::BASIC,large(Language::BASIC,"30000 IF B<3 .RA=42;END\n"));
    f.variables[1]=value;uint32_t block=0;
    {flash::Reader image(f.input());const View view=f.view(image);
      for(uint32_t pc=view.code;pc<view.end;pc=instruction_end(view,pc)) {
        if(scalar_op(Op(view.byte(pc)))==Op::LOAD && pc>65536 &&
           view.byte(pc+2)>=uint8_t(Op::CONST_0) && view.byte(pc+2)<=uint8_t(Op::CONST_15) &&
           Op(view.byte(pc+3))==Op::COMPARE_FALSE) {
          assert(instruction_end(view,pc+3)==pc+9);block=pc;break;
        }
      }
    }
    assert(block);
    auto crc=[&]() {
      uint32_t state=0xFFFFFFFF;uint8_t bytes[256];
      for(uint32_t at=32;at<f.compiled.size;) {
        const uint16_t n=uint16_t(f.compiled.size-at<sizeof(bytes)?f.compiled.size-at:sizeof(bytes));
        assert(Disk::read(&f.disk,IMAGE,at,bytes,n));
        for(unsigned j=0;j<n;++j){state^=bytes[j];for(unsigned k=0;k<8;++k)state=(state>>1)^(0xEDB88320U&(0U-(state&1)));}at+=n;
      }
      flash::dword(f.disk.pages[IMAGE][0].data()+24,~state);
    };
    f.disk.pages[IMAGE][block/WRITE_BYTES][block%WRITE_BYTES]=uint8_t(Op::BLOCK_COMPARE);crc();
    const unsigned before=compare_hits;
    f.run();assert(f.refs[14]==(value<3?42:0));
    assert(compare_hits==before+(f.variables[1].integer()?1:0));
    uint8_t bad[4];flash::dword(bad,block+5);
    for(unsigned j=0;j<4;++j)f.disk.pages[IMAGE][(block+5+j)/WRITE_BYTES][(block+5+j)%WRITE_BYTES]=bad[j];
    crc();flash::Reader invalid(f.input());View view;
    assert(inspect_flash(invalid,f.disk.io(),view)==Error::INVALID_IMAGE);
  }
}
static void strings_data_and_failures() {
  const std::string text(1500,'x');Fixture f;
  f.compile(Language::BASIC,"10 DATA -.1,2,3\n20 READ A;INPUT B;READ C;RESTORE 10;READ D\n30 PRINT \""+text+"\";A;B;C;D\n");
  f.run();assert(f.printed==text && f.inputs==1 && f.numbers.size()==4 && f.numbers[0]==-.1 && f.numbers[1]==7 && f.numbers[2]==2 && f.numbers[3]==-.1);
  // A validated image losing a later page must stop with IO, before the
  // destination register changes. A fresh reader models an APP replacement.
  Fixture missing;missing.compile(Language::BASIC,large(Language::BASIC,"30000 .RA=42;END\n"));
  {flash::Reader image(missing.input());(void)missing.view(image);}
  missing.disk.pages[IMAGE].erase((missing.compiled.size-1)/WRITE_BYTES);
  flash::Reader image(missing.input());uint8_t h[32];assert(image.read(0,h,sizeof(h)));
  View v={nullptr,missing.compiled.size,flash::dword(h+12),flash::word(h+18),flash::word(h+16),h[6],Language(h[5]),false,false,missing.compiled.size,&image,true};
  missing.bind_lookup(v);
  auto result=language_vm::run(v,missing.state.control,missing.bindings(),missing.services(),100);
  assert(result.error==Error::IO && missing.refs[14]==0);
  Fixture duplicate;source::Reader source("2 A=1\n1 END\n2 END\n",18);
  assert(compile_flash_source(Language::BASIC,source,duplicate.disk.io()).error==Error::LINE);
}
int main(){small_contiguous();storage_descriptor();controls();focal_if_paths();on_tables();input_resume();arithmetic_hints();wide_compare_layout();strings_data_and_failures();puts("Flash VM: >64-KB calls/FOR/IF/parameters, external sorting, INPUT APP replacement, DATA, long text and lost pages PASS");}
