#ifndef MK61_AI_ATTENTION_HPP
#define MK61_AI_ATTENTION_HPP
#include "mk61_ai_model.hpp"
namespace mk61ai {
// A job contains SRAM pointers only. A query head has one writer, and its
// reductions retain the original position/dimension order on either core.
struct AttentionBatch {
  const float *query=nullptr,*values=nullptr,*scores=nullptr;
  float *output=nullptr;
  unsigned rows=0,width=0;
  float scale=0,sum=0;
  static void run(void *raw);
  static void run_width32(void *raw);
};
void attention_pair(AttentionBatch (&jobs)[2],unsigned lanes,
                    const ComputeExecution &execution,ComputeMetrics &metrics);

struct SoftmaxJob {
  float *scores;
  unsigned length;
  float maximum;
  float sum = 0.0f;
  static void run(void *raw);
};
}
#endif
