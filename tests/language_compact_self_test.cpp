#include "language_compact.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

using namespace language_vm;
static unsigned checked=0;
static Value reference(Op op,Value a,Value b) {
  switch(op) {
    case Op::ADD:return a+b;case Op::SUB:return a-b;case Op::MUL:return a*b;
    case Op::DIV:return a/b;case Op::FLOOR_DIV:return Value::floor_divide(a,b);
    case Op::MOD:return Value::modulo(a,b);
    case Op::EQ:return a==b;case Op::NE:return a!=b;
    case Op::LT:return a<b;case Op::LE:return a<=b;
    case Op::GT:return a>b;case Op::GE:return a>=b;
    case Op::AND:return a!=0 && b!=0;case Op::OR:return a!=0 || b!=0;
    case Op::XOR:return (a!=0)!=(b!=0);
    default:assert(false);return 0;
  }
}
static void pair(int32_t x,int32_t y) {
  for(unsigned n=0;n<sizeof(wire_widths);++n) {
    const auto op=Op(n);if(!compact::binary(op))continue;
    int32_t z;
    if(compact::integer(op,x,y,z)) {
      const auto expected=reference(op,Value(x),Value(y));
      const Value actual(z);
      assert(!memcmp(&expected,&actual,sizeof(actual)));
      ++checked;
    }
  }
}
static void arithmetic() {
  const int32_t boundaries[]={INT32_MIN,INT32_MIN+1,-65536,-129,-64,-1,0,1,63,128,65536,INT32_MAX-1,INT32_MAX};
  for(auto x:boundaries)for(auto y:boundaries)pair(x,y);
  uint32_t seed=0x4c425632;
  for(unsigned i=0;i<20000;++i) {
    seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;const int32_t x=int32_t(seed);
    seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;
    pair(x,i&1?int32_t(seed):int32_t(seed&127)-64);
  }
  int32_t z;
  assert(!compact::integer(Op::ADD,INT32_MAX,1,z));
  assert(!compact::integer(Op::SUB,INT32_MIN,1,z));
  assert(!compact::integer(Op::MUL,0,-1,z));
  assert(!compact::integer(Op::MUL,-1,0,z));
  assert(!compact::integer(Op::DIV,0,-1,z));
  assert(!compact::integer(Op::DIV,INT32_MIN,-1,z));
  assert(!compact::integer(Op::DIV,7,2,z));
  assert(!compact::integer(Op::MOD,1,0,z));
}
static void emit(compact::Tail& t,uint32_t pc,Op op,uint32_t payload=0) {
  t.begin(op,pc);
  for(unsigned i=1;i<wire_widths[unsigned(op)] && i<=4;++i)t.byte(pc+i,uint8_t(payload>>((i-1)*8)));
}
static void lowering() {
  compact::Tail t;compact::Rewrite r;
  emit(t,70000,Op::LOAD,1);emit(t,70002,Op::LOAD,2);
  assert(t.rewrite(Op::ADD,70004,r) && !r.folded && r.begin==70000 && r.left==1 && r.right==2);
  emit(t,70004,Op::MUL);emit(t,70005,Op::CONST_I8,5);
  assert(t.rewrite(Op::ADD,70007,r) && r.begin==70005 && r.left==compact::STACK && compact::literal(r.right)==5);
  assert(!t.rewrite(Op::ADD,70008,r)); // Nonadjacent bytes are never swallowed.
  assert(!t.rewrite(Op::POW,70007,r));
  emit(t,10,Op::CONST_I32,100000);emit(t,15,Op::CONST_I16,2345);
  assert(t.rewrite(Op::ADD,18,r) && r.folded && r.value==102345 && r.begin==10);
  emit(t,0,Op::CONST_0);emit(t,1,Op::CONST_I8,255);
  assert(!t.rewrite(Op::MUL,3,r) || !r.folded); // Preserve negative zero.
  t.barrier();assert(!t.rewrite(Op::ADD,3,r));
  for(int n=-64;n<=63;++n) {
    compact::Record rec{0,uint32_t(n),Op::CONST_I32};uint8_t encoded=0;
    assert(rec.operand(encoded) && compact::source(encoded) && compact::literal(encoded)==n);
  }
  for(int n:{-65,64,INT32_MIN,INT32_MAX}) {
    compact::Record rec{0,uint32_t(n),Op::CONST_I32};uint8_t encoded;
    assert(!rec.operand(encoded));
  }
  for(unsigned n=0;n<256;++n)assert(compact::source(uint8_t(n))==(n<26 || n>=128));
}
int main() {
  arithmetic();lowering();
  std::printf("compact operands: %u bit-exact numeric cases; folding/overflow/signed-zero, operand IDs, wide PCs and barriers PASS\n",checked);
}
