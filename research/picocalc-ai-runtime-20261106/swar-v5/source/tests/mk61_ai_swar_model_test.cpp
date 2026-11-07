#include "mk61_ai_swar_fixture.hpp"
int main(int argc,char** argv) {
  assert(argc==3);unsigned comparisons=0;
  for(unsigned layout=1;layout<3;++layout) {
    std::ifstream file(argv[layout],std::ios::binary);
    const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
    Runtime control(bytes),candidate(bytes);control.configure(false);candidate.configure(true);
    std::uint16_t tokens[64];unsigned count=0;
    assert(control.model.encode("Задача: сложи R0 и R1, затем проверь результат.",tokens,64,count)==ModelStatus::OK && count>3);
    std::vector<float> a(control.model.config().vocab),b(a.size());
    std::uint16_t left=0,right=0;
    for(auto kernel : {LinearKernel::FLASH,LinearKernel::SRAM}) {
      auto e=control.model.execution();e.kernel=kernel;control.model.execution(e);
      e=candidate.model.execution();e.kernel=kernel;candidate.model.execution(e);
      control.model.reset();candidate.model.reset();
      for(unsigned p=0;p<16;++p) {
        bool output=p<2 || p==15;
        assert(control.forward(tokens[p%count],Arithmetic::INT8,left,output?a.data():nullptr,output)==ModelStatus::OK);
        assert(candidate.forward(tokens[p%count],Arithmetic::SWAR_INT8,right,output?b.data():nullptr,output)==ModelStatus::OK);
        assert(control.model.compute_metrics().checksum==candidate.model.compute_metrics().checksum && control.cache==candidate.cache);
        if(output) { assert(left==right && !std::memcmp(a.data(),b.data(),a.size()*sizeof(float)));++comparisons; }
      }
    }
  }
  std::printf("SWAR model PASS: %u exact full-logit comparisons vs INT8; both Q4 layouts, FLASH/SRAM,2cores,prefetch,16-position KV exact.\n",comparisons);
}
