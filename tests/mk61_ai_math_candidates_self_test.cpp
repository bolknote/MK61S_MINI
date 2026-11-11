#include "fixtures/mk61_ai_math_candidates.hpp"
#include "mk61_ai_math.hpp"
#include "worker_job_slot.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <fstream>
#include <limits>
#include <random>
#include <string>
#include <vector>
namespace mk61ai {void reference_linear_batch_sram(void*);void reference_linear_batch_flash(void*);}
using namespace ai_candidates;
namespace {
float add(float a,float b){return a+b;}float mul(float a,float b){return a*b;}
const Ops ops{add,mul};
std::mt19937 rng(0x3a17cafe);
struct Workspace {
 mk61ai_lut8x32 tables[MaxGroups]{};Scratch scratch{};
 Workspace(){scratch.tables=tables;}
};
std::uint32_t word(const std::vector<std::uint8_t>& data,unsigned at){std::uint32_t v;std::memcpy(&v,data.data()+at,4);return v;}
std::vector<std::uint8_t> package;
unsigned active_tensor=0,row_cursor=0,position=0,prompt_index=0;
Workspace work;
Best causal{-std::numeric_limits<float>::max(),~0U};
unsigned matrices=0,tiles=0,rows_checked=0,head_rows=0,pruned_half=0,pruned_last=0;
std::uint64_t quant_values=0,quant_zeros=0,zero_blocks=0,blocks=0,groups_total=0,bounds_total=0;
std::vector<std::uint8_t> fixtures;
unsigned fixture_count=0;
WorkerJobSlot mailbox;unsigned native_joins=0;
bool submit(void* context,void(*function)(void*)){return mailbox.submit(context,function);}
void join(){++native_joins;if(mailbox.queued())assert(mailbox.run());assert(mailbox.join());}
void worker_ownership() {
 unsigned result=0;
 auto calculate=[](void* raw){++*static_cast<unsigned*>(raw);};
 assert(!mailbox.join());
 {
  ComputeLease owner(submit,join);assert(owner.start(&result,calculate));
  assert(!owner.start(&result,calculate));assert(mailbox.run()); // DONE
  owner.join();assert(native_joins==1 && result==1);
  assert(!mailbox.join()); // Consumed DONE -> IDLE: raw join cannot succeed.
  owner.join();assert(native_joins==1); // Guard forbids the second native join.
 }
 assert(native_joins==1);
 {ComputeLease owner(submit,join);assert(owner.start(&result,calculate));}
 assert(native_joins==2 && result==2); // Early scope exit joins once.
 assert(mailbox.submit(&result,calculate));
 {ComputeLease refused(submit,join);assert(!refused.start(&result,calculate));refused.join();}
 assert(native_joins==2);assert(mailbox.run());assert(mailbox.join());
 std::puts("Worker ownership: DONE -> join -> IDLE; repeated/declined join suppressed PASS");
}
void append(const void* p,unsigned n){const auto* b=static_cast<const std::uint8_t*>(p);fixtures.insert(fixtures.end(),b,b+n);}
void evaluate(mk61ai::LinearBatch& batch,bool head,unsigned row_base,Best before) {
 assert(shape(batch));
 std::vector<float> expected(batch.rows),actual(batch.rows);
 auto ref=batch;ref.output=expected.data();mk61ai::reference_linear_batch_sram(&ref);
 assert(ref.status==mk61ai::ModelStatus::OK);
 const unsigned groups=batch.columns/32;
 std::vector<std::uint8_t> planes(batch.rows*batch.columns/2);
 for(unsigned r=0;r<batch.rows;++r)for(unsigned g=0;g<groups;++g)
  mk61ai_pack_q4_planes32(batch.weights+r*batch.columns/2+g*16,planes.data()+r*batch.columns/2+g*16);
 for(unsigned variant=0;variant<=ZERO_SKIP;++variant) {
  auto b=batch;b.output=actual.data();if(variant==LUT8_FULL || variant==LUT8_BOUNDED)b.weights=planes.data();
  mk61ai_lut8x32 one{};Scratch bounded=work.scratch;bounded.tables=&one;
  Stats stats{};assert(matrix(b,variant,variant==LUT8_BOUNDED?bounded:work.scratch,ops,stats));
  assert(!std::memcmp(expected.data(),actual.data(),batch.rows*4));
 }
 if(head) {
  std::vector<std::uint16_t> norms(batch.rows*groups);make_norms(batch,norms.data());assert(validate_norms(batch,norms.data()));
  Best full=before;for(unsigned r=0;r<batch.rows;++r)if(better(expected[r],row_base+r,full))full={expected[r],row_base+r};
  for(unsigned cut=1;cut<groups;++cut) {
   Best best=before;Stats stats{};
   assert(classify(batch,norms.data(),work.scratch,ops,row_base,cut,best,stats));
   assert(bits(best.score)==bits(full.score) && best.id==full.id);
   if(cut==groups/2){pruned_half+=stats.pruned;groups_total+=stats.groups;bounds_total+=stats.bounded;}
   if(cut==groups-1)pruned_last+=stats.pruned;
   Best all=before;Stats forced{};
   assert(classify(batch,norms.data(),work.scratch,ops,row_base,cut,all,forced,actual.data()));
   assert(!forced.pruned && !std::memcmp(expected.data(),actual.data(),batch.rows*4));
  }
  norms[0]^=1;assert(!validate_norms(batch,norms.data()));
 }
 rows_checked+=batch.rows;
}
void save_fixture(const mk61ai::LinearBatch& b,unsigned tensor,unsigned row_base,unsigned total,Best before) {
 const unsigned g=b.columns/32;
 std::vector<std::uint16_t> norms(b.rows*g);make_norms(b,norms.data());
 std::vector<std::uint8_t> planes(b.rows*b.columns/2);
 for(unsigned r=0;r<b.rows;++r)for(unsigned k=0;k<g;++k)
  mk61ai_pack_q4_planes32(b.weights+r*b.columns/2+k*16,planes.data()+r*b.columns/2+k*16);
 std::vector<float> output(b.rows);auto copy=b;copy.output=output.data();mk61ai::reference_linear_batch_sram(&copy);
 const unsigned header[]={fixture_count++,tensor,position,b.rows,b.columns,g,row_base,total,
                         unsigned(tensor==0),before.id,bits(before.score),b.rows*b.columns/2,b.rows*g*2,b.rows*g*2,0,0};
 append(header,sizeof(header));append(b.quant,b.columns);append(b.activation_scales,g*4);
 std::vector<std::int32_t> sums(g);
 for(unsigned k=0;k<g;++k)for(unsigned j=0;j<32;++j)sums[k]+=b.quant[k*32+j];
 append(sums.data(),g*4);append(b.weights,b.rows*b.columns/2);append(planes.data(),unsigned(planes.size()));
 append(b.scales,b.rows*g*2);append(norms.data(),unsigned(norms.size()*2));append(output.data(),b.rows*4);
}
void capture(void* raw) {
 auto& b=*static_cast<mk61ai::LinearBatch*>(raw);assert(b.arithmetic==mk61ai::Arithmetic::INT8 && shape(b));
 const unsigned table=word(package,60),at=table+active_tensor*32;
 const unsigned total=word(package,at),cols=word(package,at+4),data=word(package,at+16),scale=word(package,at+20);
 assert(cols==b.columns && row_cursor+b.rows<=total);
 assert(!std::memcmp(b.weights,package.data()+data+row_cursor*cols/2,b.rows*cols/2));
 assert(!std::memcmp(b.scales,package.data()+scale+row_cursor*cols/16,b.rows*cols/16));
 if(!row_cursor) {
  ++matrices;prepare_zero(b,work.scratch);prepare_lut(b,work.scratch);
  for(unsigned j=0;j<b.columns;++j){++quant_values;quant_zeros+=b.quant[j]==0;}
  for(unsigned j=0;j<b.columns;j+=8){bool zero=true;for(unsigned k=0;k<8;++k)zero=zero && b.quant[j+k]==0;++blocks;zero_blocks+=zero;}
  if(active_tensor==0)causal={-std::numeric_limits<float>::max(),~0U};
 }
 const bool head=active_tensor==0;evaluate(b,head,row_cursor,causal);
 const unsigned halfway=(total/2/28)*28,last=((total-1)/28)*28;
 const bool selected=prompt_index<2 && (position==0 || position==3) &&
     ((head && (row_cursor==0 || row_cursor==halfway || row_cursor==last)) ||
      ((active_tensor==3 || active_tensor==10 || active_tensor==12) && row_cursor==0));
 if(selected)save_fixture(b,active_tensor,row_cursor,total,causal);
 mk61ai::reference_linear_batch_sram(&b);assert(b.status==mk61ai::ModelStatus::OK);
 if(head){for(unsigned r=0;r<b.rows;++r)if(better(b.output[r],row_cursor+r,causal))causal={b.output[r],row_cursor+r};head_rows+=b.rows;}
 row_cursor+=b.rows;++tiles;
}
bool read(void*,std::uint32_t at,void* output,unsigned n) {
 if(at>package.size() || n>package.size()-at)return false;
 const unsigned table=word(package,60),count=2+11*word(package,16);
 if(n==32 && at>=table && at<table+count*32 && (at-table)%32==0){active_tensor=(at-table)/32;row_cursor=0;}
 std::memcpy(output,package.data()+at,n);return true;
}
void units() {
 Workspace local;std::vector<std::uint8_t> w(MaxRows*MaxColumns/2),scale(MaxRows*MaxGroups*2);
 std::int8_t x[MaxColumns];float a[MaxGroups],out[MaxRows];
 mk61ai::LinearBatch b{};b.arithmetic=mk61ai::Arithmetic::INT8;b.bits=4;b.grid=0;
 b.quant=x;b.weights=w.data();b.scales=scale.data();b.activation_scales=a;b.output=out;
 for(unsigned trial=0;trial<192;++trial) {
  b.columns=(1+rng()%MaxGroups)*32;b.rows=1+rng()%MaxRows;
  for(unsigned j=0;j<b.columns;++j)x[j]=trial<128 && (rng()%100)<(trial%8)*14?0:std::int8_t(rng());
  for(auto& q:w)q=std::uint8_t(rng());
  for(unsigned k=0;k<b.columns/32;++k)a[k]=trial%11==0?0:trial%13==0?0x1p-140f:float(1+rng()%127)*0x1p-12f;
  for(unsigned k=0;k<b.rows*b.columns/16;k+=2) {
   const unsigned h=rng()%0x7c00;scale[k]=std::uint8_t(h);scale[k+1]=std::uint8_t((h>>8)|((rng()&1)<<7));
  }
  prepare_zero(b,work.scratch);prepare_lut(b,work.scratch);
  const auto moments=work.scratch;prepare_bounds(b,work.scratch);
  assert(!std::memcmp(moments.squared,work.scratch.squared,sizeof(moments.squared)));
  assert(!std::memcmp(moments.absolute,work.scratch.absolute,sizeof(moments.absolute)));
  evaluate(b,true,100,{-std::numeric_limits<float>::max(),~0U});
  for(unsigned r=0;r<b.rows;++r)for(unsigned k=0;k<b.columns/32;++k) {
   const auto* p=b.weights+r*b.columns/2+16*k;const auto* q=x+32*k;
   std::int64_t dot=0;for(unsigned j=0;j<32;++j)dot+=(int((p[j/2]>>(4*(j&1)))&15)-8)*int(q[j]);
   assert(dot==mk61ai_dot_q4_a8_32(p,q));
   const unsigned bound=ceil_sqrt(unsigned(weight_square(p))*work.scratch.squared[k]);
   assert(std::uint64_t(dot<0?-dot:dot)<=bound);
  }
 }
 // Exhaustively check the exact square root's transitions plus wide extremes.
 for(unsigned root=0;root<=32768;++root)for(int delta=-1;delta<=1;++delta) {
  const std::int64_t n=std::int64_t(root)*root+delta;if(n<0 || n>0x40000000)continue;
  const auto got=ceil_sqrt(unsigned(n));assert(std::uint64_t(got)*got>=std::uint64_t(n));
  assert(!got || std::uint64_t(got-1)*(got-1)<std::uint64_t(n));
 }
 // All-zero ties keep the earliest token, even with an equal seed score.
 b.columns=128;b.rows=4;std::memset(x,0,sizeof(x));std::fill(a,a+MaxGroups,1.0f);
 std::fill(scale.begin(),scale.end(),0);prepare_zero(b,work.scratch);
 std::uint16_t norms[MaxRows*MaxGroups];make_norms(b,norms);
 Best best{0,200};Stats stats{};assert(classify(b,norms,work.scratch,ops,100,2,best,stats));assert(best.id==100);
 // A nonfinite suffix forbids a certificate; it cannot be hidden by pruning.
 scale[6]=0;scale[7]=0x7c;best={1,0};stats={};
 assert(!classify(b,norms,work.scratch,ops,100,2,best,stats));
 std::puts("Synthetic: exact dots, FP32 logits, all cut points, ties, malformed norms, nonfinite suffix and sqrt boundaries PASS");
}
} // namespace
namespace mk61ai {void linear_batch_sram(void* p){capture(p);}void linear_batch_flash(void* p){capture(p);}}
int main(int argc,char** argv) {
 assert(argc==3);worker_ownership();units();rows_checked=pruned_half=pruned_last=0;groups_total=bounds_total=0;
 std::ifstream in(argv[1],std::ios::binary);package.assign(std::istreambuf_iterator<char>(in),{});assert(package.size()>128);
 mk61ai::Model model;assert(model.open({nullptr,unsigned(package.size()),read})==mk61ai::ModelStatus::OK);
 mk61ai::ComputeExecution e{};e.kernel=mk61ai::LinearKernel::SRAM;e.tile_rows=28;e.prefetch=false;model.execution(e);
 std::vector<std::uint64_t> workspace((model.workspace_bytes()+7)/8);std::vector<std::uint8_t> cache(model.cache_bytes());
 auto cr=[](void* p,std::uint32_t at,void* out,unsigned n){auto& c=*static_cast<std::vector<std::uint8_t>*>(p);if(at>c.size() || n>c.size()-at)return false;std::memcpy(out,c.data()+at,n);return true;};
 auto cw=[](void* p,std::uint32_t at,const void* out,unsigned n){auto& c=*static_cast<std::vector<std::uint8_t>*>(p);if(at>c.size() || n>c.size()-at)return false;std::memcpy(c.data()+at,out,n);return true;};
 assert(model.bind(workspace.data(),model.workspace_bytes(),{&cache,unsigned(cache.size()),cr,cw})==mk61ai::ModelStatus::OK);
 const char* prompts[]={"Hello! How are you?","Задача: сложи R0 и R1.","Проверь программу и вычисли синус 22 градусов.","Write a short calculator program."};
 for(prompt_index=0;prompt_index<4;++prompt_index) {
  model.reset();std::uint16_t tokens[128],best;unsigned count=0;assert(model.encode(prompts[prompt_index],tokens,128,count,true)==mk61ai::ModelStatus::OK);
  count=std::min(count,8U);
  for(position=0;position<count;++position)assert(model.forward(tokens[position],true,best,nullptr,nullptr,mk61ai::Arithmetic::INT8)==mk61ai::ModelStatus::OK);
 }
 const std::string dir=argv[2];std::ofstream data(dir+"/MATHCASE.BIN",std::ios::binary);
 const unsigned header[]={0x4d434e31,1,fixture_count,unsigned(fixtures.size()+16)};data.write(reinterpret_cast<const char*>(header),16);data.write(reinterpret_cast<const char*>(fixtures.data()),fixtures.size());
 FILE* report=std::fopen((dir+"/host-results.json").c_str(),"w");assert(report);
 std::fprintf(report,"{\n\"status\":\"PASS\",\"matrix_calls\":%u,\"tiles\":%u,\"rows_bit_exact\":%u,\"classifier_rows\":%u,\"quant_values\":%llu,\"quant_zeros\":%llu,\"blocks8\":%llu,\"zero_blocks8\":%llu,\"pruned_half\":%u,\"pruned_last\":%u,\"groups_evaluated_half\":%llu,\"bound_groups_half\":%llu,\"hardware_cases\":%u,\"physical_io\":false\n}\n",matrices,tiles,rows_checked,head_rows,(unsigned long long)quant_values,(unsigned long long)quant_zeros,(unsigned long long)blocks,(unsigned long long)zero_blocks,pruned_half,pruned_last,(unsigned long long)groups_total,(unsigned long long)bounds_total,fixture_count);
 std::fclose(report);std::printf("Real model: %u bit-exact rows, %u classifier rows, %u/%u pruned; %u hardware cases prepared\n",rows_checked,head_rows,pruned_half,pruned_last,fixture_count);
}
