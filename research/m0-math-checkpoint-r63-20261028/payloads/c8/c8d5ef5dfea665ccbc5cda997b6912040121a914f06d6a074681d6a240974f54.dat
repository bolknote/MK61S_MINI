#ifndef MK61_LANGUAGE_INTEGER_SPANS_HPP
#define MK61_LANGUAGE_INTEGER_SPANS_HPP
#include "language_bytecode.hpp"
namespace language_vm { namespace detail {
// One identical marking pass for RAM compatibility images and paged LBV2.
// Marks retain widths, labels, diagnostics and scalar fallback semantics.
template<class Read,class Next,class Mark>
void integer_spans(uint32_t code,uint32_t end,Read read,Next next,Mark mark) {
  uint32_t first=0;unsigned count=0;
  auto finish=[&]() {if(first && count>=5)mark(first,Op::INTEGER_SPAN);first=0;count=0;};
  auto skip=[&](uint32_t at) {while(at<end && end-at>=3 && Op(read(at))==Op::SOURCE_POS)at+=3;return at;};
  for(uint32_t pc=code;pc<end;) {
    const Op op=Op(read(pc));const uint32_t after=next(pc);if(!after)break;
    if(op==Op::SOURCE_POS){pc=after;continue;}
    if(op==Op::BLOCK_INDEX){finish();pc+=6;continue;}
    if(op==Op::LOAD) {
      const uint32_t middle=skip(after);
      if(middle<end && (Op(read(middle))==Op::LOAD_ARRAY ||
          (end-middle>=2 && Op(read(middle))==Op::FUNCTION && Function(read(middle+1))==Function::ABS))) {
        const uint32_t last=skip(middle+(Op(read(middle))==Op::LOAD_ARRAY?1:2));
        if(last<end && end-last>=2 && Op(read(last))==Op::STORE) {
          finish();mark(pc,Op::INTEGER_SHORT);pc=last+2;continue;
        }
      }
    }
    const bool supported=op==Op::LOAD || op==Op::LOAD_ARRAY_FIXED || op==Op::LOAD_ARRAY || op==Op::STORE ||
        op==Op::STORE_ARRAY || op==Op::CONST_I8 || op==Op::CONST_I16 || op==Op::CONST_I32 ||
        (op>=Op::CONST_0 && op<=Op::CONST_15) || op==Op::NEG || op==Op::NOT ||
        (op>=Op::ADD && op<=Op::XOR && op!=Op::POW) || op==Op::FLOOR_DIV;
    if(!supported)finish();else {if(!first && op==Op::LOAD)first=pc;if(first)++count;}
    pc=after;
  }
  finish();
}
}}
#endif
