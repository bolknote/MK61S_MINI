#ifndef MK61_LANGUAGE_COMPACT_HPP
#define MK61_LANGUAGE_COMPACT_HPP
#include "language_bytecode.hpp"
#ifndef MK61_VM_COMPACT_OPERANDS
#define MK61_VM_COMPACT_OPERANDS 1
#endif

namespace language_vm { namespace compact {
// Operand IDs name existing locals or signed seven-bit integer literals. Only
// the left operand may name the previous expression result on the VM stack.
constexpr uint8_t STACK = 127;
constexpr bool source(uint8_t id) {return id<26 || id>=128;}
constexpr int32_t literal(uint8_t id) {return int32_t(id&127)-((id&64)?128:0);}
constexpr bool binary(Op op) {
  return (op>=Op::ADD && op<=Op::XOR && op!=Op::POW) || op==Op::FLOOR_DIV;
}
inline bool integer(Op op,int32_t x,int32_t y,int32_t& z) {
  switch(op) {
    case Op::ADD:return !__builtin_add_overflow(x,y,&z);
    case Op::SUB:return !__builtin_sub_overflow(x,y,&z);
    case Op::MUL:
      return !((!x && y<0) || (!y && x<0)) && !__builtin_mul_overflow(x,y,&z);
    case Op::DIV:
      if(!y || (x==INT32_MIN && y==-1) || (!x && y<0) || x%y)return false;
      z=x/y;return true;
    case Op::FLOOR_DIV:
      if(!y || (x==INT32_MIN && y==-1))return false;
      z=x/y;if(x%y && ((x<0)!=(y<0)))--z;return true;
    case Op::MOD:
      if(!y)return false;
      if(x==INT32_MIN && y==-1)z=0;
      else {z=x%y;if(z && ((z<0)!=(y<0)))z+=y;}
      return true;
    case Op::EQ:z=x==y;return true;case Op::NE:z=x!=y;return true;
    case Op::LT:z=x<y;return true;case Op::LE:z=x<=y;return true;
    case Op::GT:z=x>y;return true;case Op::GE:z=x>=y;return true;
    case Op::AND:z=x && y;return true;case Op::OR:z=x || y;return true;
    case Op::XOR:z=(x!=0)!=(y!=0);return true;
    default:return false;
  }
}

struct Record {
  uint32_t pc=0;
  uint32_t arguments=0;
  Op op=Op::HALT;
  uint8_t width() const {
    return uint8_t(op)<sizeof(wire_widths)?wire_widths[uint8_t(op)]:0;
  }

  __attribute__((noinline)) bool constant(int32_t& value) const {
    if(op>=Op::CONST_0 && op<=Op::CONST_15)value=int32_t(unsigned(op)-unsigned(Op::CONST_0));
    else if(op==Op::CONST_I8)value=int8_t(arguments);
    else if(op==Op::CONST_I16)value=int16_t(arguments);
    else if(op==Op::CONST_I32)value=int32_t(uint32_t(arguments));
    else return false;
    return true;
  }
  bool operand(uint8_t& id) const {
    if(op==Op::LOAD && arguments<26) {id=uint8_t(arguments);return true;}
    int32_t value;
    if(!constant(value) || value < -64 || value>63)return false;
    id=uint8_t(128|(uint32_t(value)&127));return true;
  }
};
struct Rewrite {
  uint32_t begin;
  uint8_t left,right;
  bool folded;
  int32_t value;
};
// A bounded emission analysis shared by both language grammars. No AST,
// heap, source-sized array, runtime cache or program-specific rule is used.
template<bool Third> struct Earlier {};
template<> struct Earlier<true> {Record earlier{};};
template<bool Third=false> struct History : Earlier<Third> {
  Record before{},last{};
  void barrier() {if constexpr(Third)this->earlier.op=Op::HALT;before.op=Op::HALT;last.op=Op::HALT;}
  void begin(Op op,uint32_t pc) {if constexpr(Third)this->earlier=before;before=last;last={pc,0,op};}
  void byte(uint32_t pc,uint8_t value) {
    const uint32_t n=pc-last.pc;
    if(n>=1 && n<=4)last.arguments|=uint32_t(value)<<((n-1)*8);
  }
  __attribute__((noinline)) bool rewrite(Op op,uint32_t pc,Rewrite& r) const {
    if((op>=Op::EQ && op<=Op::GE) || op==Op::FLOOR_DIV || !binary(op) || !last.width() || last.pc+last.width()!=pc)return false;
    const bool adjacent=before.width() && before.pc+before.width()==last.pc;
    int32_t x,y,z;
    // Keep cold compiler folding small; all other operators still use direct
    // operands and the complete guarded integer kernel during execution.
    if(op>=Op::ADD && op<=Op::MUL && adjacent && before.constant(x) && last.constant(y) && integer(op,x,y,z)) {
      r={before.pc,0,0,true,z};return true;
    }
    uint8_t right,left=STACK;
    if(!last.operand(right))return false;
    const bool pair=adjacent && before.operand(left);
    r={pair?before.pc:last.pc,pair?left:STACK,right,false,0};return true;
  }
};
using Tail=History<>;
}}
#endif
