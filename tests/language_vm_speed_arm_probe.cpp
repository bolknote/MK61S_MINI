#include "language_bytecode.hpp"
using namespace language_vm;
extern "C" void _exit(int) {__builtin_trap();}
extern "C" int _kill(int,int) {return -1;}
extern "C" int _getpid() {return 1;}
extern "C" __attribute__((noinline)) unsigned bench(const uint8_t* image,unsigned length,double* output) {
  View view;
  if(inspect(image,(uint16_t)length,view)!=Error::NONE) return 255;
  Value variables[26]={},array[385]={},stack[MAX_STACK]={};
  State state={};state.variables=variables;state.array=array;state.array_count=385;
  state.stack=stack;state.stack_capacity=MAX_STACK;
  const auto result=run(view,state,{},1000000);
  *output=variables[0].number();return (unsigned)result.error;
}
