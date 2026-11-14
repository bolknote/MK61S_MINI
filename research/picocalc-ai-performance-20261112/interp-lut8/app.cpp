#pragma GCC optimize("O3","fp-contract=off")
#include "mk61_app.h"
#include "mk61_ai_math_candidates.hpp"
#include "interp.hpp"
#include "addresses.hpp"
#include <cstdint>
using U=std::uint32_t;
using namespace ai_candidates;
namespace {
constexpr unsigned Variants=7,Cases=32,Rounds=7,Repeats=8;
const Ops ops{reinterpret_cast<Binary>(math_add_address),reinterpret_cast<Binary>(math_mul_address)};
using Native=void(*)(void*);
using Dot=std::int32_t(*)(const std::uint8_t*,const mk61ai_lut8x32*);
struct Job {mk61ai::LinearBatch b{};unsigned variant=0;bool ok=false,restored=false;float out[28]{};};
Job jobs[2];mk61ai::LinearBatch original{};
const float* expected=nullptr;
const mk61_app_services* services=nullptr;
struct Row {U available,ok,us[Rounds],state_ok,groups,rows,checksum;};
struct Case {U id,tensor,position,rows,columns,row_base,total_rows,head;Row variant[Variants];};
struct Report {U magic,version,before,hz,after,restored,count,rounds,repeats,cores,workspace_bytes,failed_case;Case cases[Cases];};
Report report{};
U micros(){asm volatile("":::"memory");return *reinterpret_cast<volatile U*>(0x40054028);}
U crc(const std::uint8_t* p,unsigned n) {
 U v=~0U;for(unsigned i=0;i<n;++i){v^=p[i];for(unsigned b=0;b<8;++b)v=(v>>1)^((0U-(v&1))&0xedb88320U);}return ~v;
}
__attribute__((noipa)) bool submit(void* context,void(*function)(void*)) {
 return reinterpret_cast<bool(*)(void*,void(*)(void*))>(submit_compute_address)(context,function);
}
__attribute__((noipa)) void join(){reinterpret_cast<void(*)()>(join_compute_address)();}
}
extern "C" {
alignas(4) U m0_interp_header[16]{};
alignas(4) std::uint8_t m0_interp_payload[13000]{};
mk61ai_lut8x32* m0_interp_tables=nullptr;
struct ProbeResult {U ok,state_ok,output[28];};
ProbeResult m0_interp_result{};
}
namespace {
template<unsigned V> void matrix(Job& j) {
 auto& b=j.b;
 if constexpr(V==0) {
  reinterpret_cast<Native>(b.columns==128?linear_lut8_address:linear_direct_address)(&b);
  j.ok=b.status==mk61ai::ModelStatus::OK;j.restored=true;return;
 }
 constexpr bool hardware=V>=5,group_major=V==2 || V==4 || V==6;
 interp_lut8::State state;
 if constexpr(hardware){state.save();state.configure();}
 const auto* tables=reinterpret_cast<const mk61ai_lut8x32*>(b.lookup);
 auto dot=[&](unsigned r,unsigned g) {
  const auto* w=b.weights+r*64+g*16;
  if constexpr(hardware)return interp_dot32(w,tables[g].sum);
  else if constexpr(V>=3)return packed_dot32(w,tables+g);
  else return reinterpret_cast<Dot>(dot_lut8_address)(w,tables+g);
 };
 auto term=[&](unsigned r,unsigned g,int d) {
  const auto* p=b.scales+r*8+g*2;
  const auto h=std::uint16_t(p[0]|unsigned(p[1])<<8);
  return ops.mul(mk61ai::half_scaled_q4_dot(d,h),b.activation_scales[g]);
 };
 if constexpr(group_major) {
  for(unsigned r=0;r<b.rows;++r)b.output[r]=0;
  for(unsigned g=0;g<4;++g) {
   if constexpr(hardware)interp_lut8::State::bases(tables+g);
   for(unsigned r=0;r<b.rows;++r)b.output[r]=ops.add(b.output[r],term(r,g,dot(r,g)));
  }
 } else {
  for(unsigned r=0;r<b.rows;++r) {
   float value=0;
   for(unsigned g=0;g<4;++g) {
    if constexpr(hardware)interp_lut8::State::bases(tables+g);
    value=ops.add(value,term(r,g,dot(r,g)));
   }
   b.output[r]=value;
  }
 }
 j.ok=true;
 for(unsigned r=0;r<b.rows;++r)j.ok=j.ok && finite(b.output[r]);
 if constexpr(hardware)j.restored=state.restore();else j.restored=true;
 j.ok=j.ok && j.restored;
}
void calculate(void* ptr) {
 auto& j=*static_cast<Job*>(ptr);j.ok=j.restored=false;
 switch(j.variant) {
  case 0:matrix<0>(j);break;case 1:matrix<1>(j);break;
  case 2:matrix<2>(j);break;case 3:matrix<3>(j);break;
  case 4:matrix<4>(j);break;case 5:matrix<5>(j);break;case 6:matrix<6>(j);break;
 }
}
void setup(unsigned v,unsigned cores) {
 const unsigned half=cores==2?original.rows/2:original.rows;
 for(unsigned k=0;k<cores;++k) {
  auto& j=jobs[k];const unsigned start=k?half:0;
  j.b=original;j.b.rows=k?original.rows-half:half;
  j.b.weights+=start*original.columns/2;j.b.scales+=start*original.columns/16;
  j.b.output=j.out;j.variant=v;j.ok=j.restored=false;
 }
}
bool dispatch(unsigned cores) {
 ComputeLease worker(submit,join);bool accepted=false;
 if(cores==2)accepted=worker.start(&jobs[1],calculate);
 calculate(&jobs[0]);
 if(cores==2){if(accepted)worker.join();else calculate(&jobs[1]);}
 return cores==1 || accepted;
}
bool collect(unsigned cores) {
 bool ok=true,state_ok=true;unsigned row=0;
 for(unsigned k=0;k<cores;++k) {
  const auto& j=jobs[k];ok=ok && j.ok;state_ok=state_ok && j.restored;
  for(unsigned r=0;r<j.b.rows;++r,++row) {
   const U v=bits(j.out[r]);m0_interp_result.output[row]=v;ok=ok && v==bits(expected[row]);
  }
 }
 m0_interp_result.ok=ok;m0_interp_result.state_ok=state_ok;return ok && state_ok;
}
}
extern "C" __attribute__((noipa)) U m0_interp_load() {
 const unsigned rows=m0_interp_header[3],cols=m0_interp_header[4],groups=m0_interp_header[5];
 if(!m0_interp_tables || !rows || rows>28 || (cols!=128 && cols!=384) || groups!=cols/32)return 0;
 const unsigned w=rows*cols/2,s=rows*groups*2,total=cols+groups*8+w*2+s*2+rows*4;
 if(total>sizeof(m0_interp_payload) || m0_interp_header[11]!=w || m0_interp_header[12]!=s || m0_interp_header[13]!=s || crc(m0_interp_payload,total)!=m0_interp_header[15])return 0;
 auto* p=m0_interp_payload;original={};original.rows=rows;original.columns=cols;
 original.arithmetic=mk61ai::Arithmetic::INT8;original.bits=4;original.grid=cols==128?256:0;
 original.quant=reinterpret_cast<const std::int8_t*>(p);p+=cols;
 original.activation_scales=reinterpret_cast<const float*>(p);p+=groups*4;
 original.quant_sums=reinterpret_cast<const std::int32_t*>(p);p+=groups*4;
 const auto* nibble=p;p+=w;const auto* planar=p;p+=w;
 original.weights=cols==128?planar:nibble;original.scales=p;p+=s;
 p+=s;expected=reinterpret_cast<const float*>(p);original.lookup=reinterpret_cast<const float*>(m0_interp_tables);
 if(cols==128)for(unsigned g=0;g<4;++g)
  reinterpret_cast<void(*)(const std::int8_t*,mk61ai_lut8x32*)>(prepare_lut8_address)(original.quant+g*32,m0_interp_tables+g);
 return 1;
}
extern "C" __attribute__((noipa)) U m0_interp_probe(U variant,U cores) {
 if(variant>=Variants || (cores!=1 && cores!=2) || (original.columns!=128 && variant))return 0;
 setup(variant,cores);return dispatch(cores) && collect(cores);
}
namespace {
__attribute__((noipa)) void stage(unsigned n) {
 char text[64];const int size=mk61_app_snprintf(services,text,sizeof(text),"AI_INTERP stage=%u\r\n",n);
 if(size>0)services->call(MK61_SERVICE_DEBUG_WRITE,unsigned(size),0,0,text);
}
bool read(const char* name,void* target,U offset,U bytes) {
 auto* p=static_cast<std::uint8_t*>(target);
 for(U at=0;at<bytes;) {
  const U n=bytes-at>4096?4096:bytes-at;mk61_service_file_bytes r{name,p+at,offset+at,n};
  if(!services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_READ,0,sizeof(r),&r))return false;
  at+=n;mk61_api->service();
 }
 return true;
}
struct ClockState {U sys=0,peri=0,peri_ctrl=0,peri_div=0,spi0_hz=0,spi1_hz=0;bool changed=false,restore_attempted=false;};
static_assert(sizeof(ClockState)==28 && sizeof(mk61ai::LinearBatch)==60 && sizeof(Row)==52,"Pinned native ABI");
}
extern "C" U mk61_app_flow_step(mk61_app_flow* flow) {
 if(!mk61_app_flow_compatible(flow))return 0;
 services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_BUFFERS);
 if(!services)return 0;
 uintptr_t footer=footer_address;asm volatile("":"+r"(footer));
 for(unsigned i=0;i<10;++i)if(reinterpret_cast<volatile const U*>(footer)[i]!=footer_words[i])return 0;
 mk61_service_file app{};if(!services->call(MK61_SERVICE_FILE_ENTRY,0,flow->current.file_id,0,&app))return 0;
 U header[4];if(!read("MATHCASE.BIN",header,0,sizeof(header)) || header[0]!=0x4d434e31 || header[1]!=1 || !header[2] || header[2]>Cases)return 0;
 mk61_service_buffer workspace{};report.workspace_bytes=4*sizeof(mk61ai_lut8x32);
 if(!mk61_app_buffer_acquire(services,report.workspace_bytes,MK61_BUFFER_DIRECT,&workspace))return 0;
 bool ok=mk61_app_buffer_call(services,MK61_BUFFER_INFO,&workspace) && workspace.storage==MK61_BUFFER_SRAM && workspace.data;
 m0_interp_tables=reinterpret_cast<mk61ai_lut8x32*>(workspace.data);
 reinterpret_cast<void(*)()>(math_initialize_address)();
 report.magic=0x49505431;report.version=1;report.count=header[2];report.rounds=Rounds;report.repeats=Repeats;report.cores=2;report.failed_case=~0U;
 report.before=reinterpret_cast<U(*)()>(clock_hz_address)();ClockState clock;
 stage(1);reinterpret_cast<void(*)(bool)>(render_gate_address)(false);stage(2);
 ok=ok && report.before==125000000 && reinterpret_cast<bool(*)(unsigned,ClockState*)>(clock_begin_address)(270,&clock);
 report.hz=reinterpret_cast<U(*)()>(clock_hz_address)();ok=ok && report.hz==270000000;
 stage(3);const U warm=micros();while(ok && micros()-warm<500000)mk61_api->service();
 U offset=16;
 for(unsigned index=0;ok && index<report.count;++index) {
  report.failed_case=index;
  if(offset>header[3] || sizeof(m0_interp_header)>header[3]-offset || !read("MATHCASE.BIN",m0_interp_header,offset,sizeof(m0_interp_header))){ok=false;break;}
  offset+=sizeof(m0_interp_header);
  const U bytes=m0_interp_header[4]+m0_interp_header[5]*8+m0_interp_header[11]*2+m0_interp_header[12]+m0_interp_header[13]+m0_interp_header[3]*4;
  if(bytes>sizeof(m0_interp_payload) || offset>header[3] || bytes>header[3]-offset || !read("MATHCASE.BIN",m0_interp_payload,offset,bytes) || !m0_interp_load()){ok=false;break;}
  offset+=bytes;auto& c=report.cases[index];
  c.id=m0_interp_header[0];c.tensor=m0_interp_header[1];c.position=m0_interp_header[2];c.rows=m0_interp_header[3];c.columns=m0_interp_header[4];
  c.row_base=m0_interp_header[6];c.total_rows=m0_interp_header[7];c.head=m0_interp_header[8];
  for(unsigned v=0;v<Variants;++v) {
   if(c.columns!=128 && v)continue;
   auto& row=c.variant[v];row.available=1;
   ok=m0_interp_probe(v,1) && ok;ok=m0_interp_probe(v,2) && ok;
   row.ok=ok;row.state_ok=m0_interp_result.state_ok;
  }
  for(unsigned round=0;ok && round<Rounds;++round)for(unsigned k=0;ok && k<Variants;++k) {
   const unsigned v=(round+k+index)%Variants;auto& row=c.variant[v];if(!row.available)continue;
   for(unsigned repeat=0;ok && repeat<Repeats;++repeat) {
    mk61_api->service();setup(v,2);const U start=micros();const bool worker=dispatch(2);const U done=micros();
    row.us[round]+=done-start;ok=worker && collect(2);row.state_ok&=m0_interp_result.state_ok;
    row.checksum=crc(reinterpret_cast<const std::uint8_t*>(m0_interp_result.output),c.rows*4);
    row.groups=c.rows*(c.columns/32);row.rows=c.rows;
   }
  }
  char progress[64];const int n=mk61_app_snprintf(services,progress,sizeof(progress),"AI_INTERP case=%u/%u ok=%u\r\n",index+1,report.count,unsigned(ok));
  if(n>0)services->call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,progress);
 }
 ok=ok && offset==header[3];if(ok)report.failed_case=~0U;
 stage(6);report.restored=reinterpret_cast<bool(*)(ClockState*)>(clock_end_address)(&clock);
 report.after=reinterpret_cast<U(*)()>(clock_hz_address)();
 reinterpret_cast<void(*)(bool)>(render_gate_address)(true);stage(7);
 ok=ok && report.restored && report.after==report.before;
 ok=mk61_app_buffer_release(services,workspace.handle) && ok;m0_interp_tables=nullptr;
 mk61_service_write write{"INTERP.BIN",reinterpret_cast<const std::uint8_t*>(&report),unsigned(48+report.count*sizeof(Case)),MK61_SERVICE_INVALID_ID};
 ok=services->call(MK61_SERVICE_FILE_WRITE,app.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&write) && ok;
 mk61_app_flow_exit(flow,ok?MK61_APP_OK:MK61_APP_RUNTIME_ERROR,MK61_FLOW_OK);return 1;
}
