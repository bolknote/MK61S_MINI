#include "language_bytecode.hpp"
#include "language_vm_abi.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <string>
using namespace language_vm;
struct Program {
  uint8_t image[MAX_IMAGE]; View view={}; State state={};
  Value variables[26], array[385], stack[MAX_STACK];
  unsigned inputs=0;
  static bool event(void* raw,Event e,const char*,uint16_t,double& value) {
    if(e==Event::READ_INPUT){++((Program*)raw)->inputs;value=7;}
    return true;
  }
  static double math(void*,Function,double a,double b){return mk_math::pow(a,b);}
  explicit Program(const char* source,Language language=Language::BASIC){
    auto r=compile(language,source,(uint16_t)strlen(source),image,sizeof(image));
    if(r.error!=Error::NONE)std::fprintf(stderr,"compile %s at %u: %s\n",error_name(r.error),r.source_offset,source);
    assert(r.error==Error::NONE && inspect(image,r.size,view)==Error::NONE);
    state.variables=variables;state.array=array;state.array_count=385;
    state.stack=stack;state.stack_capacity=MAX_STACK;
  }
  RunResult run(bool yield=false,bool resume=false){Services s={this,nullptr,math,nullptr,nullptr,nullptr,event,yield};return language_vm::run(view,state,s,100000,resume);}
  void expected(char name,double expected,bool integer){Value v=variables[name-'A'];assert(v.number()==expected && v.integer()==integer);}
};
int main(){
  {
    Program p("10 A=INT(-7/2);B=-7 MOD 3;C=7 MOD -3\n20 D=2147483647+1;E=1/2\n30 F=9007199254740992+1-9007199254740992\n");
    assert(p.run().error==Error::NONE);p.expected('A',-4,true);p.expected('B',2,true);p.expected('C',-2,true);
    p.expected('D',2147483648.,false);p.expected('E',.5,false);p.expected('F',0,true);
  }
  {
    Program p("10 A=281474976710655;B=INT(A/536870912);C=A MOD 65536\n20 D=INT(7/2+.9);E=INT(INT(7/2)/2)\n");
    assert(p.run().error==Error::NONE);p.expected('A',281474976710655.,false);p.expected('B',524287,true);p.expected('C',65535,true);p.expected('D',4,true);p.expected('E',1,true);
  }
  for(Language l:{Language::BASIC,Language::FOCAL}){
    Program p(l==Language::BASIC?"10 S=0;FOR I=1 TO 9;S=S+I;NEXT I\n20 A=INT(-7/2)\n":"1.10 S S=0\n1.20 F I=1,9;S S=S+I\n1.30 S A=INT(-7/2)\n",l);
    assert(p.run().error==Error::NONE);p.expected('S',45,true);p.expected('A',-4,true);
  }
  {
    Program p("10 A=0;B=-A;C=B*2;D=C/2\n");assert(p.run().error==Error::NONE);
    for(char n:{'B','C','D'}){Value v=p.variables[n-'A'];assert(!v.integer() && mk_math::binary64_bits(v.number())==UINT64_C(0x8000000000000000));}
  }
  {
    Program p("10 FOR I=1 TO 2;INPUT @(I);NEXT I\n20 A=@(1)+@(2)\n");
    auto r=p.run(true);assert(r.error==Error::YIELDED && p.variables['I'-'A'].integer());
    p.stack[p.state.sp++]=Value(7);r=p.run(true,true);assert(r.error==Error::YIELDED && p.array[1].integer());
    p.stack[p.state.sp++]=Value(9);r=p.run(true,true);assert(r.error==Error::NONE);p.expected('A',16,true);
  }
  {
    Program p("10 DATA 2147483647,.5,281474976710655\n20 READ A;READ B;READ C\n");
    assert(p.run().error==Error::NONE);p.expected('A',2147483647,true);p.expected('B',.5,false);p.expected('C',281474976710655.,false);
  }
  for(const char* source:{"10 A=1/0\n","10 A=INT(1/0)\n","10 A=1 MOD 0\n"}){
    Program p(source);const auto r=p.run();assert(r.error==Error::DIV_ZERO && r.line==10);
    const char* operation=strchr(source,'/');if(!operation) operation=strstr(source,"MOD");
    assert(source_column(p.view,r.pc)==(unsigned)(operation-source)+1);
  }
  {
    Program p("1.10 S A=INT(1/0)\n",Language::FOCAL);
    const auto r=p.run();assert(r.error==Error::MATH && r.line==1010);
  }
  {
    Request request={};request.size=sizeof(request);request.capacity=MAX_IMAGE;
    request.version=3;assert(!compatible(&request));
    request.version=REQUEST_VERSION;assert(compatible(&request));
  }
  std::puts("integer VM: automatic types, int32 overflow, fractional division, FLOOR_DIV, MOD, wide history, signed zero, FOR/INPUT/DATA PASS");
}
