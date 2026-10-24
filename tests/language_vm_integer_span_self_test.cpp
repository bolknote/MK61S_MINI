#include "language_bytecode.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>
using namespace language_vm;
namespace language_vm { RunResult reference_run(const View&,State&,const Services&,uint32_t,bool); }
namespace {
struct Snapshot {
  std::vector<uint64_t> trace,events,polls,results,cells,control;
  std::string text;
  bool operator==(const Snapshot& b)const {
    return trace==b.trace && events==b.events && polls==b.polls && results==b.results &&
        cells==b.cells && control==b.control && text==b.text;
  }
};
Snapshot* recording;
const View* executing_view;
unsigned comparisons=0,spans=0,multiple=0,short_blocks=0;
bool aliased_code_fixture=false;
struct Fixture {
  uint8_t image[MAX_IMAGE]; View view={};
  Value variables[26],array[385],stack[MAX_STACK]; State state={};
  Snapshot result;
  unsigned stop=0,polls=0;
  static bool service(void* context) {
    auto& f=*static_cast<Fixture*>(context);++f.polls;
    // Service callbacks must see committed control and all the old dead cells.
    uint64_t hash=UINT64_C(14695981039346656037);
    auto add=[&](uint64_t n){for(unsigned i=0;i<8;++i){hash^=(uint8_t)n;hash*=UINT64_C(1099511628211);n>>=8;}};
    for(auto& v:f.variables)add(v.representation());
    for(auto& v:f.array)add(v.representation());
    for(auto& v:f.stack)add(v.representation());
    f.result.polls.insert(f.result.polls.end(),{f.state.pc,f.state.sp,f.state.call_count,f.state.loop_count,hash});
    return !f.stop || f.polls<f.stop;
  }
  static bool event(void* context,Event kind,const char* text,uint16_t length,double& value) {
    auto& f=*static_cast<Fixture*>(context);
    f.result.events.insert(f.result.events.end(),{(uint64_t)kind,length,mk_math::binary64_bits(value)});
    if(text)f.result.text.append(text,length);
    return true;
  }
  static double math(void*,Function f,double a,double b) {
    return (unsigned)f==255?std::pow(a,b):f==Function::SQRT?std::sqrt(a):0;
  }
  Fixture(const char* source,Language language,Value x,Value y) {
    const auto c=compile(language,source,(uint16_t)strlen(source),image,sizeof(image));
    if(c.error!=Error::NONE)std::fprintf(stderr,"compile %u line %u: %s\n",(unsigned)c.error,c.line,source);
    assert(c.error==Error::NONE && inspect(image,c.size,view)==Error::NONE);
    for(unsigned n=0;n<26;++n)variables[n]=Value((int32_t)n-10);
    variables['I'-'A']=x;variables['J'-'A']=y;
    for(unsigned n=0;n<385;++n)array[n]=(n%11)?Value((int32_t)n-100):Value(.25);
    for(unsigned n=0;n<MAX_STACK;++n)stack[n]=Value((int32_t)n+123);
    state.variables=variables;state.array=array;state.array_count=385;
    state.stack=stack;state.stack_capacity=MAX_STACK;
  }
  Snapshot execute(bool reference,unsigned limit,bool resume=false) {
    recording=&result;executing_view=&view;
    Services host={};host.context=this;host.service=service;host.event=event;host.math=math;host.yield_input=true;
    for(unsigned phase=0;;++phase) {
      assert(phase<5);
      const auto r=reference?reference_run(view,state,host,limit,resume):run(view,state,host,limit,resume);
      result.results.insert(result.results.end(),{(uint64_t)r.error,r.pc,r.line,r.steps,source_column(view,r.pc)});
      if(r.error!=Error::YIELDED)break;
      assert(state.sp<MAX_STACK);stack[state.sp++]=Value(7.5);resume=true;
    }
    recording=nullptr;executing_view=nullptr;
    for(const auto& v:variables)result.cells.push_back(v.representation());
    for(const auto& v:array)result.cells.push_back(v.representation());
    for(const auto& v:stack)result.cells.push_back(v.representation());
    result.control={state.pc,state.sp,state.data_pc,state.data_index,state.call_count,state.loop_count};
    for(unsigned n=0;n<state.call_count;++n) {
      const auto& f=state.calls[n];result.control.insert(result.control.end(),
        {f.resume,f.end,f.loops,f.group,f.base,f.mode,f.print_width,f.arguments});
    }
    for(unsigned n=0;n<state.loop_count;++n) {
      const auto& f=state.loops[n];result.control.insert(result.control.end(),
        {f.body,f.end,f.variable,f.step.representation(),f.limit.representation(),f.value.representation()});
    }
    return result;
  }
  unsigned marks()const {
    unsigned n=0;for(uint16_t pc=view.code;pc<view.end;pc=instruction_end(image,view.end,pc))
      n+=(Op)image[pc]==Op::INTEGER_SPAN || (Op)image[pc]==Op::INTEGER_SHORT;
    return n;
  }
};
void equal(Fixture& a,Fixture& b,unsigned limit,bool resume=false) {
  const auto fast=a.execute(false,limit,resume),reference=b.execute(true,limit,resume);
  if(!(fast==reference)) {
    std::fprintf(stderr,"integer span mismatch case=%u limit=%u stop=%u resume=%u\n",comparisons,limit,a.stop,resume);
    std::fprintf(stderr,"trace=%d events=%d polls=%d results=%d cells=%d control=%d\n",fast.trace==reference.trace,
      fast.events==reference.events,fast.polls==reference.polls,fast.results==reference.results,
      fast.cells==reference.cells,fast.control==reference.control);
    assert(false);
  }
  ++comparisons;
}
void short_code_alias(const char* source,Language language,Value value,unsigned offset,unsigned limit,unsigned stop=0) {
  Fixture fast(source,language,value,5),reference(source,language,value,5);
  Value first[MAX_IMAGE/sizeof(Value)]={},second[MAX_IMAGE/sizeof(Value)]={};
  Value* images[]={first,second};Fixture* fixtures[]={&fast,&reference};
  for(unsigned which=0;which<2;++which) {
    auto& f=*fixtures[which];auto* cells=images[which];
    std::memcpy(cells,f.image,f.view.size);
    assert(inspect(reinterpret_cast<const uint8_t*>(cells),(uint16_t)f.view.size,f.view)==Error::NONE);
    f.state.stack=cells+f.view.code/sizeof(Value)+offset;f.state.stack_capacity=32;f.stop=stop;
  }
  aliased_code_fixture=true;equal(fast,reference,limit);aliased_code_fixture=false;
  assert(!std::memcmp(first,second,sizeof(first)));
}
}
namespace language_vm {
void trace_instruction(const View& v,uint16_t pc,uint32_t steps) {
  if(recording)recording->trace.insert(recording->trace.end(),{pc,steps,(uint64_t)scalar_op((Op)v.byte(pc))});
}
void integer_span_applied(uint16_t first,uint8_t count) {
  ++spans;multiple+=count>1;
  assert(executing_view);
  // The hook runs after the span: a code/value alias can have overwritten
  // its original marker already. The reference and full bytes are compared.
  if(!aliased_code_fixture)
    assert((Op)executing_view->bytes[first]==Op::INTEGER_SPAN ||
           (Op)executing_view->bytes[first]==Op::INTEGER_SHORT);
}
void integer_short_block_applied(uint16_t) {++short_blocks;}
}
int main() {
  // Original case297/limit3: LOAD writes the first inactive stack cell over
  // SOURCE_POS/ABS/STORE. Prefetching the whole short block changes subsequent
  // scalar fetches. The image is valid before RUN; this alias is not rejected.
  short_code_alias("10 A=ABS(I)\n",Language::BASIC,-3,1,3);
  for(Language language:{Language::BASIC,Language::FOCAL})for(bool array:{false,true}) {
    if(array && language==Language::FOCAL)continue;
    const char* source=array?"10 A=@(I)\n":language==Language::BASIC?"10 A=ABS(I)\n":"1.1 S A=ABS(I)\n";
    for(Value value:{Value(-3),Value(3),Value(.5),Value::floating_bits(UINT64_C(0x8000000000000000))})
      for(unsigned offset:{0U,1U,2U,3U,4U})for(unsigned limit:{0U,1U,2U,3U,4U,31U,32U,33U})
        for(unsigned stop:{0U,1U,2U})short_code_alias(source,language,value,offset,limit,stop);
    // Ordinary immutable code still takes the existing short fast path.
    Fixture fast(source,language,3,5),reference(source,language,3,5);
    const unsigned before=multiple;equal(fast,reference,0);assert(multiple==before+1);
    // A reader ignores View::bytes. An overlapping, unused pointer must not
    // disable the short path when the actual callback supplies immutable code.
    Fixture paged(source,language,3,5),paged_reference(source,language,3,5);
    auto read=[](void* raw,uint32_t at,uint8_t* out,uint16_t n) {
      std::memcpy(out,static_cast<const uint8_t*>(raw)+at,n);return true;
    };
    flash::Reader reader({paged.image,read,paged.view.size});
    flash::Reader reference_reader({paged_reference.image,read,paged_reference.view.size});
    paged.view.reader=&reader;paged_reference.view.reader=&reference_reader;
    paged.view.bytes=reinterpret_cast<const uint8_t*>(paged.stack);
    paged_reference.view.bytes=reinterpret_cast<const uint8_t*>(paged_reference.stack);
    const unsigned before_reader=multiple;aliased_code_fixture=true;
    equal(paged,paged_reference,0);aliased_code_fixture=false;
    assert(multiple==before_reader+1);
  }
  // Half-open bounds: a full writable cell ending at image[0], or starting
  // exactly at image[end], is adjacent, not aliased. Keep the fast path.
  for(bool before:{false,true}) {
    Fixture fast("10 A=ABS(I)\n",Language::BASIC,-3,5),reference("10 A=ABS(I)\n",Language::BASIC,-3,5);
    Value first[MAX_IMAGE/sizeof(Value)]={},second[MAX_IMAGE/sizeof(Value)]={};
    Value* banks[]={first,second};Fixture* fixtures[]={&fast,&reference};
    for(unsigned which=0;which<2;++which) {
      auto& f=*fixtures[which];auto* cells=banks[which];
      const unsigned offset=before?sizeof(Value):(sizeof(Value)-f.view.end%sizeof(Value))%sizeof(Value);
      auto* image=reinterpret_cast<uint8_t*>(cells)+offset;
      std::memcpy(image,f.image,f.view.size);assert(inspect(image,(uint16_t)f.view.size,f.view)==Error::NONE);
      f.state.stack=before?cells:cells+(offset+f.view.end)/sizeof(Value);f.state.stack_capacity=32;
    }
    const unsigned initial=multiple;aliased_code_fixture=true;equal(fast,reference,0);aliased_code_fixture=false;
    assert(multiple==initial+1 && !std::memcmp(first,second,sizeof(first)));
  }
  const char* basic[]={
    "10 A=(I+3)*(J-2);B=I*J+I-J\n20 END\n",
    "10 A=I/J+I MOD J;B=INT(I/J)+J\n",
    "10 A=I*J+I/J-I MOD J;B=I+1\n",
    "10 A=-(I+J)*I+NOT J;B=I<J\n",
    "10 A=(I<J)+(I<=J)+(I>J)+(I>=J)+(I=J)+(I#J)\n",
    "10 A=(I AND J)+(I OR J)+(I XOR J)\n",
    "10 A=@(I)+@(J)*I-J\n",
    "10 @(I)=I*J+I-J;A=@(I)\n",
    "10 A=I+32767+32768+2147483647+2147483648\n",
    "10 FOR K=1 TO 7;A=(I+3)*(J-2);B=@(K)+I*J;NEXT K\n",
    "10 GOSUB 100;END\n100 A=(I+3)*(J-2);RETURN\n",
    "10 INPUT A\n20 A=(I+3)*(J-2)+A;B=I*J+I-J\n",
    "10 IF I<J A=(I+3)*(J-2) ELSE A=I*J+I-J\n",
    "10 DATA 1,-2,105\n20 READ A,B,C;A=(I+3)*(J-2)+A\n",
    "10 PRINT \"I LIKE SPANS\";I*J+I-J\n",
    "10 A=128+I;B=@(128+I);C=(I+3)*(J-2)\n",
    "10 A=I^J+I*J-I\n",
    "10 A=ABS(I);B=ABS(J)\n",
    "10 A=@(I);B=ABS(A);C=@(J)\n",
    "10 A=ABS(ABS(I));B=ABS(I+J);C=ABS(I*J)\n",
    "10 A=@(I);B=ABS(A)*J;@(I)=ABS(B)\n",
    "10 A=ABS(I);B=SQRT(J);C=ABS(B)\n"
  };
  const Value values[]={Value(INT32_MIN),Value(INT32_MIN+1),Value(-129),Value(-1),Value(0),Value(1),
    Value(15),Value(16),Value(384),Value(385),Value(INT32_MAX),Value(.5),Value(2147483648.),
    Value::floating_bits(UINT64_C(0x8000000000000000)),Value(std::numeric_limits<double>::infinity()),
    Value(-std::numeric_limits<double>::infinity()),Value(std::numeric_limits<double>::quiet_NaN())};
  unsigned marked=0;
  // Every power-of-two magnitude, its neighbours and both divisor signs.
  // Compare the full Value bank with the scalar oracle: negative quotients
  // round down, MOD follows the divisor, and zero/overflow still fall back.
  for(unsigned bit=0;bit<32;++bit)for(int sign:{-1,1})for(int delta:{-1,0,1}) {
    const int64_t candidate=int64_t(sign)*(INT64_C(1)<<bit)+delta;
    if(candidate<INT32_MIN || candidate>INT32_MAX)continue;
    const Value y=Value(int32_t(candidate));
    for(int32_t x:{INT32_MIN,INT32_MIN+1,-65537,-257,-129,-3,-1,0,1,3,127,255,65537,INT32_MAX})
      for(const char* source:{"10 A=I MOD J;B=INT(I/J);C=A+B\n",
                             "1.10 S A=INT(I/J);S B=INT((I-1)/J);S C=A+B\n"})
        for(unsigned limit:{0U,2U,5U,31U,32U,33U}) {
          const auto language=source[1]=='.'?Language::FOCAL:Language::BASIC;
          Fixture fast(source,language,Value(x),y),reference(source,language,Value(x),y);
          equal(fast,reference,limit);
        }
  }
  for(const char* source:basic)for(Value x:values)for(Value y:{Value(-1),Value(0),Value(3),Value(.5),Value(INT32_MAX)})
    for(unsigned limit:{0U,1U,2U,3U,4U,5U,7U,15U,30U,31U,32U,33U,34U,65U})for(unsigned stop:{0U,1U,2U}) {
      Fixture fast(source,Language::BASIC,x,y),reference(source,Language::BASIC,x,y);
      marked+=fast.marks();fast.stop=reference.stop=stop;equal(fast,reference,limit);
    }
  for(const char* source:{"1.10 S A=(I+3)*(J-2)\n","1.10 F K=1,9;S A=(I+3)*(J-2)\n",
      "1.10 D 2,3;EXIT\n2.10 S A=(I+3)*(J-2);RETURN ARG(1)\n",
      "1.10 S A=(I+3)*(J-2);S B=ABS(I);S C=ABS(ABS(J))\n"})
    for(Value x:values)for(Value y:{Value(0),Value(3),Value(.5)})for(unsigned limit:{0U,1U,2U,5U,31U,32U,33U,65U}) {
      Fixture fast(source,Language::FOCAL,x,y),reference(source,Language::FOCAL,x,y);
      assert(fast.marks());equal(fast,reference,limit);
    }
  // Every original instruction remains a legal resume point. Include nearly
  // full stacks and call endings inside the expression, not just its labels.
  for(unsigned program:{0U,2U,6U,7U,15U,17U,18U,19U,20U,21U}) {
    Fixture full(basic[program],Language::BASIC,3,5);
    for(uint16_t pc=full.view.code;pc<full.view.end;pc=instruction_end(full.image,full.view.end,pc))
      for(unsigned sp:{0U,1U,2U,94U,95U,96U})for(unsigned limit:{0U,1U,2U,5U,31U,32U,33U})for(bool call:{false,true}) {
        Fixture fast(basic[program],Language::BASIC,3,5),reference(basic[program],Language::BASIC,3,5);
        for(Fixture* f:{&fast,&reference}) {
          f->state.pc=pc;f->state.data_pc=f->view.code;f->state.sp=(uint8_t)sp;
          if(call){f->state.call_count=1;f->state.calls[0]={f->view.code,(uint16_t)(pc+1),0,false,0,0,0,0};}
        }
        equal(fast,reference,limit?limit:128,true);
      }
    for(uint16_t end=full.view.code;end<=full.view.end;++end)for(unsigned limit:{1U,2U,5U,31U,32U,33U}) {
      Fixture fast(basic[program],Language::BASIC,3,5),reference(basic[program],Language::BASIC,3,5);
      fast.view.end=reference.view.end=end;equal(fast,reference,limit);
    }
  }
  // Full signed range plus ordinary small arithmetic; compare the actual
  // old path, including promotion, quotient/remainder signs and dead cells.
  uint32_t seed=0x61F411U;
  auto random=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
  for(unsigned n=0;n<20000;++n) {
    int32_t x=mk_math::bit_copy<int32_t>(random()),y=mk_math::bit_copy<int32_t>(random());
    if(n&1){x%=32768;y%=32768;}
    for(unsigned family=0;family<2;++family) {
      const char* source=basic[family?17+n%5:n%3];
      Fixture fast(source,Language::BASIC,Value(x),Value(y)),reference(source,Language::BASIC,Value(x),Value(y));
      fast.stop=reference.stop=n%7==0?2:0;
      equal(fast,reference,n%4==0?0:30+n%4);
    }
  }
  // Public bindings do not promise that the value banks are disjoint.
  for(unsigned program:{7U,20U})for(unsigned alias=0;alias<3;++alias)for(int x:{0,3})
      for(unsigned limit:{0U,1U,5U,31U,32U,33U}) {
    Fixture fast(basic[program],Language::BASIC,x,5),reference(basic[program],Language::BASIC,x,5);
    for(Fixture* f:{&fast,&reference}) {
      if(alias==0)f->state.variables=f->stack;
      if(alias==1){f->state.array=f->stack;f->state.array_count=MAX_STACK;}
      if(alias==2){f->state.variables=f->array;}
    }
    equal(fast,reference,limit);
  }
  // Raw code may share storage with a value bank. A span must consume the
  // current operands before its first write; later fetches see the same
  // modified bytes as the ordinary evaluator.
  static_assert(std::is_trivially_copyable<Value>::value,"value representation fixture");
  for(unsigned program:{0U,7U})for(unsigned bank=0;bank<3;++bank)
      for(unsigned shift:{0U,8U,16U})for(unsigned limit:{1U,2U,5U,31U,32U,33U,128U}) {
    Fixture fast(basic[program],Language::BASIC,3,5),reference(basic[program],Language::BASIC,3,5);
    Value first[MAX_IMAGE/sizeof(Value)],second[MAX_IMAGE/sizeof(Value)];
    Value* images[]={first,second};Fixture* fixtures[]={&fast,&reference};
    for(unsigned which=0;which<2;++which) {
      auto& f=*fixtures[which];auto* cells=images[which];
      std::memcpy(cells,f.image,f.view.size);f.view.bytes=reinterpret_cast<const uint8_t*>(cells);
      cells+=(f.view.code+7U+shift)/8U;
      if(bank==0){f.state.stack=cells;f.state.stack_capacity=32;}
      if(bank==1)f.state.variables=cells;
      if(bank==2){f.state.array=cells;f.state.array_count=32;}
    }
    aliased_code_fixture=true;equal(fast,reference,limit);aliased_code_fixture=false;
    assert(!std::memcmp(first,second,sizeof(first)));
  }
  // The existing hint retains every instruction width and scalar fallback.
  // Changed compiler APP CRC automatically invalidates its old file cache.
  Fixture short_chain(basic[17],Language::BASIC,-17,3);
  assert(short_chain.marks()==2);
  for(Value cell:{Value(.25),Value::floating_bits(UINT64_C(0x8000000000000000)),
      Value::floating_bits(UINT64_C(0x3FF0000000000000)),
      Value(std::numeric_limits<double>::infinity()),
      Value(-std::numeric_limits<double>::infinity()),
      Value(std::numeric_limits<double>::quiet_NaN())})
      for(unsigned limit:{0U,1U,2U,3U,4U,31U,32U,33U})for(unsigned stop:{0U,1U,2U}) {
    Fixture fast(basic[18],Language::BASIC,3,5),reference(basic[18],Language::BASIC,3,5);
    fast.array[3]=reference.array[3]=cell;fast.stop=reference.stop=stop;
    equal(fast,reference,limit);
  }
  // Near-integral floating indices retain the scalar tolerance and error PC.
  for(double index:{3+1e-8,3-1e-8,-1e-8,384-1e-8})
      for(unsigned limit:{0U,1U,2U,3U,4U,31U,32U,33U}) {
    Fixture fast(basic[18],Language::BASIC,index,5),reference(basic[18],Language::BASIC,index,5);
    equal(fast,reference,limit);
  }
  // A short mark is only a hint. A valid but nonmatching middle instruction
  // must execute through ordinary LOAD/function/STORE, not the fast shape.
  for(Function function:{Function::INT,Function::SGN,Function::SQRT})
      for(Value x:{Value(0),Value(-17),Value(INT32_MIN),Value(.5)})
      for(unsigned limit:{0U,1U,2U,3U,31U,32U,33U}) {
    Fixture fast(basic[17],Language::BASIC,x,3),reference(basic[17],Language::BASIC,x,3);
    for(Fixture* f:{&fast,&reference}) {
      uint16_t at=f->view.code;
      while((Op)f->image[at]!=Op::INTEGER_SHORT)at=instruction_end(f->image,f->view.end,at);
      at=(uint16_t)(at+2);
      while((Op)f->image[at]==Op::SOURCE_POS)at=(uint16_t)(at+3);
      assert((Op)f->image[at]==Op::FUNCTION);f->image[at+1]=(uint8_t)function;
      const uint32_t crc=checksum(f->image+HEADER_SIZE,f->view.size-HEADER_SIZE);
      for(unsigned byte=0;byte<4;++byte)f->image[20+byte]=(uint8_t)(crc>>(byte*8));
      assert(inspect(f->image,f->view.size,f->view)==Error::NONE);
    }
    equal(fast,reference,limit);
  }
  // Multi-byte span operations must reject every truncated operand before
  // reading it, then retain the scalar error PC/steps and all dead cells.
  for(Op op:{Op::CONST_I8,Op::CONST_I16,Op::CONST_I32,Op::LOAD,
             Op::INTEGER_SPAN,Op::LOAD_ARRAY_FIXED,Op::STORE})
      for(unsigned available=1;available<=wire_widths[(unsigned)op];++available)
      for(unsigned limit:{0U,1U,2U,3U,31U,32U,33U}) {
    Fixture fast(basic[0],Language::BASIC,3,5),reference(basic[0],Language::BASIC,3,5);
    for(Fixture* f:{&fast,&reference}) {
      uint16_t at=f->view.code;
      while((Op)f->image[at]!=Op::INTEGER_SPAN)at=instruction_end(f->image,f->view.end,at);
      at=(uint16_t)(at+2);f->image[at]=(uint8_t)op;
      std::memset(f->image+at+1,0,wire_widths[(unsigned)op]-1);
      f->view.end=(uint16_t)(at+available);
    }
    equal(fast,reference,limit);
  }
  // Unassigned opcode bytes, including zero-width table holes, must not be
  // consumed as one-byte span instructions or spin inside its local loop.
  for(unsigned op=0;op<256;++op) {
    if(op<sizeof(wire_widths) && wire_widths[op])continue;
    for(unsigned limit:{0U,1U,2U,31U,32U,33U}) {
      Fixture fast(basic[0],Language::BASIC,3,5),reference(basic[0],Language::BASIC,3,5);
      for(Fixture* f:{&fast,&reference}) {
        uint16_t at=f->view.code;
        while((Op)f->image[at]!=Op::INTEGER_SPAN)at=instruction_end(f->image,f->view.end,at);
        at=(uint16_t)(at+2);f->image[at]=(uint8_t)op;f->view.end=(uint16_t)(at+1);
      }
      equal(fast,reference,limit);
    }
  }
  // A caller may supply only one actual stack cell. Pointer guards must not
  // form a pointer two cells past its beginning, even on an underflow path.
  for(unsigned limit:{0U,1U,2U,3U,31U,32U,33U}) {
    Fixture fast(basic[0],Language::BASIC,3,5),reference(basic[0],Language::BASIC,3,5);
    Value a[1]={Value(123)},b[1]={Value(123)};
    fast.view.stack=reference.view.stack=1;
    fast.state.stack=a;reference.state.stack=b;
    fast.state.stack_capacity=reference.state.stack_capacity=1;
    equal(fast,reference,limit);assert(a[0].representation()==b[0].representation());
  }
  // Inactive cells and aliased variable/array banks may contain fractions,
  // signed zero or NaNs. All overlapping/dead cells and load fallbacks must
  // remain bit-exact, even around the original 32-step service boundary.
  for(unsigned program:{0U,6U,7U,20U,21U})for(unsigned offset:{0U,1U,4U})
    for(unsigned bank=0;bank<3;++bank)
      for(Value poison:{Value(0),Value(.25),Value::floating_bits(UINT64_C(0x8000000000000000)),
                        Value::floating_bits(UINT64_C(0x7FF8000000000000))})
        for(unsigned limit:{0U,2U,31U,32U,33U,65U}) {
          Fixture fast(basic[program],Language::BASIC,3,5),reference(basic[program],Language::BASIC,3,5);
          for(Fixture* f:{&fast,&reference}) {
            for(auto& cell:f->stack)cell=poison;
            f->stack[offset+2]=Value(3);
            if(bank!=1)f->state.variables=f->stack+offset;
            if(bank!=0){f->state.array=f->stack+offset;f->state.array_count=MAX_STACK-offset;}
          }
          equal(fast,reference,limit);
        }
  assert(marked>1000 && spans>1000 && multiple>1000 && short_blocks>1000);
  std::printf("integer spans: %u exact reference comparisons; %u spans, %u multi-op, %u short blocks; trace/steps/dead cells/polls/errors/INPUT/ESC/resume PASS\n",comparisons,spans,multiple,short_blocks);
}
