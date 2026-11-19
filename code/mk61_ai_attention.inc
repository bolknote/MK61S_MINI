#if defined(PICO_ON_DEVICE)
#define MK61_ATTENTION_CODE __attribute__((section(".ai_attention_extension"),noinline))
#define MK61_ATTENTION_FAST __attribute__((section(".ai_attention_fast_extension"),noinline,optimize("O2")))
#else
#define MK61_ATTENTION_CODE
#define MK61_ATTENTION_FAST
#endif

MK61_ATTENTION_CODE void SoftmaxJob::run(void *raw) {
  auto &head = *static_cast<SoftmaxJob *>(raw);
  for (unsigned i = 0; i < head.length; ++i) {
    float &score = head.scores[i];
    score = math::exp(math::sub(score, head.maximum));
    head.sum = math::add(head.sum, score);
  }
}

MK61_ATTENTION_CODE void AttentionBatch::run(void *raw) {
  auto &b=*static_cast<AttentionBatch*>(raw);
  if(b.query) {
    for(unsigned t=0;t<b.rows;++t) {
      float dot=0;
      for(unsigned j=0;j<b.width;++j)
        dot=exact_fp32::sum(dot,exact_fp32::product(b.query[j],b.values[t*b.width+j]));
      b.output[t]=exact_fp32::product(dot,b.scale);
    }
  } else {
    for(unsigned t=0;t<b.rows;++t) {
      const float factor=math::div(b.scores[t],b.sum);
      for(unsigned j=0;j<b.width;++j)
        b.output[j]=exact_fp32::sum(b.output[j],exact_fp32::product(factor,b.values[t*b.width+j]));
    }
  }
}

MK61_ATTENTION_FAST void AttentionBatch::run_width32(void *raw) {
  auto &b=*static_cast<AttentionBatch*>(raw);
  if(b.query) {
    for(unsigned t=0;t<b.rows;++t) {
      float dot=0;
      const auto *row=b.values+t*32;
      for(unsigned j=0;j<32;++j)
        dot=exact_fp32::attention_sum(dot,exact_fp32::attention_product(exact_fp32::ProductOperand(b.query[j]),row[j]));
      b.output[t]=exact_fp32::product(dot,b.scale);
    }
  } else {
    for(unsigned t=0;t<b.rows;++t) {
      const exact_fp32::ProductOperand factor(math::div(b.scores[t],b.sum));
      const auto *row=b.values+t*32;
      for(unsigned j=0;j<32;++j)
        b.output[j]=exact_fp32::attention_sum(b.output[j],exact_fp32::attention_product(factor,row[j]));
    }
  }
}

MK61_ATTENTION_CODE void attention_pair(AttentionBatch (&jobs)[2],unsigned lanes,
                           const ComputeExecution &execution,ComputeMetrics &metrics) {
  const auto kernel=jobs[0].width==32 &&
      (execution.attention_kernel==AttentionKernel::BOTH ||
       (jobs[0].query && execution.attention_kernel==AttentionKernel::QUERY) ||
       (!jobs[0].query && execution.attention_kernel==AttentionKernel::WEIGHTED)) ?
      AttentionBatch::run_width32 : AttentionBatch::run;
  const bool submitted=lanes==2 && jobs[0].rows>=4 && execution.parallel_attention &&
      execution.submit && execution.join &&
      execution.submit(execution.context,kernel,&jobs[1]);
  if(submitted) ++metrics.attention_worker_jobs;
  kernel(&jobs[0]);
  if(lanes==2) {
    if(submitted) execution.join(execution.context);
    else kernel(&jobs[1]);
  }
}

#undef MK61_ATTENTION_FAST
#undef MK61_ATTENTION_CODE
