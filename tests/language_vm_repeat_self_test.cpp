#include "language_vm_repeat_fixture.hpp"
#include "language_flash_program.hpp"
#include "language_flash_fixture.hpp"
#include "app_flow.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
#include <string>

using namespace language_vm;
using namespace language_vm::flash;
using C=loadable_module::Command;
namespace {
unsigned executions,inputs,finishes,polls,starts;
bool cancel_input,stop,fail_execute,fail_finish,fail_input,mutate;
bool changed;
PageCache<32768>* live_cache;
CompilerContext* active;
uint8_t page[WRITE_BYTES];
std::vector<Event> events;
double external;
bool service(void*) {
  ++polls;
  if(mutate && !changed) {
    changed=true;
    for(unsigned i=0;i<80;++i)live_cache->put(2,uint16_t(100+i),i,page);
  }
  return !stop;
}
bool event(void*,Event e,const char*,uint16_t,double&) {events.push_back(e);return true;}
bool reference(void*,bool write,uint8_t,double& value) {if(write)external=value;else value=external;return true;}
const Services services={nullptr,service,nullptr,nullptr,nullptr,reference,event,true,true};
uint32_t execute(OverlayRequest* p) {
  ++executions;if(fail_execute)return 0;
  assert(execution_compatible(p));View v;assert(validated_view(*p,v));
  auto& s=*p->state;auto& r=*p->execution;
  if(p->action==OverlayAction::ABORT) {r.result.error=s.cancelled?Error::STOPPED:Error::IO;return 1;}
  const Bindings b={r.variables,r.array,s.array_count,s.stack,MAX_STACK};
  if(p->action==OverlayAction::EXPRESSION){r.result=evaluate_input(v,s,b,services);return 1;}
  const bool resume=p->action==OverlayAction::RESUME;
  if(resume)s.stack[s.control.sp++]=s.input_value;
  else {++starts;assert(!s.control.sp && !s.control.call_count && !s.control.loop_count && !s.output[0]);}
  r.result=run(v,s.control,b,services,0,resume);s.steps+=r.result.steps;r.result.steps=s.steps;
  if(r.result.error==Error::YIELDED) {
    assert(Op(v.byte(r.result.pc))==Op::READ_INPUT);
    s.prompt_offset=r.result.pc+3;s.prompt_length=word(v.at(r.result.pc+1).raw());
  }
  return 1;
}
uint32_t input(InputRequest* r) {
  ++inputs;if(fail_input)return 0;
  if(cancel_input){r->result=InputResult::CANCELLED;return 1;}
  if(r->language==Language::FOCAL){r->result=InputResult::VALUE;r->value=3;return 1;}
  const auto expression=compile_expression(Language::BASIC,"1+2",3,r->image,r->capacity);
  assert(expression.error==Error::NONE);r->result=InputResult::EXPRESSION;r->image_size=expression.size;
  return 1;
}
uint32_t finish(OverlayRequest*) {++finishes;return !fail_finish;}
app_flow::Status invoke(void*,const app_flow::Target& t,app_flow::Step& step) {
  assert(step.context==active && step.context_size==sizeof(*active));
  uint32_t ok=t.kind==MK61_APP_KIND_LANGUAGE_VM?flow_vm(&step,execute):
      flow_input(&step,validate_execution,input,finish);
  return ok?MK61_FLOW_OK:MK61_FLOW_CORRUPT;
}
struct Fixture {
  Disk disk;
  PageCache<32768> cache;
  ValidatedImage validated{};
  PersistentValues values{};
  uint32_t size=0;
  Fixture(Language language,const char* source) {
    source::Reader text(source,uint16_t(strlen(source)));
    const auto compiled=compile_flash_source(language,text,disk.io(),true);
    assert(compiled.error==Error::NONE);size=compiled.size;
    Reader reader({&disk,[](void* raw,uint32_t at,uint8_t* out,uint16_t n){return Disk::read(raw,IMAGE,at,out,n);},size});View view;
    assert(inspect_flash(reader,disk.io(),view)==Error::NONE);
    validated={VALIDATED_MAGIC,view.size,view.code,view.source_size,view.end,view.lines,
        view.stack,uint8_t((view.requires_rf?2:0)|(view.byte(7)&12)),language,true};
    assert(size<=8192);
    cache.remember_image(1,{123,456,0,42,2,3,4,0,validated});
  }
  void warm() {const uint8_t* image=nullptr;assert(cache.borrow(1,4,size,disk.io(),image) && image);cache.release(image);}
  uint32_t run_call(Language language,C command,uint32_t mode=0) {
    RepeatImage image(cache,1,42,123,language);assert(image);
    assert(image.source_stamp()==456 && image.source()==42);
    CompilerContext c;memset(&c,0xB7,sizeof(c));ExecutionState state;
    memset(&state,0xD3,sizeof(state));
    auto lookup=image.io();
    assert(prepare_repeat_call(c,image,values,state,command,mode,lookup));
    assert(c.prepared && !c.cache_target && !c.storage && c.execution.storage==&lookup && !c.execution.paged.read);
    assert(c.language==language && state.language==language && c.source_id==42 && !c.execution.edit_requested);
    assert(c.execution.mode==(command==C::TINYBASIC_RUN_ID_STATUS?mode:0));
    assert(values.selected[language==Language::BASIC?0:1]==42);
    View v;assert(execution_compatible(&c.vm.program) && validated_view(c.vm.program,v));
    active=&c;live_cache=&cache;changed=false;
    uint32_t result=99;
    const auto status=app_flow::run(mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_VM,MK61_APP_FLOW_SYSTEM_FILE,FLOW_RUN_PROGRAM),
        &c,sizeof(c),result,invoke);
    active=nullptr;
    if(fail_execute || fail_finish || fail_input)assert(status==MK61_FLOW_CORRUPT);
    else assert(status==MK61_FLOW_OK);
    return result;
  }
};
void reset() {cancel_input=stop=fail_execute=fail_finish=fail_input=mutate=false;events.clear();}
void no_fill_on_miss() {
  Fixture f(Language::BASIC,"10 END\n");uint8_t out[WRITE_BYTES];memset(page,0x71,sizeof(page));
  f.cache.put(1,999,0,page);const auto before=f.cache.statistics();
  {RepeatImage miss(f.cache,1,42,123,Language::BASIC);assert(!miss);}
  assert(f.cache.get(1,999,0,out) && !memcmp(out,page,sizeof(page)));
  assert(f.cache.statistics().publications==before.publications && f.cache.statistics().evictions==before.evictions);
  assert(f.cache.statistics().loan_misses==before.loan_misses);
  f.warm();
  {RepeatImage wrong(f.cache,1,42,124,Language::BASIC);assert(!wrong);}
  {RepeatImage wrong(f.cache,1,42,123,Language::FOCAL);assert(!wrong);}
  {RepeatImage wrong(f.cache,1,43,123,Language::BASIC);assert(!wrong);}
  {RepeatImage pinned(f.cache,1,42,123,Language::BASIC);assert(pinned);
    RepeatImage busy(f.cache,1,42,123,Language::BASIC);assert(!busy);}
  {RepeatImage good(f.cache,1,42,123,Language::BASIC);assert(good);}
  {RepeatImage stale(f.cache,2,42,123,Language::BASIC);assert(!stale);}
  {RepeatImage stale(f.cache,1,42,123,Language::BASIC);assert(!stale);}
  for(uint32_t size:{0U,8193U,UINT32_MAX}) {
    auto c=f.validated;c.size=size;
    f.cache.remember_image(3,{123,456,0,42,2,3,4,0,c});
    RepeatImage large(f.cache,3,42,123,Language::BASIC);assert(!large);
  }
}
void ordinary_calls() {
  reset();Fixture basic(Language::BASIC,"10 A=A+1;@(2)=A/10;.RA=A;END\n");basic.warm();
  auto other=basic.values.variables[1][0];
  for(unsigned i=1;i<=20;++i) {
    assert(basic.run_call(Language::BASIC,C::TINYBASIC_RUN_ID_STATUS,1)==1);
    assert(basic.values.variables[0][0].number()==i && external==i);
    assert(basic.values.array[2].number()==double(i)/10);
    assert(!memcmp(&other,&basic.values.variables[1][0],sizeof(other)));
  }
  assert(finishes==0);
  assert(basic.run_call(Language::BASIC,C::TINYBASIC_RUN_ID)==1 && finishes==1);
  reset();Fixture focal(Language::FOCAL,"1.1 S A=A+1;S B=A/10;S .RA=A;E\n");focal.warm();
  for(unsigned i=1;i<=20;++i) {
    assert(focal.run_call(Language::FOCAL,C::FOCAL_RUN_ID)==0);
    assert(focal.values.variables[1][0].number()==i && external==i);
  }
  assert(finishes==21);
}
void certificate_rejections() {
  Fixture f(Language::BASIC,"10 END\n");f.warm();
  RepeatImage image(f.cache,1,42,123,Language::BASIC);assert(image);
  CompilerContext c{};ExecutionState state;auto lookup=image.io();
  assert(prepare_repeat_call(c,image,f.values,state,C::TINYBASIC_RUN_ID_STATUS,1,lookup));
  for(unsigned fault=0;fault<10;++fault) {
    auto bad=f.validated;
    switch(fault) {
      case 0:bad.magic=0;break;
      case 1:--bad.size;break;
      case 2:++bad.code;break;
      case 3:bad.end=bad.size+1;break;
      case 4:bad.source_size=0;break;
      case 5:bad.stack=0;break;
      case 6:bad.flags=16;break;
      case 7:bad.lines=0;break;
      case 8:bad.language=Language::FOCAL;break;
      case 9:bad.wide=false;break;
    }
    c.prepared=false;
    assert(!prepare_cached_execution(c,bad,state,C::TINYBASIC_RUN_ID_STATUS));
    assert(!c.prepared);
  }
  assert(prepare_cached_execution(c,f.validated,state,C::TINYBASIC_RUN_ID_STATUS));
}
void input_and_failures() {
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    reset();Fixture f(language,language==Language::BASIC?"10 A=10;INPUT B;A=A+B;END\n":"1.1 S A=10;A B;S A=A+B;E\n");f.warm();
    const auto command=language==Language::BASIC?C::TINYBASIC_RUN_ID_STATUS:C::FOCAL_RUN_ID;
    assert(f.run_call(language,command,1)==(language==Language::BASIC?1U:0U));
    assert(f.values.variables[language==Language::BASIC?0:1][0].number()==13);
    cancel_input=true;const auto cancelled=f.run_call(language,command,1);
    assert(cancelled==(language==Language::BASIC?2U:1U));cancel_input=false;
    assert(f.run_call(language,command,1)==(language==Language::BASIC?1U:0U));
    fail_input=true;(void)f.run_call(language,command,1);fail_input=false;
    fail_execute=true;(void)f.run_call(language,command,1);fail_execute=false;
  }
  reset();Fixture f(Language::BASIC,"10 A=A+1;END\n");f.warm();
  fail_finish=true;(void)f.run_call(Language::BASIC,C::TINYBASIC_RUN_ID);fail_finish=false;
  mutate=true;assert(f.run_call(Language::BASIC,C::TINYBASIC_RUN_ID_STATUS,1)==1 && changed);
  RepeatImage stale(f.cache,2,42,123,Language::BASIC);assert(!stale);
}
void control_and_errors() {
  reset();Fixture basic(Language::BASIC,"10 L=30;GOTO L\n20 A=99;END\n30 A=7;GOSUB 50;END\n50 A=A+2;RETURN\n");basic.warm();
  assert(basic.run_call(Language::BASIC,C::TINYBASIC_RUN_ID_STATUS,1)==1);
  assert(basic.values.variables[0][0].number()==9);
  reset();Fixture focal(Language::FOCAL,"1.1 S A=3;G 2.1\n1.2 S A=99;E\n2.1 S A=A+2;E\n");focal.warm();
  assert(focal.run_call(Language::FOCAL,C::FOCAL_RUN_ID)==0 && focal.values.variables[1][0].number()==5);
  reset();Fixture failed(Language::BASIC,"10 A=1/0;END\n");failed.warm();
  assert(failed.run_call(Language::BASIC,C::TINYBASIC_RUN_ID_STATUS,1)==4);
  reset();Fixture interrupted(Language::BASIC,"10 A=A+1;GOTO 10\n");interrupted.warm();stop=true;
  assert(interrupted.run_call(Language::BASIC,C::TINYBASIC_RUN_ID_STATUS,1)==2);
  reset();assert(interrupted.values.variables[0][0].number()==0);
}
}
int main() {
  no_fill_on_miss();ordinary_calls();certificate_rejections();input_and_failures();control_and_errors();
  printf("Prepared repeat calls: BASIC/FOCAL, numeric banks, fresh state, INPUT/resume/cancel, failures, immutable epoch loans PASS; starts=%u executions=%u inputs=%u polls=%u\n",starts,executions,inputs,polls);
}
