#include "zx0_candidates.hpp"
#ifdef ZX0_PRODUCTION_ENCODER
#include "zx0_encode_kernels.hpp"
#endif
#ifdef ZX0_REGISTER_COPY
#include "zx0_register_candidate.hpp"
#endif
struct Job {
  u32 family,variant;u8* input;u32 size,position,offset;u8* output;
  u32 result,near_length,far_length;
};
extern "C" __attribute__((noipa)) bool zx0_probe(Job* j) {
  namespace k=zx0_candidates;
  if(j->family==0) {
    u8* p=j->input+j->position;
    const bool ok=j->variant?
#ifdef ZX0_REGISTER_COPY
      zx0_register_candidate::copy_match(p,j->input,j->input+j->size,j->offset,j->size-j->position):
#else
      k::copy_word(p,j->input,j->input+j->size,j->offset,j->size-j->position):
#endif
      k::copy_scalar(p,j->input,j->input+j->size,j->offset,j->size-j->position);
    j->result=(u32)(p-j->input);return ok;
  }
  if(j->family==1) {
    j->result=j->variant?
#ifdef ZX0_PRODUCTION_ENCODER
      zx0_encode_kernels::match_length(j->input,(u16)j->size,(u16)j->position,(u16)j->offset):
#else
      k::match_word(j->input,(u16)j->size,(u16)j->position,(u16)j->offset):
#endif
      k::match_scalar(j->input,(u16)j->size,(u16)j->position,(u16)j->offset);
    return true;
  }
  if(j->family==2) {
    u16 a,b;
    if(j->variant==0)k::lcp_scalar(j->input,(u16)j->position,(u16*)j->output,a,b);
    else if(j->variant==1)k::lcp_blocks<false>(j->input,(u16)j->position,(u16*)j->output,a,b);
    else
#ifdef ZX0_PRODUCTION_ENCODER
      zx0_encode_kernels::lcp_blocks(j->input,(u16)j->position,(u16*)j->output,a,b);
#else
      k::lcp_blocks<true>(j->input,(u16)j->position,(u16*)j->output,a,b);
#endif
    j->near_length=a;j->far_length=b;return true;
  }
#ifdef ZX0_PRODUCTION_ENCODER
  j->result=zx0_encode_kernels::equal_byte_mask(j->offset);return true;
#else
  j->result=k::equal_byte_mask<true>(j->offset);return true;
#endif
}
