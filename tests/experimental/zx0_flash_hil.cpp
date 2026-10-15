#include "zx0_prototypes.hpp"
#include "zx0_flash_transport.hpp"
alignas(4) static u8 input[520],output[576],expected[576],workspace[2200];
static unsigned output_size;
static const FlashProfile* selected_profile;
struct Sink {u8* data;unsigned size,capacity;};
static bool write(void* context,u8 value) {
  auto& sink=*(Sink*)context;
  if(sink.size==sink.capacity)return false;
  sink.data[sink.size++]=value;return true;
}
static bool matches(u32 address,const u8* bytes,unsigned size) {
  const volatile u8* at=(const volatile u8*)(uintptr_t)address;
  for(unsigned i=0;i<size;++i)if(at[i]!=bytes[i])return false;
  return true;
}
static void native_checks() {
  selected_profile=nullptr;
  for(const auto& profile:flash_profiles) {
    if(matches(profile.footer_address,profile.footer,40)&&
       matches(profile.prepare&~1U,profile.prepare_bytes,32)&&
       matches(profile.emit&~1U,profile.emit_bytes,32)) {
      if(selected_profile){++failures;selected_profile=nullptr;return;}
      selected_profile=&profile;
    }
  }
  if(!selected_profile)++failures;
}
static void prepare_input(const BenchCase& c,unsigned align) {
  u32 random=0xC061F411;
  for(unsigned i=0;i<c.size;++i) {
    random^=random<<13;random^=random>>17;random^=random<<5;
    input[align+i]=c.pattern==0?'X':c.pattern==1?(u8)('a'+i%2):c.pattern==2?(u8)('a'+i%3):
      c.pattern==3?(u8)random:c.pattern==4?source_fixture[i%sizeof(source_fixture)]:image_fixture[i%sizeof(image_fixture)];
  }
}
static unsigned work_size(const BenchCase& c) {return c.parameter?3*c.size+64:4*(c.size+1)+64;}
static u32 encode(bool reference,const BenchCase& c,unsigned align) {
  Sink sink={output+align,0,sizeof(output)-align};const zx0::Output out={&sink,write};
  zx0::EncodeResult result={};bool ok;
  if(reference) {
    ok=zx0_prototypes::encode_scalar(input+align,c.size,workspace+align,work_size(c),out,result);
  } else {
    if(!selected_profile)return 0;
    typedef bool(*Prepare)(const u8*,u32,u8*,usize,zx0::Prepared&);
    typedef bool(*Emit)(const zx0::Prepared&,const zx0::Output&);
    zx0::Prepared prepared;memset(&prepared,0,sizeof(prepared));
    ok=((Prepare)(uintptr_t)selected_profile->prepare)(input+align,c.size,workspace+align,work_size(c),prepared);
    __asm__ __volatile__("" : "+m"(prepared) :: "memory");
    if(ok)ok=((Emit)(uintptr_t)selected_profile->emit)(prepared,out);
    result.output_size=prepared.output_size;result.mode=prepared.mode;
  }
  output_size=sink.size;
  return ok&&result.output_size==sink.size&&result.mode==(c.parameter?zx0::EncodeMode::GREEDY:zx0::EncodeMode::BOUNDED_OPTIMAL)?sink.size:0;
}
static void measure(const BenchCase& c,unsigned align) {
  prepare_input(c,align);memset(output,0xA7,sizeof(output));
  const u32 reference=encode(true,c,align);
  if(!reference){++failures;return;}
  memcpy(expected,output,sizeof(output));memset(output,0xA7,sizeof(output));
  const u32 actual=encode(false,c,align);
  if(!actual||memcmp(output,expected,sizeof(output)))++failures;
  const unsigned iterations=c.size<=16?4:1;u32 times[7];
  for(unsigned sample=0;sample<7;++sample) {
    checksum+=encode(false,c,align);
    const u32 start=cycles();
    for(unsigned i=0;i<iterations;++i)checksum+=encode(false,c,align);
    times[sample]=cycles()-start;mk61_api->service();
  }
  row(0,align,iterations,times);
}
static void benchmark(unsigned index) {
  for(unsigned align=0;align<4;++align)measure(bench_cases[index],align);
}
