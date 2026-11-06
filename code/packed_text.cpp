#include "packed_text.hpp"
#if MK61_PACKED_TEXT_ENABLED
namespace packed_text {
namespace {
#include "packed_text_data.inc"
unsigned read9(const uint8_t* data,unsigned index) {
  const unsigned bit=index*9,offset=bit/8;
  return ((unsigned(data[offset])|(unsigned(data[offset+1])<<8))>>(bit%8))&511;
}
}
unsigned Reader::symbol() {
  unsigned code=0,first=0,index=0;
  for(unsigned length=1;length<=MAX_CODE_BITS;++length) {
    code=(code<<1)|((MESSAGE_BITS[bit_/8]>>(7-bit_%8))&1);++bit_;
    const unsigned count=CODE_COUNTS[length];
    if(code-first<count)return read9(CODE_SYMBOLS,index+code-first);
    first=(first+count)<<1;index+=count;
  }
  return 0;
}
uint8_t Reader::next() {
  if(ended_)return 0;
  if(!packed_) {
    const uint8_t value=plain_?uint8_t(*plain_):0;
    if(value)++plain_;else ended_=true;
    return value;
  }
  unsigned token=pending_?stack_[--pending_]:symbol();
  while(token>=256) {
    const unsigned index=(token-256)*2;
    stack_[pending_++]=uint16_t(read9(PAIR_SYMBOLS,index+1));
    token=read9(PAIR_SYMBOLS,index);
  }
  if(!token)ended_=true;
  return uint8_t(token);
}
size_t copy(char* out,size_t capacity,Text text) {
  Reader reader(text);size_t n=0;
  for(uint8_t byte;(byte=reader.next())!=0;++n)if(n+1<capacity)out[n]=char(byte);
  if(capacity)out[n<capacity?n:capacity-1]=0;
  return n;
}
}
#endif
