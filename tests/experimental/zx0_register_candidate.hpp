#ifndef MK61_ZX0_REGISTER_CANDIDATE_HPP
#define MK61_ZX0_REGISTER_CANDIDATE_HPP
#include "zx0_candidates.hpp"
namespace zx0_register_candidate {
// A by-value pointer keeps decode's current cursor in a register. Passing a
// reference to the larger out-of-line copy forces even literal writes to
// reload/store that cursor on the stack under GCC -Os.
static __attribute__((noinline)) u8* expand(u8* output,u32 offset,u32 length) {
  const u8* source=output-offset;
  if(length>=4&&offset!=0&&offset<4) {
    u32 pattern;
    if(offset==1)pattern=(u32)source[0]*0x01010101U;
    else if(offset==2) {
      pattern=*(const zx0_candidates::Half*)source;pattern|=pattern<<16;
    } else pattern=(u32)source[0]|((u32)source[1]<<8)|((u32)source[2]<<16)|((u32)source[0]<<24);
    do {
      zx0_candidates::store(output,pattern);output+=4;length-=4;
      if(offset==3)pattern=(pattern>>8)|((pattern&0xFF00U)<<16);
    } while(length>=4);
    source=output-offset;
  } else while(length>=4) {
    const u32 word=zx0_candidates::load(source);zx0_candidates::store(output,word);
    output+=4;source+=4;length-=4;
  }
  while(length--!=0)*output++=*source++;
  return output;
}
static inline __attribute__((always_inline)) bool copy_match(u8*& output,
    const u8* begin,const u8* end,u32 offset,u32 length) {
  if(offset>(u32)(output-begin)||length>(u32)(end-output))return false;
  // Measured four/seven-byte word copies do not consistently pay for setup.
  if(length<8) {
    const u8* source=output-offset;
    while(length--!=0)*output++=*source++;
    return true;
  }
  output=expand(output,offset,length);return true;
}
}
#endif
