#include "zx0.hpp"
struct Job {u32 prepare,emit;const u8* input;u32 size;u8* workspace;u32 work_size;u8* output;u32 capacity,written;zx0::Prepared prepared;};
static bool write(void* context,u8 value) {auto& j=*(Job*)context;if(j.written==j.capacity)return false;j.output[j.written++]=value;return true;}
extern "C" __attribute__((noipa)) bool flash_probe(Job* j) {
  typedef bool(*Prepare)(const u8*,u32,u8*,usize,zx0::Prepared&);
  typedef bool(*Emit)(const zx0::Prepared&,const zx0::Output&);
  j->written=0;const zx0::Output out={j,write};
  if(!((Prepare)(uintptr_t)j->prepare)(j->input,j->size,j->workspace,j->work_size,j->prepared))return false;
  return ((Emit)(uintptr_t)j->emit)(j->prepared,out)&&j->prepared.output_size==j->written;
}
