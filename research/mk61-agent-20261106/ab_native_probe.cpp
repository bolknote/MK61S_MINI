#include "ab_native.hpp"
namespace { mk61action::Decoder decoder; }
extern "C" {
void ab_reset() { decoder=mk61action::Decoder{}; }
int ab_allows(unsigned short token,const char *piece) { return decoder.allows(token,piece); }
int ab_accept(unsigned short token,const char *piece) { return decoder.accept(token,piece); }
int ab_complete() { return decoder.complete(); }
int ab_action() { return int(decoder.action); }
unsigned ab_body(unsigned char *out) {
  for(unsigned i=0;i<decoder.size;++i)out[i]=decoder.body[i];
  return decoder.size;
}
unsigned ab_state_bytes() { return sizeof(decoder); }
}
