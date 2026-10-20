#include "language_linked_program.hpp"
#include "language_flash_fixture.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace language_vm;
namespace {
using Bytes=std::vector<uint8_t>;
Bytes compile_image(Language language,const char* text,bool wide) {
  if(wide) {
    Disk disk;source::Reader source(text,uint16_t(strlen(text)));
    auto c=compile_flash_source(language,source,disk.io());
    if(c.error!=Error::NONE)std::fprintf(stderr,"compile %s: %s at %u\n",text,error_name(c.error),c.line);
    assert(c.error==Error::NONE);Bytes out(c.size);
    for(uint32_t at=0;at<c.size;) {auto n=uint16_t(std::min<uint32_t>(1024,c.size-at));assert(Disk::read(&disk,flash::IMAGE,at,out.data()+at,n));at+=n;}
    return out;
  }
  Bytes out(MAX_MODULE);auto c=compile(language,text,uint16_t(strlen(text)),out.data(),uint16_t(out.size()));
  if(c.error!=Error::NONE)std::fprintf(stderr,"compile %s: %s at %u\n",text,error_name(c.error),c.line);
  assert(c.error==Error::NONE);out.resize(c.size);return out;
}
void seal(Bytes& b){flash::dword(b.data()+24,checksum(b.data()+linked::HEADER_BYTES,b.size()-linked::HEADER_BYTES));flash::dword(b.data()+28,checksum(b.data(),28));}
Bytes package(const std::vector<Bytes>& images) {
  Bytes out(linked::HEADER_BYTES+images.size()*linked::ENTRY_BYTES);
  memcpy(out.data(),"LVP1",4);out[4]=linked::VERSION;
  flash::word(out.data()+6,uint16_t(images.size()));flash::dword(out.data()+12,1);
  flash::dword(out.data()+16,uint32_t(images.size()*linked::ENTRY_BYTES));
  for(unsigned i=0;i<images.size();++i) {
    auto* e=out.data()+linked::HEADER_BYTES+i*linked::ENTRY_BYTES;
    flash::dword(e,i+1);flash::dword(e+4,uint32_t(out.size()));
    flash::dword(e+8,uint32_t(images[i].size()));flash::dword(e+12,100+i);
    out.insert(out.end(),images[i].begin(),images[i].end());
  }
  flash::dword(out.data()+8,uint32_t(out.size()));seal(out);return out;
}
struct Fixture {
  Bytes bytes;linked::Member members[8];linked::Program program;linked::Session session{};
  Value variables[2][26]={},arrays[2][385]={},stack[MAX_STACK]={};
  double refs[20]={};uint32_t revision=1,polls=0,enters=0,transitions=0;
  unsigned invalidate_at=0,stop_at=0,math_calls=0,random_calls=0,value_calls=0;
  unsigned loans=0,releases=0;bool whole_mode;
  bool free_on_reference=false,free_on_math=false;std::vector<unsigned> order;
  Disk scratch;
  static uint32_t epoch(void* p){return ((Fixture*)p)->revision;}
  explicit Fixture(Bytes b,bool paged=false,bool whole=false):bytes(std::move(b)),whole_mode(whole) {
    linked::Input in{};in.bytes=paged?nullptr:bytes.data();in.size=uint32_t(bytes.size());
    in.epoch_context=this;in.epoch=epoch;
    if(paged)in.paged={this,[](void* p,uint32_t at,uint8_t* out,uint16_t n){auto& f=*(Fixture*)p;if(at>f.bytes.size() || n>f.bytes.size()-at)return false;memcpy(out,f.bytes.data()+at,n);return true;},in.size};
    const auto error=linked::inspect(in,members,8,program,scratch.io());
    if(error!=Error::NONE)std::fprintf(stderr,"inspect %s\n",error_name(error));
    assert(error==Error::NONE && linked::start(program,session));
  }
  linked::Host host() {
    linked::Host h={this,[](void* p,Language language,Bindings& b){auto& f=*(Fixture*)p;unsigned i=language==Language::BASIC?0:1;b={f.variables[i],f.arrays[i],uint16_t(i?64:385),f.stack,MAX_STACK};return true;},
      [](void* p,uint32_t symbol,uint16_t id,Language){auto& f=*(Fixture*)p;assert(id==99+symbol);++f.enters;f.order.push_back(symbol);return true;},
      [](void* p,uint32_t,uint32_t& next){auto& f=*(Fixture*)p;++f.transitions;next=uint32_t(f.refs[18]);return true;}};
    if(whole_mode && !program.input.bytes) {
      h.borrow=[](void* p,const linked::Member& m,const uint8_t*& image){auto& f=*(Fixture*)p;++f.loans;image=f.bytes.data()+m.offset;return true;};
      h.release=[](void* p,const uint8_t* image){assert(image);++((Fixture*)p)->releases;};
    }
    return h;
  }
  Services services() {
    Services s={};s.context=this;
    s.service=[](void* p){auto& f=*(Fixture*)p;++f.polls;if(f.invalidate_at==f.polls)++f.revision;return !f.stop_at || f.polls<f.stop_at;};
    s.reference=[](void* p,bool write,uint8_t ref,double& v){auto& f=*(Fixture*)p;if(ref>=20)return false;if(write)f.refs[ref]=v;else v=f.refs[ref];if(f.free_on_reference){++f.revision;Bytes{}.swap(f.bytes);}return true;};
    s.math=[](void* p,Function fn,double a,double b){auto& f=*(Fixture*)p;++f.math_calls;
      assert((fn==Function::SQRT && a==16) || (unsigned(fn)==255 && a==2 && b==3));
      if(f.free_on_math){++f.revision;Bytes{}.swap(f.bytes);}return fn==Function::SQRT?4.:8.;};
    s.random=[](void* p){++((Fixture*)p)->random_calls;return .25;};
    s.value=[](void* p,Function fn){auto& f=*(Fixture*)p;++f.value_calls;assert(fn==Function::COLS);return 26.;};
    s.event=[](void*,Event,const char*,uint16_t,double&){return true;};return s;
  }
  linked::Result run(uint32_t budget=0,const Value* input=nullptr){
    if(!whole_mode)return linked::execute(program,session,host(),services(),budget,input);
    assert(!budget && !input);
    const auto r=linked::execute_whole_with(program,session,host(),services(),language_vm::run);
    assert(loans==releases);return r;
  }
};
void basics(bool wide,bool paged,bool whole=false) {
  Fixture f(package({compile_image(Language::BASIC,"10 A=A+1;@(1)=@(1)+3;.RE=2;END\n",wide),
    compile_image(Language::BASIC,"10 A=A+2;@(2)=@(1)+A;.RE=0;END\n",wide)}),paged,whole);
  const auto r=f.run();assert(r.status==linked::Status::DONE && r.members==2 && f.enters==2);
  assert(f.variables[0][0]==Value(3) && f.arrays[0][1]==Value(3) && f.arrays[0][2]==Value(6));
  assert((f.order==std::vector<unsigned>{1,2}) && r.source_id==101 && f.polls>=2);
}
void input_and_limits(bool wide,bool paged) {
  Fixture reference(package({compile_image(Language::BASIC,"10 A=7;INPUT B\n20 A=A+B;.RE=2;END\n",wide),
    compile_image(Language::BASIC,"10 A=A*2;.RE=0;END\n",wide)}),paged);
  auto answer=reference.run();assert(answer.status==linked::Status::AWAIT_INPUT && reference.enters==1);
  auto waiting=reference.run();assert(waiting.status==linked::Status::AWAIT_INPUT && reference.enters==1);
  Value input=5;answer=reference.run(0,&input);
  assert(answer.status==linked::Status::DONE && reference.variables[0][0]==Value(24) && reference.enters==2);
  for(unsigned budget:{1U,2U,5U,31U,32U,33U}) {
    Fixture f(reference.bytes,paged);linked::Result r=f.run(budget);unsigned calls=1;
    while(r.status!=linked::Status::DONE) {
      assert(++calls<200 && (r.status==linked::Status::BUDGET || r.status==linked::Status::AWAIT_INPUT));
      const bool needs_input=r.status==linked::Status::AWAIT_INPUT;
      r=f.run(budget,needs_input?&input:nullptr);
    }
    assert(f.variables[0][0]==Value(24) && f.enters==2 && f.transitions==2 && r.steps==answer.steps);
  }
}
void isolation(bool wide,bool paged,bool whole=false) {
  Fixture f(package({compile_image(Language::BASIC,"10 A=9;@(1)=17;.RE=2;END\n",wide),
    compile_image(Language::FOCAL,"1.10 S A=4;S Z(1)=6;S B=Z(1);S .RE=3;E\n",wide),
    compile_image(Language::BASIC,"10 B=A+@(1);.RE=0;END\n",wide)}),paged,whole);
  assert(f.run().status==linked::Status::DONE);
  assert(f.variables[0][1]==Value(26) && f.variables[1][0]==Value(4) && f.variables[1][1]==Value(6));
}
void errors(bool wide,bool paged,bool whole=false) {
  Bytes p=package({compile_image(Language::BASIC,"10 A=A+1;.RE=1;END\n",wide)});
  Fixture f(p,paged,whole);f.stop_at=3;assert(f.run().run.error==Error::STOPPED && f.enters==3);
  Fixture changed(p,paged,whole);changed.invalidate_at=2;
  assert(changed.run().status==linked::Status::INVALIDATED && changed.enters==2);
  Fixture stale(p,paged,whole);++stale.revision;assert(stale.run().status==linked::Status::INVALIDATED && !stale.enters);
  Fixture missing(package({compile_image(Language::BASIC,"10 .RE=9;END\n",wide)}),paged,whole);
  auto r=missing.run();assert(r.status==linked::Status::UNRESOLVED && r.symbol==9 && r.members==1);
  Fixture runtime(package({compile_image(Language::BASIC,"10 A=1/0;END\n",wide)}),paged,whole);
  r=runtime.run();assert(r.status==linked::Status::ERROR && r.run.error!=Error::NONE && r.source_id==100 && r.run.line==10);
  Fixture evicted(package({compile_image(Language::BASIC,"10 .RE=0;END\n",wide)}),paged,whole);
  evicted.free_on_reference=true;assert(evicted.run().status==linked::Status::INVALIDATED && evicted.bytes.empty());
  Fixture math(package({compile_image(Language::BASIC,"10 A=SQRT(16);END\n",wide)}),paged,whole);
  math.free_on_math=true;assert(math.run().status==linked::Status::INVALIDATED && math.bytes.empty());
  Fixture restarted(p,paged,whole);assert(!linked::start(restarted.program,restarted.session,99));
  assert(restarted.run().status==linked::Status::ERROR && !restarted.enters);
  Fixture bad_phase(p,paged,whole);bad_phase.session.phase=linked::Phase(255);
  assert(bad_phase.run().status==linked::Status::ERROR && !bad_phase.enters);
}
void callbacks(bool wide,bool paged,bool whole=false) {
  Fixture f(package({compile_image(Language::BASIC,"10 A=SQRT(16)+2^3+COLS;B=RND();.RE=0;END\n",wide)}),paged,whole);
  assert(f.run().status==linked::Status::DONE && f.variables[0][0]==Value(38) && f.variables[0][1]==Value(.25));
  assert(f.math_calls==2 && f.value_calls==1 && f.random_calls==1);
}
void invalid_images() {
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
  constexpr bool wide=true;
#else
  constexpr bool wide=false;
#endif
  const Bytes p=package({compile_image(Language::BASIC,"10 END\n",wide),compile_image(Language::BASIC,"10 END\n",wide)});
  auto rejected=[](Bytes b){linked::Member members[2];linked::Program out;out.count=17;
    linked::Input in{};in.bytes=b.data();in.size=uint32_t(b.size());
    Disk scratch;assert(linked::inspect(in,members,2,out,scratch.io())!=Error::NONE && !out.count && !out.members);};
  for(size_t n=0;n<p.size();++n){Bytes b(p.begin(),p.begin()+n);rejected(b);}
  for(size_t n=0;n<p.size();++n){auto b=p;b[n]^=1;rejected(b);}
  auto b=p;flash::dword(b.data()+linked::HEADER_BYTES+linked::ENTRY_BYTES,1);seal(b);rejected(b);
  b=p;flash::dword(b.data()+linked::HEADER_BYTES+4,UINT32_MAX);seal(b);rejected(b);
  b=p;flash::dword(b.data()+12,999);seal(b);rejected(b);
  b=p;flash::dword(b.data()+linked::HEADER_BYTES+12,65536);seal(b);rejected(b);
}
void large_paged_and_failures() {
  std::string text="1 A=32000;GOTO A\n";
  for(unsigned i=2;i<5002;++i)text+=std::to_string(i)+" A=1\n";
  text+="32000 B=42;.RE=0;END\n";
  auto bytes=package({compile_image(Language::BASIC,text.c_str(),true)});
  assert(bytes.size()>65536);
  Fixture f(bytes,true);auto result=f.run();
  assert(result.status==linked::Status::DONE && f.variables[0][1]==Value(42) && result.run.pc>65536);
  Fixture whole(bytes,false,true);result=whole.run();
  assert(result.status==linked::Status::DONE && whole.variables[0][1]==Value(42) && result.run.pc>65536);
  Fixture io(std::move(bytes),true);
  io.program.input.paged.read=[](void*,uint32_t,uint8_t*,uint16_t){return false;};
  assert(io.run().status==linked::Status::ERROR);
  Fixture input(package({compile_image(Language::BASIC,"10 INPUT A;.RE=0;END\n",true)}),true);
  assert(input.run().status==linked::Status::AWAIT_INPUT);++input.revision;
  const Value answer=7;assert(input.run(0,&answer).status==linked::Status::INVALIDATED);
  auto graph=package({compile_image(Language::FOCAL,"1.10 GRAPH X,-1,1,-1,1;EXIT\n",true)});
  linked::Input in{};in.bytes=graph.data();in.size=uint32_t(graph.size());
  linked::Member member;linked::Program out;Disk scratch;
  assert(linked::inspect(in,&member,1,out,scratch.io())==Error::GRAPHICS_UNAVAILABLE && !out.count);
}
void invalidated_alias_directory() {
  const auto image=compile_image(Language::BASIC,"10 A=1;END\n",true);
  auto bytes=package({image,image,image});
  const auto first=bytes.data()+linked::HEADER_BYTES;
  const auto offset=flash::dword(first+4);
  for(unsigned i=1;i<3;++i) {
    auto record=bytes.data()+linked::HEADER_BYTES+i*linked::ENTRY_BYTES;
    flash::dword(record+4,offset);flash::dword(record+12,100);
  }
  bytes.resize(offset+image.size());flash::dword(bytes.data()+8,uint32_t(bytes.size()));seal(bytes);
  struct Source {Bytes bytes;uint32_t revision=1;unsigned stale_reads=0;} source{std::move(bytes)};
  linked::Input in{};in.size=uint32_t(source.bytes.size());in.epoch_context=&source;
  in.epoch=[](void* raw){return ((Source*)raw)->revision;};
  in.paged={&source,[](void* raw,uint32_t at,uint8_t* data,uint16_t size) {
    auto& s=*(Source*)raw;
    if(s.revision!=1){++s.stale_reads;return false;}
    if(at>s.bytes.size() || size>s.bytes.size()-at)return false;
    memcpy(data,s.bytes.data()+at,size);
    if(at==linked::HEADER_BYTES+linked::ENTRY_BYTES && size==linked::ENTRY_BYTES) {
      ++s.revision;Bytes{}.swap(s.bytes);
    }
    return true;
  },in.size};
  linked::Member members[3];linked::Program out;Disk scratch;
  assert(linked::inspect(in,members,3,out,scratch.io())==Error::IO);
  assert(source.revision==2 && !source.stale_reads && !out.count);
}
unsigned kernel_calls,loan_calls,release_calls;
RunResult external_kernel(const View& v,Continuation& c,const Bindings& b,const Services& h,uint32_t n,bool resume) {
  ++kernel_calls;assert(v.bytes && !v.reader);return run(v,c,b,h,n,resume);
}
void borrowed_external_kernel() {
  Fixture f(package({compile_image(Language::BASIC,"10 A=9;INPUT B;.RE=2;END\n",true),
      compile_image(Language::BASIC,"10 A=A+B;.RE=0;END\n",true)}),true);
  auto host=f.host();host.borrow=[](void* raw,const linked::Member& member,const uint8_t*& image) {
    ++loan_calls;image=((Fixture*)raw)->bytes.data()+member.offset;return true;
  };
  host.release=[](void*,const uint8_t* image){assert(image);++release_calls;};
  kernel_calls=loan_calls=release_calls=0;
  auto r=linked::execute_with(f.program,f.session,host,f.services(),external_kernel,5);
  Value input=4;unsigned calls=0;
  while(r.status!=linked::Status::DONE) {
    assert(++calls<100);
    const auto* value=r.status==linked::Status::AWAIT_INPUT?&input:nullptr;
    assert(loan_calls==release_calls && kernel_calls==loan_calls);
    r=linked::execute_with(f.program,f.session,host,f.services(),external_kernel,5,value);
  }
  assert(f.variables[0][0]==Value(13) && loan_calls==release_calls && kernel_calls==loan_calls);
  Fixture failed(f.bytes,true);auto bad=host;bad.context=&failed;
  bad.borrow=[](void* raw,const linked::Member& member,const uint8_t*& image) {
    ++loan_calls;image=((Fixture*)raw)->bytes.data()+member.offset;return false;
  };
  assert(linked::execute_with(failed.program,failed.session,bad,failed.services(),external_kernel).status==linked::Status::ERROR);
  assert(loan_calls==release_calls && kernel_calls+1==loan_calls);
  Fixture stopped(f.bytes,true);stopped.stop_at=1;host.context=&stopped;
  assert(linked::execute_with(stopped.program,stopped.session,host,stopped.services(),external_kernel).run.error==Error::STOPPED);
  assert(loan_calls==release_calls);
}
void whole_contract() {
  auto image=package({compile_image(Language::BASIC,"10 INPUT A\n20 A=A+2;.RE=0;END\n",true)});
  Fixture input(image,false,true);
  assert(input.run().status==linked::Status::AWAIT_INPUT);
  uint8_t suspended[sizeof(input.session)];memcpy(suspended,&input.session,sizeof(suspended));
  const auto enters=input.enters;
  assert(input.run().run.error==Error::INVALID_IMAGE && input.enters==enters);
  assert(!memcmp(suspended,&input.session,sizeof(suspended)));
  Value answer=5;
  assert(linked::execute(input.program,input.session,input.host(),input.services(),0,&answer).status==linked::Status::DONE);
  assert(input.variables[0][0]==Value(7) && input.enters==enters);

  Fixture limit(package({compile_image(Language::BASIC,"10 .RE=0;END\n",true)}),true,true);
  const auto limited=[](const View& v,Continuation& c,const Bindings& b,const Services& h,uint32_t budget,bool resume) {
    assert(v.wide && v.bytes && !v.reader && !budget && !resume);
    return language_vm::run(v,c,b,h,1,false);
  };
  assert(linked::execute_whole_with(limit.program,limit.session,limit.host(),limit.services(),limited).status==linked::Status::BUDGET);
  assert(limit.session.phase==linked::Phase::RUN && limit.loans==limit.releases);
  uint8_t cursor[sizeof(limit.session)];memcpy(cursor,&limit.session,sizeof(cursor));
  assert(limit.run().run.error==Error::INVALID_IMAGE && !memcmp(cursor,&limit.session,sizeof(cursor)));
  assert(linked::execute(limit.program,limit.session,limit.host(),limit.services()).status==linked::Status::DONE);

  // No raw image means a real error, never an implicit paged fallback.
  Fixture no_loan(image,true);
  no_loan.program.input.paged.read=[](void*,uint32_t,uint8_t*,uint16_t)->bool{assert(false);return false;};
  assert(linked::execute_whole_with(no_loan.program,no_loan.session,no_loan.host(),no_loan.services(),language_vm::run).run.error==Error::IO);
  Fixture null_loan(image,true,true);auto host=null_loan.host();
  host.borrow=[](void*,const linked::Member&,const uint8_t*& p){p=nullptr;return true;};
  assert(linked::execute_whole_with(null_loan.program,null_loan.session,host,null_loan.services(),language_vm::run).run.error==Error::IO);
  Fixture failed(image,true,true);host=failed.host();
  host.borrow=[](void* p,const linked::Member& m,const uint8_t*& out){auto& f=*(Fixture*)p;++f.loans;out=f.bytes.data()+m.offset;return false;};
  assert(linked::execute_whole_with(failed.program,failed.session,host,failed.services(),language_vm::run).run.error==Error::IO);
  assert(failed.loans==1 && failed.releases==1);
  Fixture stale(image,true,true);host=stale.host();
  host.borrow=[](void* p,const linked::Member& m,const uint8_t*& out){auto& f=*(Fixture*)p;++f.loans;out=f.bytes.data()+m.offset;++f.revision;Bytes{}.swap(f.bytes);return true;};
  assert(linked::execute_whole_with(stale.program,stale.session,host,stale.services(),language_vm::run).status==linked::Status::INVALIDATED);
  assert(stale.loans==1 && stale.releases==1);

  for(unsigned bad=0;bad<3;++bad) {
    Fixture f(image,false,true);
    if(bad==0)f.members[0].validated.wide=false;
    if(bad==1)f.members[0].validated.magic=0;
    if(bad==2)f.members[0].validated.flags|=1;
    assert(f.run().run.error==Error::INVALID_IMAGE && !f.enters);
  }
  Fixture done(package({compile_image(Language::BASIC,"10 .RE=0;END\n",true)}),false,true);
  assert(done.run().status==linked::Status::DONE);const auto count=done.enters;
  assert(done.run().status==linked::Status::DONE && done.enters==count);
}
}
int main() {
  for(bool wide:{false,true})for(bool paged:{false,true}) {
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
    if(!wide)continue;
#endif
    if(paged && !wide)continue;
    basics(wide,paged);input_and_limits(wide,paged);isolation(wide,paged);errors(wide,paged);callbacks(wide,paged);
  }
  invalid_images();large_paged_and_failures();invalidated_alias_directory();borrowed_external_kernel();
  for(bool paged:{false,true}) {
    basics(true,paged,true);isolation(true,paged,true);errors(true,paged,true);callbacks(true,paged,true);
  }
  whole_contract();
  std::puts("linked VM: unchanged LBV1/LBV2, shared banks, BASIC/FOCAL isolation, INPUT/budgets, epoch/ESC/errors and corrupt containers PASS");
}
