#include "language_vm_flow.hpp"
#include "language_linked_cache.hpp"
#include "language_flash_fixture.hpp"
#include "loadable_module_abi.hpp"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

using namespace language_vm;
namespace {
void focal_jumps() {
  const struct {const char* text;int a,c;} cases[]={
    {"1.10 D 2.20;S A=7;EXIT\n2.10 S C=5;EXIT\n2.20 S B=1;G 2.10\n",7,0},
    {"1.10 D 2;S A=99;EXIT\n2.10 S B=1;G 3.10\n3.10 S A=5;EXIT\n",5,0},
    {"1.10 S A=3+CALL(2,7);EXIT\n2.10 S B=1;G 2.30\n2.20 R 99\n2.30 R ARG(1)*2\n",17,0},
    {"1.10 S A=CALL(2);EXIT\n2.10 D 3\n2.20 R 99\n2.30 R 7\n3.10 S B=1;G 2.30\n",7,0}
  };
  for(const auto& test:cases)for(bool paged:{false,true}) {
    uint8_t image[MAX_IMAGE];Disk disk;
    source::Reader source(test.text,uint16_t(strlen(test.text)));
    const auto compiled=paged?compile_flash_source(Language::FOCAL,source,disk.io()):
      compile(Language::FOCAL,test.text,uint16_t(strlen(test.text)),image,sizeof(image));
    assert(compiled.error==Error::NONE);
    flash::Reader reader({&disk,[](void* raw,uint32_t at,uint8_t* out,uint16_t n) {
      return Disk::read(raw,IMAGE,at,out,n);
    },compiled.size});
    View view;
    assert((paged?inspect_flash(reader,disk.io(),view):inspect(image,compiled.size,view))==Error::NONE);
    Value variables[26]{},array[64]{},stack[MAX_STACK]{};
    State state{};state.variables=variables;state.array=array;state.array_count=64;
    state.stack=stack;state.stack_capacity=MAX_STACK;
    const auto result=run(view,state,{},1000);
    assert(result.error==Error::NONE && variables[0]==test.a && variables[2]==test.c);
    assert(state.call_count==0 && state.loop_count==0);
  }
}

void folded_maps() {
  for(auto language:{Language::BASIC,Language::FOCAL})for(unsigned constant:{128U,32768U,2147483647U}) {
    const bool basic=language==Language::BASIC;
    const std::string text=std::string(basic?"10 A=1;B=":"1.10 S A=1;S B=")+
      std::to_string(constant)+"-"+std::to_string(constant-1)+"\n";
    uint8_t image[MAX_IMAGE];
    const auto compiled=compile(language,text.c_str(),uint16_t(text.size()),image,sizeof(image));
    assert(compiled.error==Error::NONE);
    std::vector<uint8_t> exact(compiled.size+16,0xA5);
    const auto bounded=compile(language,text.c_str(),uint16_t(text.size()),exact.data()+8,uint16_t(compiled.size));
    assert(bounded.error==Error::NONE && bounded.size==compiled.size);
    assert(!memcmp(image,exact.data()+8,compiled.size));
    for(unsigned i=0;i<8;++i)assert(exact[i]==0xA5 && exact[compiled.size+8+i]==0xA5);
    View raw;assert(inspect(image,compiled.size,raw)==Error::NONE);
    Disk disk;source::Reader source(text.c_str(),uint16_t(text.size()));
    const auto paged=compile_flash_source(language,source,disk.io());
    assert(paged.error==Error::NONE && paged.size==compiled.size);
    std::vector<uint8_t> stored(paged.size);
    assert(Disk::read(&disk,IMAGE,0,stored.data(),uint16_t(stored.size())));
    assert(!memcmp(image,stored.data(),stored.size()));
    bool second=false;
    for(uint32_t pc=raw.code;pc<raw.end;pc=instruction_end(raw,pc)) {
      assert(instruction_end(raw,pc)>pc);
      if(source_column(raw,pc)==(basic?8:12))second=true;
    }
    assert(second);
    Value variables[26]{},stack[MAX_STACK]{};State state{};
    state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
    assert(run(raw,state,{}).error==Error::NONE && variables[0]==1 && variables[1]==1);
  }
}

unsigned prompts;
bool retry_expression;
uint32_t prompt(InputRequest* input) {
  ++prompts;
  // Sixteen simultaneously live operands would not fit the former borrowed
  // tail even at fifteen calls (60 arguments), before reaching the old sp64 cut.
  std::string expression="1";
  for(unsigned i=1;i<16;++i)expression="1+("+expression+")";
  if(retry_expression && prompts==1)expression="1/0";
  const auto result=compile_expression(Language::BASIC,expression.c_str(),uint16_t(expression.size()),
                                       input->image,input->capacity);
  assert(result.error==Error::NONE);
  input->image_size=uint16_t(result.size);input->result=InputResult::EXPRESSION;
  return 1;
}
uint32_t finish(OverlayRequest*) {return 1;}
void live_input() {
  for(unsigned levels:{15U,16U})for(bool indexed:{false,true})for(bool retry:{false,true}) {
    std::string text="10 GOSUB 100,1,2,3,4;END\n";
    for(unsigned n=1;n<levels;++n)text+=std::to_string(100*n)+" GOSUB "+
      std::to_string(100*(n+1))+",1,2,3,4;C=C+ARG(1)+ARG(2)+ARG(3)+ARG(4);RETURN\n";
    text+=std::to_string(100*levels)+(indexed?" INPUT @(2)":" INPUT N")+
      ";C=ARG(1)+ARG(2)+ARG(3)+ARG(4);RETURN\n";
    uint8_t image[MAX_MODULE];
    const auto compiled=compile_basic(text.c_str(),uint16_t(text.size()),image,sizeof(image),true);
    assert(compiled.error==Error::NONE && compiled.stack==MAX_STACK);
    Value variables[26]{},array[385]{};ExecutionState state{};state.language=Language::BASIC;
    ExecuteRequest execution{};execution.size=sizeof(execution);execution.version=REQUEST_VERSION;
    execution.image=image;execution.image_size=compiled.size;execution.variables=variables;
    execution.array=array;execution.array_count=385;execution.mode=1;
    FlowContext context;
    memset(&context,0xA5,sizeof(context));reset_flow_context(context);
    for(auto byte:context.input_storage)assert(byte==0xA5); // no extra clearing on RUN
    context.magic=FLOW_CONTEXT_MAGIC;
    context.original_command=uint32_t(loadable_module::Command::TINYBASIC_RUN_ID_STATUS);
    context.program={sizeof(OverlayRequest),REQUEST_VERSION,&execution,&state,&context.program_validated,
                       OverlayAction::START,{0,0,0}};
    assert(validate_execution(&context.program) && execution.result.error==Error::NONE);
    View view;assert(validated_view(context.program,view));
    Bindings bindings{variables,array,385,state.stack,MAX_STACK};Services services{};services.yield_input=true;
    execution.result=run(view,state.control,bindings,services);
    assert(execution.result.error==Error::YIELDED && state.control.sp==levels*4+unsigned(indexed));
    assert(state.control.call_count==levels);
    state.prompt_offset=execution.result.pc+3;
    state.prompt_length=flash::word(image+execution.result.pc+1);
    const Continuation saved_control=state.control;
    Value saved_stack[MAX_STACK];memcpy(saved_stack,state.stack,sizeof(saved_stack));
    mk61_app_flow flow{};flow.size=sizeof(flow);flow.version=MK61_APP_FLOW_VERSION;
    flow.context=&context;flow.context_size=sizeof(context);flow.current.phase=FLOW_EDIT_INPUT;
    prompts=0;retry_expression=retry;
    for(unsigned attempt=0;attempt<(retry?2U:1U);++attempt) {
      assert(flow_input(&flow,validate_execution,prompt,finish)==1);
      assert(flow.action==MK61_FLOW_CALL && context.input.image==context.input_storage);
      assert(context.input.invalid==(attempt!=0));
      View expression;assert(validated_view(context.expression_request,expression));
      const Bindings expression_bindings={variables,array,385,
        input_workspace(context.input.image).stack,INPUT_STACK_CAPACITY};
      context.expression.result=evaluate_input(expression,state,expression_bindings,{});
      assert(context.expression.result.error==(retry && !attempt?Error::DIV_ZERO:Error::NONE));
      assert(!memcmp(&saved_control,&state.control,sizeof(saved_control)));
      assert(!memcmp(saved_stack,state.stack,sizeof(saved_stack)));
      flow.current.phase=FLOW_AFTER_EXPRESSION;flow.status=MK61_FLOW_OK;flow.result=1;
    }
    assert(flow_input(&flow,validate_execution,prompt,finish)==1);
    assert(flow.action==MK61_FLOW_RETURN && flow.status==MK61_FLOW_OK && state.input_value==16);
    state.stack[state.control.sp++]=state.input_value;
    const auto result=run(view,state.control,bindings,services,0,true);
    assert(result.error==Error::NONE && variables[2]==int32_t(10*levels));
    assert((indexed?array[2]:variables['N'-'A'])==16);
    assert(!state.control.call_count && !state.control.sp);
  }
}

struct CachedImage {
  std::vector<uint8_t> bytes;
  unsigned reads=0;
  static bool read(void* raw,flash::Space space,uint32_t at,uint8_t* out,uint16_t n) {
    auto& source=*static_cast<CachedImage*>(raw);assert(space==flash::IMAGE);
    ++source.reads;assert(at+n<=source.bytes.size());memcpy(out,source.bytes.data()+at,n);return true;
  }
  explicit CachedImage(const char* source) : bytes(flash::WRITE_BYTES,0) {
    const auto compiled=compile_basic(source,uint16_t(strlen(source)),bytes.data(),uint16_t(bytes.size()),true);
    assert(compiled.error==Error::NONE);
  }
};
void linked_identity() {
  flash::PageCache<24*1024> cache;
  static_assert(sizeof(cache)<=24*1024,"unchanged cache budget");
  CachedImage first("10 A=1;END\n"),second("10 A=2;END\n");
  linked::Member member{};member.source_id=100;member.offset=73;
  member.validated.size=flash::dword(first.bytes.data()+8);
  assert(member.validated.size==flash::dword(second.bytes.data()+8));
  const uint8_t* image=nullptr;
  auto execute=[&](CachedImage& source,uint32_t epoch,uint16_t file,uint32_t offset,int expected) {
    member.offset=offset;flash::IO io{};io.context=&source;io.read=CachedImage::read;
    assert(linked::borrow_image(cache,epoch,file,member,io,image) && image);
    View view;assert(inspect(image,member.validated.size,view)==Error::NONE);
    Value variables[26]{},stack[MAX_STACK]{};State state{};
    state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
    assert(run(view,state,{}).error==Error::NONE && variables[0]==expected);
    cache.release(image);
  };
  execute(first,1,10,73,1);
  execute(second,1,11,73,2);assert(second.reads==1); // same local label/size/epoch, another container
  execute(second,1,11,73,2);assert(second.reads==1); // repeat retains the useful warm loan
  execute(first,1,11,74,1); // same container/local label, another unaligned member
  execute(second,1,11,73,2);assert(second.reads==1);
  execute(first,2,11,73,1); // inode reused or modified in a new media epoch
  const unsigned reads=first.reads;
  member.offset=0x10000000U;flash::IO io{};io.context=&first;io.read=CachedImage::read;
  assert(!linked::borrow_image(cache,2,11,member,io,image) && !image && first.reads==reads);
}
}
int main() {
  focal_jumps();folded_maps();live_input();linked_identity();
  std::puts("VM review regressions: FOCAL DO/CALL jumps raw/paged, folded source maps, live INPUT arguments/retry, linked container/member/epoch identity PASS");
}
