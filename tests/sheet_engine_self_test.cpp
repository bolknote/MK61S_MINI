#include "sheet_engine.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace sheet;
namespace {
unsigned calls, yields;
bool allow_yield=true;
double math(void*,Op op,double x,double y) {
  ++calls;
  switch(op) {
    case Op::SIN:return std::sin(x); case Op::COS:return std::cos(x);
    case Op::TAN:return std::tan(x); case Op::ASIN:return std::asin(x);
    case Op::ACOS:return std::acos(x); case Op::ATAN:return std::atan(x);
    case Op::LN:return std::log(x); case Op::LG:return std::log10(x);
    case Op::EXP:return std::exp(x); case Op::SQRT:return std::sqrt(x);
    case Op::POW:return std::pow(x,y); case Op::TEN:return std::pow(10,x);
    default:assert(false); return 0;
  }
}
bool yield(void*) { ++yields; return allow_yield; }
Host host={nullptr,math,yield};
uint16_t pos(unsigned column,unsigned row) { return (uint16_t)((row-1)*COLUMNS+column); }
void put(Book& b,uint16_t p,const char* text,Kind kind=Kind::FORMULA) {
  assert(set(b,p,kind,text,(uint16_t)strlen(text))==Error::OK);
}
const Cell& cell(const Book& b,uint16_t p) { const int i=find(b,p); assert(i>=0); return b.cells[i]; }
double value(Book& b,uint16_t p) { assert(recalculate(b,host)); assert(cell(b,p).error==0); return cell(b,p).value; }
void close(double x,double y,double eps=1e-10) { assert(std::fabs(x-y)<eps); }
uint32_t crc(const uint8_t* data,size_t length) {
  uint32_t c=0xffffffffU;
  for(size_t i=0;i<length;++i) { if(i>=16 && i<20) continue; c^=data[i]; for(int n=0;n<8;++n)c=(c>>1)^((c&1)?0xedb88320U:0); }
  return ~c;
}
void fix_crc(std::vector<uint8_t>& bytes) { const uint32_t c=crc(bytes.data(),bytes.size()); for(int n=0;n<4;++n)bytes[16+n]=(uint8_t)(c>>(8*n)); }
}
int main() {
  Book b; clear(b);
  put(b,pos(0,2),"2",Kind::NUMBER); put(b,pos(1,2),"125",Kind::NUMBER);
  put(b,pos(2,2),"A2 ENT B2 *"); close(value(b,pos(2,2)),250);
  put(b,pos(3,2),"C2 ENT 2 /"); close(value(b,pos(3,2)),125);
  put(b,pos(4,2),"81 SQRT"); close(value(b,pos(4,2)),9);
  calls=0; put(b,pos(0,2),"3",Kind::NUMBER);
  assert(cell(b,pos(2,2)).dirty && cell(b,pos(3,2)).dirty && !cell(b,pos(4,2)).dirty);
  close(value(b,pos(3,2)),187.5); assert(calls==0); // Unrelated SQRT is cached.
  assert(set(b,pos(1,2),Kind::EMPTY,nullptr,0)==Error::OK);
  close(value(b,pos(2,2)),0); // Empty references recalculate to zero after deletion.
  put(b,pos(1,2),"caption",Kind::TEXT); assert(recalculate(b,host));
  assert(cell(b,pos(2,2)).error==(uint8_t)Error::TYPE);
  assert(cell(b,pos(3,2)).error==(uint8_t)Error::TYPE);

  clear(b); put(b,0,"B1"); put(b,1,"C1"); put(b,2,"B1"); put(b,3,"A1 ENT 1 +");
  put(b,4,"42",Kind::NUMBER); assert(recalculate(b,host));
  for(unsigned i=0;i<4;++i) assert(cell(b,i).error==(uint8_t)Error::CYCLE);
  close(cell(b,4).value,42);
  put(b,2,"5",Kind::NUMBER); close(value(b,3),6);
  put(b,4,"E1"); assert(recalculate(b,host)); assert(cell(b,4).error==(uint8_t)Error::CYCLE);

  clear(b);
  char target[8];
  for(unsigned i=0;i<MAX_CELLS;++i) {
    address((uint16_t)((i+1)%MAX_CELLS),0,target); put(b,(uint16_t)i,target);
  }
  assert(recalculate(b,host));
  for(unsigned i=0;i<MAX_CELLS;++i) assert(cell(b,(uint16_t)i).error==(uint8_t)Error::CYCLE);
  put(b,63,"1",Kind::NUMBER); close(value(b,0),1);
  assert(set(b,64,Kind::NUMBER,"2",1)==Error::LIMIT);

  clear(b); put(b,0,"90 SIN"); close(value(b,0),1);
  b.angle=(uint8_t)Angle::GRD; invalidate(b); put(b,0,"100 SIN"); close(value(b,0),1);
  b.angle=(uint8_t)Angle::RAD; invalidate(b); put(b,0,"PI ENT 2 / SIN"); close(value(b,0),1);
  double result=0;
  assert(evaluate(b,"5 ENT 2 -",9,host,result)==Error::OK); close(result,3);
  assert(evaluate(b,"5 ENT 0 /",9,host,result)==Error::NUMBER);
  assert(evaluate(b,"-1 SQRT",7,host,result)==Error::NUMBER);
  assert(evaluate(b,"0 LN",4,host,result)==Error::NUMBER);
  assert(evaluate(b,"1E99 ENT 1E99 *",15,host,result)==Error::OK);
  assert(evaluate(b,"1E308 ENT 1E308 *",17,host,result)==Error::NUMBER);
  assert(evaluate(b,"#REF",4,host,result)==Error::REFERENCE);
  for(const char* input:{"1E","1E+",".","1.2.3","NAN","INF","1E999999999999999999999"}) {
    double number_value; assert(!number(input,(uint16_t)strlen(input),number_value));
  }
  // A post-operation entry lifts, whereas ENTER suppresses that lift.
  assert(evaluate(b,"2 ENT 3 + 4 *",13,host,result)==Error::OK); close(result,20);
  assert(evaluate(b,"2 ENT 3 SWAP -",14,host,result)==Error::OK); close(result,1);
  // Verified against the actual MK-61 ROM: 2 ENTER 3 F XY gives ~9.
  assert(evaluate(b,"2 ENT 3 POW",11,host,result)==Error::OK); close(result,9);

  char translated[SOURCE_BYTES];
  const char* original="A2 ENT $B2 * ENT C$2 + ENT $D$2 +";
  assert(translate(original,(uint16_t)strlen(original),1,2,translated)==Error::OK);
  assert(strcmp(translated,"B4 ENT $B4 * ENT D$2 + ENT $D$2 +")==0);
  assert(translate("A1",2,-1,0,translated)==Error::OK && strcmp(translated,"#REF")==0);
  assert(validate(Kind::FORMULA,translated,4)==Error::OK);
  assert(translate("P32",3,1,1,translated)==Error::OK && strcmp(translated,"#REF")==0);

  clear(b); put(b,0,"12.5",Kind::NUMBER); put(b,1,"A1 ENT 2 *");
  put(b,2,"label",Kind::TEXT); b.compact=1; b.angle=(uint8_t)Angle::GRD;
  uint8_t bytes[FILE_BYTES]; const uint16_t size=encode(b,bytes,sizeof(bytes));
  assert(size && size<=FILE_BYTES); Book loaded; clear(loaded);
  assert(decode(loaded,bytes,size)); close(value(loaded,1),25);
  assert(loaded.compact==1 && loaded.angle==(uint8_t)Angle::GRD);
  char copy[SOURCE_BYTES]; assert(source(loaded,2,copy) && strcmp(copy,"label")==0);
  std::vector<uint8_t> original_bytes(bytes,bytes+size);
  for(unsigned byte=0;byte<size;++byte) {
    auto broken=original_bytes; broken[byte]^=1;
    const Book before=loaded;
    assert(!decode(loaded,broken.data(),(uint16_t)broken.size()));
    assert(memcmp(&loaded,&before,sizeof(Book))==0);
  }
  for(unsigned n=0;n<size;++n) assert(!decode(loaded,bytes,(uint16_t)n));
  auto duplicate=original_bytes;
  const size_t second=20+4+4; duplicate[second]=0; duplicate[second+1]=0; fix_crc(duplicate);
  assert(!decode(loaded,duplicate.data(),(uint16_t)duplicate.size()));
  auto malformed=original_bytes; malformed[22]=99; fix_crc(malformed);
  assert(!decode(loaded,malformed.data(),(uint16_t)malformed.size()));
  auto trailing=original_bytes; trailing.push_back(0); trailing[12]++; fix_crc(trailing);
  assert(!decode(loaded,trailing.data(),(uint16_t)trailing.size()));

  // Repeated replacements/deletions exercise pool compaction and cache indices.
  clear(b);
  for(unsigned n=0;n<1000;++n) {
    const uint16_t p=(uint16_t)(n%16);
    if(n%7==0) assert(set(b,p,Kind::EMPTY,nullptr,0)==Error::OK);
    else put(b,p,n%2?"1":"12345",Kind::NUMBER);
    assert(recalculate(b,host));
    for(unsigned i=0;i<b.count;++i) { assert(source(b,b.cells[i].position,copy)); assert(strcmp(copy,"1")==0 || strcmp(copy,"12345")==0); }
    const uint16_t encoded=encode(b,bytes,sizeof(bytes)); assert(encoded && decode(loaded,bytes,encoded));
  }
  invalidate(b); allow_yield=false; assert(!recalculate(b,host)); allow_yield=true;
  assert(recalculate(b,host));
  std::printf("SHEET engine: arithmetic, incremental recalculation, 64-cell cycles, copy anchors, atomic CRC loads and cancellation PASS (Book=%zu)\n",sizeof(Book));
}
