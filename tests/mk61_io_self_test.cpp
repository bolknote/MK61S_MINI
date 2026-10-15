#include "mk61_io.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <limits>
struct Buffer : mk61_io::Output<Buffer> {
  std::string bytes;
  size_t limit=100;
  using Output::write;
  size_t write(uint8_t byte) {
    if(bytes.size()==limit) return 0;
    bytes.push_back(static_cast<char>(byte));return 1;
  }
};
static std::string reference(uint32_t value,int base) {
  char text[50];
  if(base==2) {
    std::string result;
    do {result.insert(result.begin(),static_cast<char>('0'+(value&1)));value>>=1;} while(value);
    return result;
  }
  std::snprintf(text,sizeof(text),base==8?"%o":base==16?"%X":"%u",value);
  return text;
}
int main() {
  uint32_t random=0;
  for(unsigned n=0;n<4096;++n) {
    random=random*1664525U+1013904223U;
    for(int base:{2,8,10,16}) {
      Buffer output;
      auto wanted=reference(random,base);
      assert(output.print(random,base)==wanted.size() && output.bytes==wanted);
      Buffer clipped;clipped.limit=n%17;
      const auto count=clipped.print(random,base);
      assert(count==clipped.bytes.size() && clipped.bytes==wanted.substr(0,clipped.limit));
    }
    Buffer output;const int32_t signed_value=static_cast<int32_t>(random);
    char wanted[30];std::snprintf(wanted,sizeof(wanted),"%d",signed_value);
    assert(output.print(signed_value)==std::strlen(wanted) && output.bytes==wanted);
  }
  Buffer minimum;minimum.print(std::numeric_limits<int32_t>::min());assert(minimum.bytes=="-2147483648");
  Buffer text;text.println("123");text.println('A');text.println(uint8_t{15},16);text.print(-1,16);
  assert(text.bytes=="123\r\nA\r\nF\r\nFFFFFFFF");
  Buffer raw;raw.print(uint32_t{0},0);raw.write("x");assert(raw.bytes==std::string("\0x",2));
  assert(raw.print(static_cast<const char*>(nullptr))==0);
  std::puts("MK61 narrow output: signed/unsigned bases, truncation, INT32_MIN, CRLF and raw bytes PASS");
}
