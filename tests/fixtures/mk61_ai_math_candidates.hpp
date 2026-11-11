#ifndef MK61_AI_MATH_CANDIDATES_HPP
#define MK61_AI_MATH_CANDIDATES_HPP
// Experimental kernels only. Production dispatch and model formats are intact.
#include "mk61_ai_linear.hpp"
#include "mk61_ai_kernels.h"
#if __STDC_HOSTED__
#include "mk61_ai_half_product.hpp"
#else
#include "math-candidate-half.hpp"
#endif
#include <cstdint>
#include <cstring>
namespace ai_candidates {
constexpr unsigned MaxColumns=384,MaxRows=28,MaxGroups=MaxColumns/32;
using Binary=float(*)(float,float);
struct Ops {Binary add,mul;};
inline std::uint32_t bits(float x){std::uint32_t u;__builtin_memcpy(&u,&x,4);return u;}
inline float value(std::uint32_t u){float x;__builtin_memcpy(&x,&u,4);return x;}
inline bool finite(float x){return (bits(x)&0x7fffffffU)<0x7f800000U;}
struct ZeroGroup {std::uint8_t count,index[32];};
struct Scratch {
 mk61ai_lut8x32* tables=nullptr;
 ZeroGroup zeros[MaxGroups]{};
 std::uint32_t squared[MaxGroups]{},absolute[MaxGroups]{};
};
struct Stats {unsigned groups=0,bounded=0,pruned=0,zeros=0;};
struct Best {float score;unsigned id;};
enum Variant {DIRECT,LUT8_FULL,LUT8_BOUNDED,ZERO_SKIP,PRUNE_HALF,PRUNE_LAST,VariantCount};
// The resident mailbox's join consumes DONE once. Never call its blocking
// wrapper unless this scope owns an accepted, not-yet-joined submission.
class ComputeLease {
 using Submit=bool(*)(void*,void(*)(void*));using Join=void(*)();
 Submit submit_;Join join_;bool pending_=false;
public:
 ComputeLease(Submit submit,Join join):submit_(submit),join_(join){}
 ComputeLease(const ComputeLease&)=delete;ComputeLease& operator=(const ComputeLease&)=delete;
 ~ComputeLease(){join();}
 bool start(void* context,void(*function)(void*)) {
  if(pending_)return false;
  pending_=submit_(context,function);return pending_;
 }
 void join(){if(pending_){join_();pending_=false;}}
};
inline bool shape(const mk61ai::LinearBatch& b) {
 return b.bits==4 && b.grid==0 && b.columns && b.columns<=MaxColumns && !(b.columns%32)
     && b.rows && b.rows<=MaxRows && b.quant && b.activation_scales && b.weights && b.scales;
}
inline void prepare_zero(const mk61ai::LinearBatch& b,Scratch& s) {
 for(unsigned g=0;g<b.columns/32;++g) {
  auto& z=s.zeros[g];z.count=0;s.squared[g]=s.absolute[g]=0;
  for(unsigned j=0;j<32;++j) {
   const int x=b.quant[g*32+j];
   if(x)z.index[z.count++]=std::uint8_t(j);
   s.squared[g]+=unsigned(x*x);s.absolute[g]+=unsigned(x<0?-x:x);
  }
 }
}
inline void prepare_lut(const mk61ai::LinearBatch& b,Scratch& s) {
 for(unsigned g=0;g<b.columns/32;++g)mk61ai_prepare_lut8x32(b.quant+g*32,s.tables+g);
}
inline void prepare_bounds(const mk61ai::LinearBatch& b,Scratch& s) {
 for(unsigned g=0;g<b.columns/32;++g) {
  s.squared[g]=s.absolute[g]=0;
  for(unsigned j=0;j<32;++j) {
   const int x=b.quant[g*32+j];s.squared[g]+=unsigned(x*x);s.absolute[g]+=unsigned(x<0?-x:x);
  }
 }
}
inline std::int32_t zero_dot(const std::uint8_t* w,const std::int8_t* x,const ZeroGroup& p) {
 std::int32_t result=0;
 for(unsigned k=0;k<p.count;++k) {
  const unsigned j=p.index[k];const int q=int((w[j/2]>>(4*(j&1)))&15)-8;
  result+=q*int(x[j]);
 }
 return result;
}
inline std::uint16_t half_bits(const mk61ai::LinearBatch& b,unsigned r,unsigned g) {
 const auto* p=b.scales+2*(r*(b.columns/32)+g);return std::uint16_t(p[0]|unsigned(p[1])<<8);
}
inline float term(const mk61ai::LinearBatch& b,unsigned r,unsigned g,int dot,const Ops& ops) {
 return ops.mul(mk61ai::half_scaled_q4_dot(dot,half_bits(b,r,g)),b.activation_scales[g]);
}
inline bool matrix(mk61ai::LinearBatch& b,unsigned variant,Scratch& scratch,const Ops& ops,Stats& stats) {
 if(!shape(b) || !b.output || variant>ZERO_SKIP)return false;
 const unsigned groups=b.columns/32;
 for(unsigned r=0;r<b.rows;++r)b.output[r]=0;
 if(variant==LUT8_BOUNDED) {
  // The same2048-byte table is rebuilt once per group/tile. Each output
  // row still accumulates groups in exactly the original FP32 order.
  for(unsigned g=0;g<groups;++g) {
   mk61ai_prepare_lut8x32(b.quant+32*g,scratch.tables);
   for(unsigned r=0;r<b.rows;++r) {
    const auto* w=b.weights+r*b.columns/2+g*16;
    const int dot=mk61ai_dot_lut8_q4_a8_32(w,scratch.tables);
    b.output[r]=ops.add(b.output[r],term(b,r,g,dot,ops));++stats.groups;
   }
  }
 } else {
  for(unsigned r=0;r<b.rows;++r)for(unsigned g=0;g<groups;++g) {
   const auto* w=b.weights+r*b.columns/2+g*16;const auto* x=b.quant+g*32;
   const int dot=variant==LUT8_FULL?mk61ai_dot_lut8_q4_a8_32(w,scratch.tables+g):
       variant==ZERO_SKIP?zero_dot(w,x,scratch.zeros[g]):mk61ai_dot_q4_a8_32(w,x);
   if(variant==ZERO_SKIP)stats.zeros+=32-scratch.zeros[g].count;
   b.output[r]=ops.add(b.output[r],term(b,r,g,dot,ops));++stats.groups;
  }
 }
 for(unsigned r=0;r<b.rows;++r)if(!finite(b.output[r]))return false;
 return true;
}
inline std::uint16_t weight_square(const std::uint8_t* w) {
 unsigned sum=0;
 for(unsigned j=0;j<32;++j){const int q=int((w[j/2]>>(4*(j&1)))&15)-8;sum+=unsigned(q*q);}
 return std::uint16_t(sum);
}
inline void make_norms(const mk61ai::LinearBatch& b,std::uint16_t* norms) {
 for(unsigned r=0;r<b.rows;++r)for(unsigned g=0;g<b.columns/32;++g)
  norms[r*(b.columns/32)+g]=weight_square(b.weights+r*b.columns/2+g*16);
}
inline bool validate_norms(const mk61ai::LinearBatch& b,const std::uint16_t* norms) {
 for(unsigned r=0;r<b.rows;++r)for(unsigned g=0;g<b.columns/32;++g)
  if(norms[r*(b.columns/32)+g]!=weight_square(b.weights+r*b.columns/2+g*16))return false;
 return true;
}
inline std::uint32_t ceil_sqrt(std::uint32_t n) {
 const auto original=n;std::uint32_t root=0,bit=1U<<30;
 while(bit>n)bit>>=2;
 while(bit) {
  if(n>=root+bit){n-=root+bit;root=(root>>1)+bit;}else root>>=1;
  bit>>=2;
 }
 return root+std::uint32_t(root*root!=original);
}
inline bool better(float score,unsigned id,const Best& best) {
 return score>best.score || (score==best.score && id<best.id);
}
inline bool classify(const mk61ai::LinearBatch& b,const std::uint16_t* norms,
                     Scratch& s,const Ops& ops,unsigned row_base,unsigned cut,
                     Best& best,Stats& stats,float* all_logits=nullptr,
                     std::uint32_t* skipped=nullptr) {
 if(!shape(b) || !norms || cut>=b.columns/32)return false;
 const unsigned groups=b.columns/32;
 for(unsigned r=0;r<b.rows;++r) {
  float sum=0;bool rejected=false;
  if(skipped)skipped[r]=0;
  for(unsigned g=0;g<groups;++g) {
   const auto* w=b.weights+r*b.columns/2+g*16;
   const int dot=mk61ai_dot_q4_a8_32(w,b.quant+g*32);
   sum=ops.add(sum,term(b,r,g,dot,ops));++stats.groups;
   if(!finite(sum))return false;
   if(!all_logits && g+1==cut) {
    float upper=sum;bool certified=true;
    for(unsigned k=g+1;k<groups;++k) {
     const unsigned ws=norms[r*groups+k];
     if(ws>2048 || s.squared[k]>524288){certified=false;break;}
     // Integer Cauchy-Schwarz bound: both factors and their product fit
     // uint32. The ceil is exact; no approximate floating-point norm.
     unsigned bound=ceil_sqrt(ws*s.squared[k]);
     const unsigned l1=8*s.absolute[k];if(bound>l1)bound=l1;
     const auto h=std::uint16_t(half_bits(b,r,k)&0x7fff);
     const float scale=value(bits(b.activation_scales[k])&0x7fffffffU);
     if((h>>10)==31 || !finite(scale)){certified=false;break;}
     const float bound_term=ops.mul(mk61ai::half_scaled_q4_dot(int(bound),h),scale);
     upper=ops.add(upper,bound_term);++stats.bounded;
     if(!finite(upper)){certified=false;break;}
    }
    // RNE is monotone. Apply every remaining FP32 addition in its original
    // order to positive term bounds: this encloses the final FP32 result
    // without a real-arithmetic approximation or a guessed error epsilon.
    const unsigned id=row_base+r;
    if(certified && (upper<best.score || (upper==best.score && id>best.id))) {
     rejected=true;++stats.pruned;if(skipped)skipped[r]=1;break;
    }
   }
  }
  if(!rejected) {
   if(all_logits)all_logits[r]=sum;
   if(better(sum,row_base+r,best))best={sum,row_base+r};
  }
 }
 return true;
}
} // namespace ai_candidates
#endif
