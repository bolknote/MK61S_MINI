// Execute the generated real owned images in the ordinary host VM, unchanged
// arithmetic/step limits. Used with both backends before the physical HIL.
#include "language_vm_abi.hpp"
#include <cassert>
#include <fstream>
#include <iterator>
#include <iostream>
#include <string>
#include <vector>
using namespace language_vm;
struct Context {std::string output;unsigned inputs=0,prints=0;};
static bool event(void* p,Event e,const char* text,uint16_t n,double& value) {
  auto& c=*(Context*)p;
  if(e==Event::TEXT)c.output.append(text,n);
  if(e==Event::PRINT_END)++c.prints;
  if(e==Event::READ_INPUT){value=7;++c.inputs;}
  assert(e!=Event::RESOURCE_TEXT && e!=Event::RESOURCE_INPUT);
  return true;
}
int main(int argc,char** argv) {
  if(argc!=4)return 2;
  std::ifstream file(argv[1],std::ios::binary);
  std::vector<uint8_t> bytes{std::istreambuf_iterator<char>(file),{}};
  View view;assert(inspect(bytes.data(),bytes.size(),view)==Error::NONE);
  Value variables[26]={},array[385]={},stack[MAX_STACK]={};Continuation control={};
  Context context;Bindings bindings={variables,array,385,stack,MAX_STACK};
  Services services={};services.context=&context;services.event=event;
  const auto result=run(view,control,bindings,services);
  if(result.error!=Error::NONE) {std::cerr<<error_name(result.error)<<'\n';return 1;}
  assert(variables[0].zero());
  assert(context.output==std::string(argv[2]) && context.prints==1);
  const bool input=std::string(argv[3])=="input";
  assert(context.inputs==(input?1U:0U));
  if(input)assert(variables[1].number()==7);
  std::cout<<argv[1]<<" execution exact PASS\n";
}
