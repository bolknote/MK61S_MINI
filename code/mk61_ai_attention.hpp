#ifndef MK61_AI_ATTENTION_HPP
#define MK61_AI_ATTENTION_HPP
#include "mk61_ai_model.hpp"
#if defined(PICO_ON_DEVICE)
#define MK61_ATTENTION_CODE __attribute__((section(".ai_attention_extension"),noinline))
#else
#define MK61_ATTENTION_CODE
#endif
namespace mk61ai {
// A job contains SRAM pointers only. A query head has one writer, and its
// reductions retain the original position/dimension order on either core.
struct AttentionBatch {
  const float *query=nullptr,*values=nullptr,*scores=nullptr;
  float *output=nullptr;
  unsigned rows=0,width=0;
  float scale=0,sum=0;
  MK61_ATTENTION_CODE static void run(void *raw) {
    auto &b=*static_cast<AttentionBatch*>(raw);
    if(b.query) {
      for(unsigned t=0;t<b.rows;++t) {
        float dot=0;
        for(unsigned j=0;j<b.width;++j) dot+=b.query[j]*b.values[t*b.width+j];
        b.output[t]=dot*b.scale;
      }
    } else {
      for(unsigned t=0;t<b.rows;++t) {
        const float factor=b.scores[t]/b.sum;
        for(unsigned j=0;j<b.width;++j) b.output[j]+=factor*b.values[t*b.width+j];
      }
    }
  }
};
MK61_ATTENTION_CODE inline void attention_pair(AttentionBatch (&jobs)[2],unsigned lanes,
                           const ComputeExecution &execution,ComputeMetrics &metrics) {
  const bool submitted=lanes==2 && jobs[0].rows>=4 && execution.parallel_attention &&
      execution.submit && execution.join &&
      execution.submit(execution.context,AttentionBatch::run,&jobs[1]);
  if(submitted) ++metrics.attention_worker_jobs;
  AttentionBatch::run(&jobs[0]);
  if(lanes==2) {
    if(submitted) execution.join(execution.context);
    else AttentionBatch::run(&jobs[1]);
  }
}
}
#undef MK61_ATTENTION_CODE
#endif
