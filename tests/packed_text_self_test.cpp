#include "../code/packed_text.hpp"
#include "../code/mk61_io.hpp"
#include "../code/mk8_codec.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

class Output:public mk61_io::Output<Output> {
public:
  std::string data;
  size_t limit=10000;
  size_t write(uint8_t byte) {
    if(data.size()==limit)return 0;
    data.push_back(char(byte));return 1;
  }
  using mk61_io::Output<Output>::write;
};
int main() {
  using namespace packed_text;
  for(const auto& literal:LITERALS) {
    std::string expected=literal.text;
    if(literal.m8) {
      std::vector<u8> encoded(expected.size()+1);usize length=0;
      assert(mk8::from_utf8((const u8*)expected.data(),expected.size(),encoded.data(),encoded.size(),length));
      expected.assign((const char*)encoded.data(),length);
    }
    const Text text=Text::encoded(literal.offset);
    Reader reader(text);
    for(unsigned char byte:expected)assert(reader.next()==byte);
    assert(reader.next()==0&&reader.next()==0);
    for(size_t capacity=0;capacity<=expected.size()+2;++capacity) {
      std::vector<char> out(capacity+2,'!');
      assert(copy(out.data()+1,capacity,text)==expected.size());
      assert(out.front()=='!'&&out.back()=='!');
      if(capacity) {
        const size_t copied=std::min(expected.size(),capacity-1);
        assert(memcmp(out.data()+1,expected.data(),copied)==0);
        assert(out[copied+1]==0);
      }
    }
    Output output;assert(output.print(text)==expected.size());assert(output.data==expected);
    output.data.clear();output.limit=expected.size()/2;
    assert(output.print(text)==output.limit);assert(output.data==expected.substr(0,output.limit));
  }
  std::string dynamic(2000,'x');Text plain(dynamic.c_str());
  assert(plain.plain()==dynamic.data());
  Reader null{Text(nullptr)};assert(!Text(nullptr));assert(null.next()==0&&null.next()==0);
  assert(bool(Text::encoded(0)));
  char out='!';assert(copy(&out,0,nullptr)==0&&out=='!');
  puts("Packed text: every resident literal, M8, bounded copies, raw lifetimes and short writes PASS");
}
