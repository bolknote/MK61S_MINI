#pragma GCC optimize("O3","fp-contract=off")
#include "mk61_app.h"
#include "mk61_ai_math_candidates.hpp"
#include "math-candidate-addresses.hpp"
#include <cstdint>
using namespace ai_candidates;
using U=std::uint32_t;
extern "C" {
alignas(4) U m0_math_header[16]{};
alignas(4) std::uint8_t m0_math_payload[13000]{};
mk61ai_lut8x32* m0_math_tables=nullptr;
struct ProbeResult {U ok,pruned,groups,bounded,zeros,best_id,best_bits,output[MaxRows];};
ProbeResult m0_math_result{};
}
namespace {
const Ops ops{reinterpret_cast<Binary>(math_add_address),reinterpret_cast<Binary>(math_mul_address)};
using Native=void(*)(void*);
struct Job {
 mk61ai::LinearBatch b{};Scratch scratch{};Stats stats{};Best best{};
 const std::uint16_t* norms=nullptr;unsigned variant=0,row_base=0;bool all=false,ok=false;
 float output[MaxRows]{};
};
Job jobs[2];
mk61ai::LinearBatch original{};
const std::uint8_t* planar=nullptr;
const std::uint16_t* norms=nullptr;
const float* expected=nullptr;
Best seed{};
U micros(){asm volatile("":::"memory");return *(volatile U*)0x40054028;}
U crc(const std::uint8_t* p,unsigned n) {
 U v=~0U;for(unsigned j=0;j<n;++j){v^=p[j];for(unsigned bit=0;bit<8;++bit)v=(v>>1)^((0U-(v&1))&0xedb88320U);}return ~v;
}
void calculate(void* ptr) {
 auto& j=*static_cast<Job*>(ptr);j.stats={};j.ok=true;
 if(j.variant==DIRECT) {
  reinterpret_cast<Native>(linear_sram_address)(&j.b);j.ok=j.b.status==mk61ai::ModelStatus::OK;
  j.stats.groups=j.b.rows*(j.b.columns/32);
 } else if(j.variant<=ZERO_SKIP)j.ok=matrix(j.b,j.variant,j.scratch,ops,j.stats);
 else j.ok=classify(j.b,j.norms,j.scratch,ops,j.row_base,
                   j.variant==PRUNE_HALF?j.b.columns/64:j.b.columns/32-1,
                   j.best,j.stats,j.all?j.b.output:nullptr);
 if(j.variant<=ZERO_SKIP)for(unsigned r=0;r<j.b.rows;++r)
  if(better(j.b.output[r],j.row_base+r,j.best))j.best={j.b.output[r],j.row_base+r};
}
void prepare(unsigned variant) {
 jobs[0].scratch.tables=m0_math_tables;
 if(variant==LUT8_FULL)prepare_lut(original,jobs[0].scratch);
 if(variant==ZERO_SKIP)prepare_zero(original,jobs[0].scratch);
 if(variant>=PRUNE_HALF)prepare_bounds(original,jobs[0].scratch);
 jobs[1].scratch=jobs[0].scratch;
 if(variant==LUT8_BOUNDED) {
  jobs[0].scratch.tables=m0_math_tables+MaxGroups;
  jobs[1].scratch.tables=m0_math_tables+MaxGroups+1;
 }
}
void setup(unsigned variant,unsigned cores,bool all) {
 const unsigned first=cores==2?original.rows/2:original.rows;
 for(unsigned k=0;k<cores;++k) {
  auto& j=jobs[k];const unsigned start=k?first:0;
  j.b=original;j.b.rows=k?original.rows-first:first;j.b.weights=
      (variant==LUT8_FULL || variant==LUT8_BOUNDED?planar:original.weights)+start*original.columns/2;
  j.b.scales+=start*original.columns/16;j.b.output=j.output;j.b.status=mk61ai::ModelStatus::OK;
  j.norms=norms+start*(original.columns/32);j.row_base=m0_math_header[6]+start;
  j.best=seed;j.variant=variant;j.all=all;j.ok=false;
 }
}
// Store APP-owned adapter addresses in the guard. With -flto -fipa-pta,
// GCC14 folds a fixed resident address stored in an object callback into an
// impossible call, deleting the two-core timing tail as unreachable. Direct
// pinned calls remain behind noipa boundaries, as in the original dispatch.
__attribute__((noipa)) bool submit_worker(void* context,void(*function)(void*)) {
 return reinterpret_cast<bool(*)(void*,void(*)(void*))>(submit_compute_address)(context,function);
}
__attribute__((noipa)) void join_worker() {reinterpret_cast<void(*)()>(join_compute_address)();}
bool dispatch(unsigned cores) {
 ComputeLease worker(submit_worker,join_worker);
 bool accepted=false;
 if(cores==2)accepted=worker.start(&jobs[1],calculate);
 calculate(&jobs[0]);
 if(cores==2) {
  if(accepted)worker.join();else calculate(&jobs[1]);
 }
 return cores==1 || accepted;
}
bool collect(unsigned cores,unsigned variant,bool all) {
 Best reference=seed;for(unsigned r=0;r<original.rows;++r)if(better(expected[r],m0_math_header[6]+r,reference))reference={expected[r],m0_math_header[6]+r};
 Best best=seed;Stats stats{};bool ok=true;unsigned row=0;
 for(unsigned k=0;k<cores;++k) {
  const auto& j=jobs[k];ok=ok && j.ok;stats.groups+=j.stats.groups;stats.bounded+=j.stats.bounded;stats.pruned+=j.stats.pruned;stats.zeros+=j.stats.zeros;
  if(better(j.best.score,j.best.id,best))best=j.best;
  for(unsigned r=0;r<j.b.rows;++r,++row) {
   const U actual=bits(j.output[r]);m0_math_result.output[row]=actual;
   if(variant<=ZERO_SKIP || all)ok=ok && actual==bits(expected[row]);
  }
 }
 ok=ok && best.id==reference.id && bits(best.score)==bits(reference.score);
 if(all)ok=ok && !stats.pruned;
 m0_math_result.ok=ok;m0_math_result.pruned=stats.pruned;m0_math_result.groups=stats.groups;
 m0_math_result.bounded=stats.bounded;m0_math_result.zeros=stats.zeros;
 m0_math_result.best_id=best.id;m0_math_result.best_bits=bits(best.score);
 return ok;
}
}
extern "C" __attribute__((noipa)) U m0_math_load() {
 const unsigned rows=m0_math_header[3],cols=m0_math_header[4],groups=m0_math_header[5];
 if(!rows || rows>MaxRows || !cols || cols>MaxColumns || cols%32 || groups!=cols/32 ||
    m0_math_header[6]>m0_math_header[7] || rows>m0_math_header[7]-m0_math_header[6])return 0;
 const unsigned w=rows*cols/2,s=rows*groups*2,total=cols+groups*8+w*2+s*2+rows*4;
 if(total>sizeof(m0_math_payload) || m0_math_header[11]!=w || m0_math_header[12]!=s || m0_math_header[13]!=s || crc(m0_math_payload,total)!=m0_math_header[15])return 0;
 auto* p=m0_math_payload;original={};original.arithmetic=mk61ai::Arithmetic::INT8;
 original.bits=4;original.grid=0;original.rows=rows;original.columns=cols;
 original.quant=reinterpret_cast<const std::int8_t*>(p);p+=cols;
 original.activation_scales=reinterpret_cast<const float*>(p);p+=groups*4;
 original.quant_sums=reinterpret_cast<const std::int32_t*>(p);p+=groups*4;
 original.weights=p;p+=w;planar=p;p+=w;original.scales=p;p+=s;
 norms=reinterpret_cast<const std::uint16_t*>(p);p+=s;expected=reinterpret_cast<const float*>(p);
 seed={value(m0_math_header[10]),m0_math_header[9]};
 return finite(seed.score) && validate_norms(original,norms);
}
extern "C" __attribute__((noipa)) U m0_math_probe(U variant,U all) {
 if(variant>=VariantCount || !m0_math_tables)return 0;
 prepare(variant);setup(variant,1,all!=0);dispatch(1);return collect(1,variant,all!=0);
}
extern "C" __attribute__((noipa)) U m0_math_pair_probe(U variant,U all) {
 if(variant>=VariantCount || !m0_math_tables)return 0;
 prepare(variant);setup(variant,2,all!=0);
 const bool accepted=dispatch(2);return accepted && collect(2,variant,all!=0);
}
namespace {
constexpr unsigned Cases=32,Rounds=6,Repeats=4;
struct Row {U available,ok,prep_us[Rounds],compute_us[Rounds],groups,bounded,pruned,zeros;};
struct CaseReport {U id,tensor,position,rows,columns,row_base,total_rows,head;Row variant[VariantCount];};
struct Report {U magic,version,before,hz,after,restored,count,rounds,repeats,cores,workspace_bytes,failed_case;CaseReport cases[Cases];};
Report report{};
const mk61_app_services* services=nullptr;
__attribute__((noipa)) void stage(unsigned number) {
 char text[48];const int n=mk61_app_snprintf(services,text,sizeof(text),"AI_MATRIX stage=%u\r\n",number);
 if(n>0)services->call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,text);
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
static_assert(sizeof(ClockState)==28 && sizeof(mk61ai::LinearBatch)==60,"Pinned resident ABI");
}
extern "C" U mk61_app_flow_step(mk61_app_flow* flow) {
 if(!mk61_app_flow_compatible(flow))return 0;
 services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_BUFFERS);
 if(!services)return 0;
 uintptr_t footer=footer_address;asm volatile("":"+r"(footer));
 for(unsigned i=0;i<10;++i)if(reinterpret_cast<volatile const U*>(footer)[i]!=footer_words[i])return 0;
 mk61_service_file app{};if(!services->call(MK61_SERVICE_FILE_ENTRY,0,flow->current.file_id,0,&app))return 0;
 U header[4];if(!read("MATHCASE.BIN",header,0,sizeof(header)) || header[0]!=0x4d434e31 || header[1]!=1 || !header[2] || header[2]>Cases)return 0;
 mk61_service_buffer workspace{};
 report.workspace_bytes=(MaxGroups+2)*sizeof(mk61ai_lut8x32);
 if(!mk61_app_buffer_acquire(services,report.workspace_bytes,MK61_BUFFER_DIRECT,&workspace))return 0;
 bool ok=mk61_app_buffer_call(services,MK61_BUFFER_INFO,&workspace) && workspace.storage==MK61_BUFFER_SRAM && workspace.data;
 m0_math_tables=reinterpret_cast<mk61ai_lut8x32*>(workspace.data);
 reinterpret_cast<void(*)()>(math_initialize_address)();
 report.magic=0x4d425431;report.version=1;report.count=header[2];report.rounds=Rounds;report.repeats=Repeats;report.cores=2;report.failed_case=~0U;
 report.before=reinterpret_cast<U(*)()>(clock_hz_address)();ClockState clock;
 const U setup_record[]={0x4d535431,1,report.before,report.workspace_bytes};
 mk61_service_write trace{"SETUP.BIN",reinterpret_cast<const std::uint8_t*>(setup_record),sizeof(setup_record),MK61_SERVICE_INVALID_ID};
 ok=services->call(MK61_SERVICE_FILE_WRITE,app.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&trace) && ok;
 stage(1);
 // Freeze through the same host gate as normal AI. Suspending only the
 // worker's frame queue lets NativeHost::pump call color_flush forever:
 // PRESENT returns BUSY while frames are suspended, then waits via pump.
 reinterpret_cast<void(*)(bool)>(render_gate_address)(false);stage(2);
 ok=ok && report.before==125000000 && reinterpret_cast<bool(*)(unsigned,ClockState*)>(clock_begin_address)(270,&clock);
 report.hz=reinterpret_cast<U(*)()>(clock_hz_address)();ok=ok && report.hz==270000000;
 stage(3);const U warm=micros();while(ok && micros()-warm<500000)mk61_api->service();
 U offset=16;
 for(unsigned index=0;ok && index<report.count;++index) {
  report.failed_case=index;
  if(offset>header[3] || sizeof(m0_math_header)>header[3]-offset || !read("MATHCASE.BIN",m0_math_header,offset,sizeof(m0_math_header))){ok=false;break;}
  offset+=sizeof(m0_math_header);
  const U bytes=m0_math_header[4]+m0_math_header[5]*8+m0_math_header[11]*2+m0_math_header[12]+m0_math_header[13]+m0_math_header[3]*4;
  if(bytes>sizeof(m0_math_payload) || offset>header[3] || bytes>header[3]-offset || !read("MATHCASE.BIN",m0_math_payload,offset,bytes) || !m0_math_load()){ok=false;break;}
  offset+=bytes;stage(4);auto& c=report.cases[index];
  c.id=m0_math_header[0];c.tensor=m0_math_header[1];c.position=m0_math_header[2];c.rows=m0_math_header[3];c.columns=m0_math_header[4];c.row_base=m0_math_header[6];c.total_rows=m0_math_header[7];c.head=m0_math_header[8];
  for(unsigned v=0;v<VariantCount;++v) {
   if(v>=PRUNE_HALF && !c.head)continue;
   c.variant[v].available=1;ok=m0_math_probe(v,0) && ok;stage(5);
   ok=m0_math_pair_probe(v,0) && ok;
   if(v>=PRUNE_HALF)ok=m0_math_pair_probe(v,1) && ok;
   c.variant[v].ok=ok;
  }
  // Every available method is validated before any timed round.
  for(unsigned round=0;ok && round<Rounds;++round)for(unsigned k=0;ok && k<VariantCount;++k) {
   const unsigned v=(round+k)%VariantCount;auto& r=c.variant[v];if(!r.available)continue;
   for(unsigned repeat=0;ok && repeat<Repeats;++repeat) {
    mk61_api->service();const U start=micros();prepare(v);const U prepared=micros();
    setup(v,2,false);const bool worker=dispatch(2);const U done=micros();
    r.prep_us[round]+=prepared-start;r.compute_us[round]+=done-prepared;
    ok=worker && collect(2,v,false);r.groups=m0_math_result.groups;r.bounded=m0_math_result.bounded;r.pruned=m0_math_result.pruned;r.zeros=m0_math_result.zeros;
   }
  }
  char progress[64];const int n=mk61_app_snprintf(services,progress,sizeof(progress),"AI_MATRIX case=%u/%u ok=%u\r\n",index+1,report.count,unsigned(ok));
  if(n>0)services->call(MK61_SERVICE_DEBUG_WRITE,unsigned(n),0,0,progress);
 }
 ok=ok && offset==header[3];
 if(ok)report.failed_case=~0U;
 // dispatch() already joins every accepted job before returning. The
 // resident join_compute is a consume-once operation: calling it on IDLE
 // waits forever, so cleanup must not perform a second unconditional join.
 stage(6);
 stage(60);
 report.restored=reinterpret_cast<bool(*)(ClockState*)>(clock_end_address)(&clock);
 stage(61);
 report.after=reinterpret_cast<U(*)()>(clock_hz_address)();
 stage(62);reinterpret_cast<void(*)(bool)>(render_gate_address)(true);stage(63);stage(7);
 ok=ok && report.restored && report.after==report.before;
 ok=mk61_app_buffer_release(services,workspace.handle) && ok;m0_math_tables=nullptr;
 mk61_service_write write{"MATHTEST.BIN",reinterpret_cast<const std::uint8_t*>(&report),unsigned(48+report.count*sizeof(CaseReport)),MK61_SERVICE_INVALID_ID};
 ok=services->call(MK61_SERVICE_FILE_WRITE,app.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&write) && ok;
 mk61_app_flow_exit(flow,ok?MK61_APP_OK:MK61_APP_RUNTIME_ERROR,MK61_FLOW_OK);return 1;
}
