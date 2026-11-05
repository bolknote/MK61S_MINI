#include "language_flash_fixture.hpp"
#include "language_bytecode.hpp"
#include "language_source_map.hpp"
#include <cstdio>
#include <string>
#include <vector>
#include <utility>

using namespace language_vm;
static void compare(Language language,const char* text) {
  const auto n=uint16_t(strlen(text));
  uint8_t memory[MAX_IMAGE];
  const auto ram=compile(language,text,n,memory,sizeof(memory));
  assert(ram.error==Error::NONE);
  std::vector<uint8_t> guarded(ram.size+16,0xA5);
  const auto exact=compile(language,text,n,guarded.data()+8,uint16_t(ram.size));
  assert(exact.error==Error::NONE && exact.size==ram.size && !memcmp(memory,guarded.data()+8,ram.size));
  for(unsigned i=0;i<8;++i)assert(guarded[i]==0xA5 && guarded[ram.size+8+i]==0xA5);
  Disk disk;source::Reader source(text,n);
  const auto paged=compile_flash_source(language,source,disk.io());
  assert(paged.error==Error::NONE && paged.size==ram.size);
  std::vector<uint8_t> bytes(paged.size);
  assert(Disk::read(&disk,IMAGE,0,bytes.data(),uint16_t(bytes.size())));
  assert(!memcmp(bytes.data(),memory,bytes.size()));
  View raw;
  assert(inspect(memory,uint16_t(ram.size),raw)==Error::NONE);
  flash::Reader reader({&disk,[](void* p,uint32_t at,uint8_t* out,uint16_t count) {
    return Disk::read(p,IMAGE,at,out,count);
  },paged.size});
  View stored;assert(inspect_flash(reader,disk.io(),stored)==Error::NONE);
  assert(raw.code==stored.code && raw.end==stored.end && raw.lines==stored.lines);
  assert(raw.address_bytes()==4 && stored.address_bytes()==4);
  for(uint32_t pc=raw.code;pc<raw.end;) {
    const auto next=instruction_end(raw,pc);
    assert(next && next==instruction_end(stored,pc));pc=next;
  }
  for(unsigned i:{6U,7U,8U,12U,18U,28U,32U}) {
    const auto saved=memory[i];memory[i]=i==7?128:0;
    if(i==8 || i==28 || i==32)memory[i]=uint8_t(saved+1);
    View bad;assert(inspect(memory,uint16_t(ram.size),bad)==Error::INVALID_IMAGE);
    memory[i]=saved;
  }
  memcpy(memory,"LBV1",4);View old;
  assert(inspect(memory,uint16_t(ram.size),old)==Error::INVALID_IMAGE);
}
static void coalesced_columns() {
  const uint32_t code=HEADER_SIZE+8,end=code+13;
  source_map::Positions positions;positions.reset(code);std::vector<uint8_t> map;
  auto output=[&](uint32_t at,const uint8_t* bytes,uint16_t n) {
    assert(at==map.size());map.insert(map.end(),bytes,bytes+n);return true;
  };
  for(const auto row:{std::pair<unsigned,unsigned>{0,6},{2,6},{3,6},{4,18},{6,18},{8,6},{9,6},{11,18}})
    assert(positions.note(code+row.first,uint16_t(row.second),output));
  assert(positions.flush(output) && positions.count==4);
  std::vector<uint8_t> image(end+map.size()+4,0);
  memcpy(image.data(),"LBV2",4);image[4]=VERSION;image[5]=1;image[6]=1;
  flash::dword(image.data()+8,uint32_t(image.size()));flash::dword(image.data()+12,code);
  flash::word(image.data()+16,1024);flash::word(image.data()+18,1);
  flash::dword(image.data()+28,end);flash::word(image.data()+38,positions.count);
  flash::dword(image.data()+HEADER_SIZE,10);flash::dword(image.data()+HEADER_SIZE+4,code);
  for(uint32_t pc=code;pc<end-1;++pc)image[pc]=uint8_t(Op::PRINT_FLUSH);
  memcpy(image.data()+end,map.data(),map.size());flash::dword(image.data()+end+map.size(),uint32_t(map.size()));
  flash::dword(image.data()+24,checksum(image.data()+HEADER_SIZE,image.size()-HEADER_SIZE));
  View view;assert(inspect(image.data(),uint16_t(image.size()),view)==Error::NONE);
  for(unsigned pc=0;pc<12;++pc)
    assert(source_column(view,code+pc)==(pc<4?6:pc<8?18:pc<11?6:18));
  assert(source_column(view,end-1)==0);
  positions.reset(code);map.clear();
  assert(positions.note(code,6,output) && positions.flush(output));
  assert(positions.note(code+4,6,output) && positions.flush(output));
  assert(!positions.note(code+3,18,output)); // A skipped record cannot hide a rewind.
}
int main() {
  coalesced_columns();
  for(const auto text:{"10 A=3+4*5\n20 END\n", "10 IF A<3 GOTO 30\n20 A=A+1\n30 END\n",
      "10 FOR I=1 TO 3;@(I)=I;NEXT I\n20 END\n", "10 DATA 1,.2,-3\n20 READ A,B,C\n30 END\n",
      "10 @(2)=7;A=1,@(INT(4/2));PRINT B;END\n", "10 @(2)=7;A=1,@(2/1)+3;PRINT B;END\n",
      "10 PRINT 'TEXT';A\n20 INPUT B\n30 END\n", "10 A=CALL(100,3);END\n100 RETURN ARG(1)+2\n"})
    compare(Language::BASIC,text);
  for(const auto text:{"1.10 S A=3+4*5\n1.20 E\n", "1.10 F I=1,3;S A=A+I\n1.20 E\n",
      "1.10 D 2\n1.20 E\n2.10 S A=7\n", "1.10 P \"TEXT\",A\n1.20 A B\n1.30 E\n"})
    compare(Language::FOCAL,text);
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    uint8_t bytes[128];const auto c=compile_expression(language,"1+2",3,bytes,sizeof(bytes));
    assert(c.error==Error::NONE && !memcmp(bytes,"LBV2",4) && bytes[4]==VERSION);
    View v;assert(inspect(bytes,uint16_t(c.size),v)==Error::NONE && v.expression && v.code==HEADER_SIZE);
    assert(v.address_bytes()==4 && v.missing()==UINT32_MAX);
  }
  std::puts("Single LBV2 wire: BASIC/FOCAL RAM/paged byte identity, INPUT, widths, corruption and rejected LBV1 PASS");
}
