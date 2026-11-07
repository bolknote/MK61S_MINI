#include "mk61_ai_model.hpp"
#include <cstring>
#include <vector>
namespace {
mk61ai::Model model;
std::vector<std::uint64_t> workspace;
std::vector<std::uint8_t> cache;
const std::uint8_t *source;
unsigned size;
int cancel_after = -1;
bool read_package(void *, std::uint32_t at, void *p, unsigned n) {
  if (at > size || n > size - at)
    return false;
  std::memcpy(p, source + at, n);
  return true;
}
bool read_cache(void *, std::uint32_t at, void *p, unsigned n) {
  if (at > cache.size() || n > cache.size() - at)
    return false;
  std::memcpy(p, cache.data() + at, n);
  return true;
}
bool write_cache(void *, std::uint32_t at, const void *p, unsigned n) {
  if (at > cache.size() || n > cache.size() - at)
    return false;
  std::memcpy(cache.data() + at, p, n);
  return true;
}
bool service(void *) { return cancel_after < 0 || cancel_after-- > 0; }
} // namespace
extern "C" {
int mk_ai_open(const unsigned char *p, unsigned n) {
  source = p;
  size = n;
  auto status = model.open({nullptr, n, read_package, nullptr});
  if (status != mk61ai::ModelStatus::OK)
    return int(status);
  workspace.resize((model.workspace_bytes() + 7) / 8);
  cache.resize(model.cache_bytes());
  return int(
      model.bind(workspace.data(), workspace.size() * 8,
                 {nullptr, unsigned(cache.size()), read_cache, write_cache}));
}
int mk_ai_encode(const char *s, unsigned short *out, unsigned capacity,
                 unsigned *used, int bos) {
  return int(model.encode(s, out, capacity, *used, bos));
}
int mk_ai_decode(unsigned short id, char *out, unsigned capacity,
                 unsigned *used) {
  return int(model.decode(id, out, capacity, *used));
}
int mk_ai_forward(unsigned short token, int output, unsigned short *best,
                  float *logits, int arithmetic) {
  return int(model.forward(token, output, *best, service, nullptr,
                           static_cast<mk61ai::Arithmetic>(arithmetic),
                           logits));
}
void mk_ai_reset() {
  model.reset();
  cancel_after = -1;
}
void mk_ai_cancel_after(int n) { cancel_after = n; }
unsigned mk_ai_position() { return model.position(); }
int mk_ai_rewind(unsigned n) { return model.rewind(n); }
int mk_ai_forward_only(unsigned short token, unsigned short *best,
                       unsigned allowed) {
  return int(model.forward(
      token, true, *best, service, nullptr, mk61ai::Arithmetic::LUT_FLOAT32,
      nullptr,
      [](void *p, std::uint16_t id) {
        return id == *static_cast<unsigned *>(p);
      },
      &allowed));
}
unsigned mk_ai_workspace() { return unsigned(model.workspace_bytes()); }
unsigned mk_ai_cache() { return model.cache_bytes(); }
}


#include "codec_native_bridge.hpp"
namespace {
std::vector<unsigned char> quality_mask;int quality_profile=0;
mk61ai::Quantization precision(void*,unsigned tensor,unsigned position,mk61ai::Arithmetic) {
 using A=mk61ai::Arithmetic;mk61ai::Quantization q{A::INT8};
 const int type=tensor==0?4:((tensor-2)%11>=8?(((tensor-2)%11==10)?3:2):(((tensor-2)%11==6)?1:0));
 const int layer=tensor?int((tensor-2)/11):-1;
 switch(quality_profile) {
 case 0:q.mode=A::LUT_FLOAT32;break;
 case 1:break;
 case 2:q.mode=A::INT16;break;
 case 3:case 4:case 5:case 6:case 7:q.mode=type==quality_profile-3?A::INT8:A::LUT_FLOAT32;break;
 case 8:q.mode=type<=1?A::INT8:A::LUT_FLOAT32;break;
 case 9:q.mode=type==4?A::LUT_FLOAT32:A::INT8;break;
 case 10:q.mode=type==3?A::LUT_FLOAT32:A::INT8;break;
 case 11:q.mode=type==1?A::LUT_FLOAT32:A::INT8;break;
 case 12:q.mode=type==2?A::LUT_FLOAT32:A::INT8;break;
 case 13:q.mode=type==0?A::LUT_FLOAT32:A::INT8;break;
 case 14:q.mode=type==4?A::INT16:A::INT8;break;
 case 15:q.mode=type==3?A::INT16:A::INT8;break;
 case 16:q.mode=type<=1?A::INT16:A::INT8;break;
 case 17:q.mode=type==4?A::LUT_FLOAT32:A::INT16;break;
 case 18:q.mode=(type==4 || layer==9)?A::LUT_FLOAT32:A::INT16;break;
 case 19:q.group=16;break;
 case 20:q.group=8;break;
 case 21:case 22:case 23:q.stochastic=true;q.seed=611009U+123457U*unsigned(quality_profile-21);break;
 case 24:q.mode=A::SWAR_INT8;break;
 default:
  if(quality_profile>=100)q.mode=A::FLOAT32;
  else if(quality_profile>=30 && quality_profile<40)q.mode=layer==quality_profile-30?A::INT8:A::LUT_FLOAT32;
  else q.mode=A::LUT_FLOAT32;
 }
 return q;
}
}
extern "C" void codec_set_mask(const unsigned short *ids,unsigned n) {
 quality_mask.assign(model.config().vocab,0);for(unsigned i=0;i<n;++i)if(ids[i]<quality_mask.size())quality_mask[ids[i]]=1;
 mk61ai::ComputeExecution e;e.kernel=mk61ai::LinearKernel::SRAM;e.filter_head=true;e.filter_logits=true;e.precision=precision;model.execution(e);
}
extern "C" void codec_set_mode(int profile){quality_profile=profile;}
extern "C" void codec_distribution(int full){auto e=model.execution();e.filter_logits=!full;model.execution(e);}
extern "C" int codec_forward(unsigned short token,int output,unsigned short*best,float*logits) {
 return int(model.forward(token,output,*best,service,nullptr,mk61ai::Arithmetic::LUT_FLOAT32,logits,
 [](void*,std::uint16_t id){return quality_mask[id]!=0;},nullptr));
}
extern "C" int codec_encode(const char*text,unsigned short*out,unsigned cap,unsigned*used) {
 return int(mk61research::encode_h32(model,text,out,cap,*used));
}
