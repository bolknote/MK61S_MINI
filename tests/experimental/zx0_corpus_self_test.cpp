// Verify exactly the native fixtures and workspace choices before device I/O.
#include "zx0_prototypes.hpp"
#include "zx0_bench_fixture.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
struct Sink {std::vector<u8> bytes;unsigned capacity;};
static bool write(void* context,u8 value) {
  auto& sink=*(Sink*)context;if(sink.bytes.size()==sink.capacity)return false;
  sink.bytes.push_back(value);return true;
}
int main() {
  const zx0_prototypes::Encode encoders[]={zx0::encode,zx0_prototypes::encode_scalar,
    zx0_prototypes::encode_word,zx0_prototypes::encode_dsp};
  unsigned checks=0;
  for(const auto& c:bench_cases)if(c.family==4)for(unsigned align=0;align<4;++align) {
    std::vector<u8> input(c.size+8);u32 random=0xC061F411;
    for(unsigned i=0;i<c.size;++i) {
      random^=random<<13;random^=random>>17;random^=random<<5;
      input[align+i]=c.pattern==0?'X':c.pattern==1?(u8)('a'+i%2):c.pattern==2?(u8)('a'+i%3):
        c.pattern==3?(u8)random:c.pattern==4?source_fixture[i%sizeof(source_fixture)]:image_fixture[i%sizeof(image_fixture)];
    }
    const unsigned size=c.parameter?3*c.size+64:4*(c.size+1)+64;
    std::vector<u8> expected;
    for(unsigned variant=0;variant<4;++variant) {
      std::vector<u8> work(size+8,0xA7);Sink sink={{},576-align};zx0::EncodeResult result={};
      const zx0::Output output={&sink,write};
      assert(encoders[variant](input.data()+align,c.size,work.data()+align,size,output,result));
      assert(result.output_size==sink.bytes.size()&&result.mode==(c.parameter?zx0::EncodeMode::GREEDY:zx0::EncodeMode::BOUNDED_OPTIMAL));
      if(!variant)expected=sink.bytes;else assert(expected==sink.bytes);
      for(unsigned i=0;i<align;++i)assert(work[i]==0xA7);
      for(size_t i=align+size;i<work.size();++i)assert(work[i]==0xA7);
      ++checks;
    }
  }
  std::printf("Exact native codec corpus: %u encode/alignment/workspace checks PASS\n",checks);
}
