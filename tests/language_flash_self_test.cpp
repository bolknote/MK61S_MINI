#include "language_flash_fixture.hpp"
#include "language_flash.hpp"
#include <array>
#include <map>
#include <vector>
#include <algorithm>
#include <cassert>
#include <cstdio>
using namespace language_vm::flash;

int main() {
  static_assert(sizeof(Writer)<WRITE_BYTES+80 && sizeof(Reader)<READ_BYTES*2+64,"paging RAM must stay bounded");
  Disk disk;
  Writer image(disk.io(),IMAGE);
  for(uint32_t i=0;i<200000;++i)assert(image.byte(i,uint8_t(i*37)));
  const uint8_t patch[]={1,2,3,4,5,6,7,8};
  assert(image.write(65533,patch,sizeof(patch)) && image.flush());
  struct Source {Disk* disk;};Source source{&disk};
  Reader reader({&source,[](void* raw,uint32_t at,uint8_t* out,uint16_t n) {
    return Disk::read(((Source*)raw)->disk,IMAGE,at,out,n);
  },image.size()});
  for(uint32_t i=0;i<image.size();++i)
    assert(reader.at(i)==(i>=65533 && i<65541?patch[i-65533]:uint8_t(i*37)));
  uint8_t bytes[10];assert(!reader.read(UINT32_MAX-3,bytes,sizeof(bytes)));
  assert(reader.good());
  LineIndex index(disk.io(),INDEX_A);Writer records(disk.io(),INDEX_A);
  for(unsigned i=0;i<3000;++i)assert(index.set(records,uint16_t(i),{3000-i,0,uint16_t(i),uint16_t(i+1)}));
  assert(records.flush() && index.sort(false));
  for(unsigned i=0;i<3000;++i) {
    Line line;assert(index.get(uint16_t(i),line));assert(line.number==i+1 && line.begin==2999-i);
    assert(index.find(i+1)==int(i));
  }
  assert(index.find(4000)==-1 && index.good() && disk.polls);
  const unsigned before=disk.writes;disk.fail=int(before);
  Writer failed(disk.io(),BOUNDARIES);assert(failed.byte(0,42));assert(!failed.flush() && !failed.good());
  // A reader latches physical I/O failure and cannot publish fabricated zeroes.
  Reader broken({nullptr,[](void*,uint32_t,uint8_t*,uint16_t){return false;},100000});
  assert(!broken.read(70000,bytes,sizeof(bytes)) && !broken.good());
  puts("Flash language files: 200 KiB, >64-KiB patches, 3000 reverse lines, bounded RAM and I/O failures PASS");
}
