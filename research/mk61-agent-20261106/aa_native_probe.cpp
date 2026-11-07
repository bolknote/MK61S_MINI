#include "aa_native.hpp"
namespace { mk61action::Decoder decoder; }
extern "C" {
void aa_reset() { decoder=mk61action::Decoder{}; }
int aa_allows(unsigned short token,const char *piece) { return decoder.allows(token,piece); }
int aa_accept(unsigned short token,const char *piece) { return decoder.accept(token,piece); }
int aa_complete() { return decoder.complete(); }
int aa_action() { return int(decoder.action); }
unsigned aa_body(unsigned char *out) {
  for(unsigned i=0;i<decoder.size;++i)out[i]=decoder.body[i];
  return decoder.size;
}
unsigned aa_state_bytes() { return sizeof(decoder); }
}
