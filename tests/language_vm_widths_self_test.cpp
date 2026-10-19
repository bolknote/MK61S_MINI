#include "language_bytecode.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace language_vm;
static uint32_t expected(const View& v,uint32_t pc,uint8_t op,uint32_t count) {
  if(pc>=v.end || op>=sizeof(wire_widths))return 0;
  unsigned width=wire_widths[op];
  if(v.wide_code())switch(Op(op)) {
    case Op::JUMP:case Op::JUMP_FALSE:case Op::GOTO_DIRECT:case Op::GOSUB_DIRECT:
    case Op::GRAPH_BEGIN:case Op::GRAPH_NEXT:width=5;break;
    case Op::COMPARE_FALSE:width=6;break;
    case Op::DO_FOCAL:width=9;break;
    case Op::BRANCH:width=13;break;
    case Op::CALL_PARAMS:width=11;break;
    case Op::FOR_FOCAL:width=7;break;
    default:break;
  }
  const uint32_t remaining=v.end-pc;
  if(width!=255)return width && width<=remaining?pc+width:0;
  const unsigned prefix=v.wide && Op(op)==Op::DATA?5:3;
  if(remaining<prefix)return 0;
  if(prefix==3)count&=65535;
  if(Op(op)==Op::ON_GOTO || Op(op)==Op::ON_GOSUB)
    return count && count<=(remaining-3)/2?pc+3+count*2:0;
  if(Op(op)==Op::DATA && !count)return 0;
  return count<=remaining-prefix?pc+prefix+count:0;
}
int main() {
  uint8_t bytes[80]={};unsigned cases=0;
  for(bool wide:{false,true})for(unsigned op=0;op<256;++op)
    for(unsigned remaining=0;remaining<=20;++remaining)
      for(uint32_t count:{0U,1U,2U,31U,65535U,UINT32_MAX}) {
        const uint32_t pc=32;
        bytes[pc]=uint8_t(op);flash::dword(bytes+pc+1,count);
        View v={bytes,sizeof(bytes),pc,0,1,1,Language::BASIC,false,false,
                pc+remaining,nullptr,wide};
        assert(instruction_end(v,pc)==expected(v,pc,uint8_t(op),count));
        ++cases;
      }
  std::printf("Instruction widths: %u narrow/wide opcode/count/truncation cases PASS\n",cases);
}
