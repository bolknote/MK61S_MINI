#include "zx0_prototypes.hpp"
#include "zx0_hil_transport.hpp"
alignas(4) static u8 input[520],output[576],expected[576],workspace[2200];
alignas(4) static u8 packed[576];
static unsigned output_size,packed_size;
struct Source {unsigned position;};
static bool read(void* context,u8& value) {
  auto& s=*(Source*)context;if(s.position==packed_size)return false;
  value=packed[s.position++];return true;
}
struct Sink {u8* data;unsigned size,capacity;};
static bool write(void* context,u8 value) {
  auto& s=*(Sink*)context;if(s.size==s.capacity)return false;s.data[s.size++]=value;return true;
}
static const zx0_prototypes::Decode decoders[]={zx0_prototypes::decode_scalar,zx0_prototypes::decode_word};
static const zx0_prototypes::Encode encoders[]={zx0_prototypes::encode_scalar,zx0_prototypes::encode_word,zx0_prototypes::encode_dsp};
static void prepare(const BenchCase& c,unsigned align) {
  u32 random=0xC061F411;
  for(unsigned i=0;i<c.size;++i) {
    random^=random<<13;random^=random>>17;random^=random<<5;
    input[align+i]=c.pattern==0?'X':c.pattern==1?(u8)('a'+i%2):c.pattern==2?(u8)('a'+i%3):
      c.pattern==3?(u8)random:c.pattern==4?source_fixture[i%sizeof(source_fixture)]:image_fixture[i%sizeof(image_fixture)];
  }
}
// Enough for a fragmented greedy token plan, but still below the threshold
// for bounded-optimal mode. A fixed 512-byte plan can legitimately reject text.
static unsigned work_size(const BenchCase& c) {return c.parameter?3*c.size+64:4*(c.size+1)+64;}
static u32 encode(unsigned variant,const BenchCase& c,unsigned align) {
  Sink sink={output+align,0,sizeof(output)-align};const zx0::Output out={&sink,write};zx0::EncodeResult result={};
  const bool ok=encoders[variant](input+align,c.size,workspace+align,work_size(c),out,result);
  output_size=sink.size;
  return ok&&result.output_size==sink.size&&result.mode==(c.parameter?zx0::EncodeMode::GREEDY:zx0::EncodeMode::BOUNDED_OPTIMAL)?sink.size:0;
}
static u32 decode(unsigned variant,const BenchCase& c,unsigned align) {
  Source source={0};const zx0::Input in={&source,read};u32 written=0;
  const bool ok=decoders[variant](in,packed_size,output+align,c.size,written);
  output_size=written;return ok&&source.position==packed_size&&written==c.size?written:0;
}
static void measure(const BenchCase& c,unsigned align,unsigned variant) {
  prepare(c,align);memset(output,0xA7,sizeof(output));
  const u32 reference=encode(0,c,align);
  if(!reference) {++failures;return;}
  if(c.family==3) {
    packed_size=output_size;memcpy(packed,output+align,packed_size);
    memset(expected,0xA7,sizeof(expected));memcpy(expected+align,input+align,c.size);
  } else memcpy(expected,output,sizeof(output));
  memset(output,0xA7,sizeof(output));
  const u32 actual=c.family==3?decode(variant,c,align):encode(variant,c,align);
  if(!actual||memcmp(output,expected,sizeof(output)))++failures;
  const unsigned iterations=c.family==3?(c.size<=64?64:16):(c.size<=16?4:1);u32 times[7];
  for(unsigned sample=0;sample<7;++sample) {
    checksum+=c.family==3?decode(variant,c,align):encode(variant,c,align);
    const u32 start=cycles();
    for(unsigned i=0;i<iterations;++i)checksum+=c.family==3?decode(variant,c,align):encode(variant,c,align);
    times[sample]=cycles()-start;mk61_api->service();
  }
  row(variant,align,iterations,times);
}
static void benchmark(unsigned index) {
  const auto& c=bench_cases[index];const unsigned count=c.family==3?2:3;
  for(unsigned align=0;align<4;++align)for(unsigned order=0;order<count;++order)
    measure(c,align,(index+order)%count);
}
static void native_checks() {}
