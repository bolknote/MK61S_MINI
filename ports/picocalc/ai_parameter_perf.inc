AI_COLD_CODE unsigned UI::parameter_perf(const char *directory, bool overlap_only, bool attention_trial) {
  using namespace mk61ai::long_bench;
  constexpr unsigned rounds = 4;
  constexpr unsigned lengths[] = {128, 256, 512};
  constexpr unsigned seed_rows = 16, row_bytes = 512;
  if (!ensure_model() || !parameter_cache) return 3;
  const auto &cfg = model.config();
  if (cfg.layers != 10 || cfg.hidden != 128 || cfg.head_dim != 32 ||
      cfg.kv_heads * cfg.head_dim * 8 != row_bytes || cfg.context < 512)
    return 3;

  std::uint16_t ids[64]{};
  unsigned count = 0, used = 0;
  char path[128];
  std::snprintf(path, sizeof(path), "%s/PERF.REF", directory);
  std::uint8_t reference[52]{};
  if (!files::read(path, reference, sizeof(reference), used) || used != sizeof(reference) ||
      word(reference, 0) != 0x31524941U || word(reference, 4) != 4 ||
      word(reference, 8) != 2 || word(reference, 12) != 2 || word(reference, 16) != cfg.vocab ||
      model.encode(prompt, ids, 64, count) != ModelStatus::OK || count < 2) return 3;
  const std::uint16_t tokens[] = {ids[0], ids[1], std::uint16_t(word(reference, 28)),
                                 std::uint16_t(word(reference, 36))};

  struct Sample {
    u32 forward_us = 0, softmax_jobs = 0;
    u32 layers_us = 0, classifier_us = 0, service_us = 0;
    u32 read_us = 0, matmul_us = 0, wait_us = 0;
    u32 xip_accesses = 0, xip_misses = 0, prefetches = 0, prefetched_bytes = 0;
  };
  struct LongCase {
    u32 context = 0, token = 0, logits = 0, kv = 0;
    Sample samples[2][rounds]{};
  };
  struct Result {
    u32 magic = 0x31444152U, bytes = sizeof(Result), ok = 0, stage = 0;
    u32 hz = 0, divider256 = 0, restored_hz = 0, status = 0;
    u32 cache_bytes = 0, heap_peak = 0, heap_capacity = 0, verified_steps = 0;
    u32 short_tokens[4]{}, short_checksums[4]{};
    Sample short_samples[2][rounds]{};
    LongCase long_cases[3]{};
  };
  struct AttentionSample {
    u32 attention_us = 0, io_us = 0;
  };
  struct PrefillSample {
    u32 us = 0, kv_bytes = 0, kv_reads = 0, weight_prefetch_bytes = 0;
    u32 weight_io_us = 0, softmax_jobs = 0;
  };
  struct Trial {
    u32 magic = 0x31545441U, stage = 0, kernel = 0, variants = 1;
    u32 micro_us[2][2][rounds]{}; // QK / PV, reference / candidate
    u32 micro_matches = 0;
    u32 prefill_start = 384, prefill_count = 8, extra_bytes = 0;
    PrefillSample prefill[2][2]{};
    u32 prompt_digest[8]{}, prompt_kv[8]{};
    u32 psram_burst = 0;
  };
  struct {
    Result timings;
    AttentionSample attention[4][2][rounds]; // Short, then 128, 256 and 512.
    Trial trial;
  } report_data;
  static_assert(sizeof(Result) == 1664);
  static_assert(offsetof(decltype(report_data),trial)==1920 && sizeof(Trial)==260);
  auto &report = report_data.timings;
  auto &trial=report_data.trial;
  report.bytes = attention_trial ? sizeof(report_data) :
      overlap_only ? offsetof(decltype(report_data),trial) : sizeof(report);
  for (unsigned i = 0; i < 3; ++i) report.long_cases[i].context = lengths[i];

  char result_path[128];
  const int path_length = std::snprintf(result_path, sizeof(result_path), "%s/READ.BIN", directory);
  if (path_length < 0 || unsigned(path_length) >= sizeof(result_path) ||
      !files::write(result_path, reinterpret_cast<const u8 *>(&report_data), report.bytes)) return 3;

  std::snprintf(path, sizeof(path), "%s/KVSEED.BIN", directory);
  std::uint8_t seed[16];
  if (!files::read_range(path, 0, seed, sizeof(seed), used) || used != sizeof(seed) ||
      word(seed, 0) != 0x31564b41U || word(seed, 4) != seed_rows ||
      word(seed, 8) != cfg.layers * seed_rows * row_bytes) return 3;
  std::uint32_t seed_hash = 2166136261U;
  {
    constexpr unsigned block_bytes = seed_rows * row_bytes;
    std::unique_ptr<u8[]> block(new (std::nothrow) u8[block_bytes]);
    if (!block) return 3;
    for (unsigned layer = 0; layer < cfg.layers; ++layer) {
      if (!files::read_range(path, sizeof(seed) + layer * block_bytes, block.get(), block_bytes, used) ||
          used != block_bytes) return 3;
      seed_hash = hash(seed_hash, block.get(), block_bytes);
      for (unsigned position = 0; position < 511; position += seed_rows) {
        const auto bytes = std::min(seed_rows, 511U - position) * row_bytes;
        if (!cache.write((layer * cfg.context + position) * row_bytes, block.get(), bytes) || !pump()) return 3;
      }
    }
  }
  if (seed_hash != word(seed, 12)) return 3;

  linear_kernel = LinearKernel::SRAM;
  arithmetic = Arithmetic::INT8;
  dual_core = freeze_screen = double_buffer = true;
  filter_head = m3_core = false;
  configure_execution();
  const auto production = model.execution();
  const auto cache_bytes = model.parameter_cache_bytes();
  report.cache_bytes = cache_bytes;
  ModelStatus status = ModelStatus::OK;
  ai_clock::State clock;
  bool ok = ai_clock::begin(270, clock);
  const auto ram_before = psram::statistics();
  const auto io_before = io_worker::statistics();
  report.hz = ai_clock::hz();
  cancel = false;
  if(ok && attention_trial) {
    // The old flag uses a different 16-byte PIO program at the same SCK.
    // Clock/divider alone cannot distinguish it from the release profile.
    ok=psram::diagnostic_read_burst(64) &&
       psram::diagnostic_read_clock(ai_psram_read_clock::default_burst_divider);
    if(ok)trial.psram_burst=64;
  }

  // Use saved K/V data and the same worker as the model. Do not run the
  // candidate on the full decode when neither inner loop is faster.
  auto micro=[&] {
    trial.stage=1;
    constexpr unsigned size=16,width=32,repetitions=24;
    struct Matrix { float elements[size*width]; };
    std::unique_ptr<Matrix> matrix(new (std::nothrow) Matrix);
    if(!matrix)return false;
    float query[2][width],scores[2][size],values[2][width],expected[2][width];
    for(unsigned lane=0;lane<2;++lane)
      if(!cache.read(128+lane*row_bytes,query[lane],width*sizeof(float))) return false;
    for(unsigned lane=0;lane<2;++lane) for(unsigned i=0;i<size;++i)
      scores[lane][i]=0.25f+float((3*i+lane)%size)*0.0625f;
    for(unsigned kind=0;kind<2;++kind) {
      for(unsigned row=0;row<size;++row)
        if(!cache.read(row*row_bytes+kind*256,matrix->elements+row*width,width*sizeof(float))) return false;
      const unsigned output_count=kind?width:size;
      for(unsigned round=0;round<rounds;++round) {
        for(unsigned side=0;side<2;++side) {
          const unsigned variant=side^(round&1);
          auto e=production;
          e.attention_kernel=variant?AttentionKernel::BOTH:AttentionKernel::REFERENCE;
          auto &time=trial.micro_us[kind][variant][round];
          for(unsigned n=0;n<repetitions;++n) {
            for(unsigned lane=0;lane<2;++lane)
              std::memcpy(values[lane],query[lane],sizeof(values[lane]));
            AttentionBatch jobs[]{
              {kind?nullptr:query[0],matrix->elements,kind?scores[0]:nullptr,values[0],size,width,0.176776692f,256.0f},
              {kind?nullptr:query[1],matrix->elements,kind?scores[1]:nullptr,values[1],size,width,0.176776692f,304.0f}};
            if(!pump())return false;
            ComputeMetrics metrics{};
            const auto start=call(MK61_SERVICE_MICROS);
            attention_pair(jobs,2,e,metrics);
            time+=call(MK61_SERVICE_MICROS)-start;
            if(metrics.attention_worker_jobs!=1) return false;
            for(unsigned lane=0;lane<2;++lane) {
              const unsigned bytes=output_count*sizeof(float);
              if(!n && !side)std::memcpy(expected[lane],values[lane],bytes);
              else if(std::memcmp(expected[lane],values[lane],bytes))return false;
              else if(side) trial.micro_matches+=output_count;
            }
          }
        }
      }
    }
    auto wins=[&](unsigned kind) {
      u32 a[rounds],b[rounds];
      std::copy_n(trial.micro_us[kind][0],rounds,a);
      std::copy_n(trial.micro_us[kind][1],rounds,b);
      std::sort(a,a+rounds);std::sort(b,b+rounds);
      return 100ULL*(b[1]+b[2])<=95ULL*(a[1]+a[2]);
    };
    const bool qk=wins(0),pv=wins(1);
    trial.kernel=unsigned(qk?(pv?AttentionKernel::BOTH:AttentionKernel::QUERY):
                            (pv?AttentionKernel::WEIGHTED:AttentionKernel::REFERENCE));
    trial.variants=trial.kernel?2:1;
    trial.stage=2;
    return true;
  };
  auto select_mode = [&](bool enabled) {
    auto execution = production;
    execution.parallel_softmax = overlap_only || enabled;
    if (overlap_only) execution.overlap_kv = attention_trial || enabled;
    if (attention_trial && enabled) execution.attention_kernel=AttentionKernel(trial.kernel);
    model.execution(execution);
    if (!overlap_only && !enabled) {
      model.clear_parameter_cache();
      return true;
    }
    status = model.cache_parameters(parameter_cache.get(), cache_bytes);
    return status == ModelStatus::OK;
  };
  auto step = [&](std::uint16_t id, bool output, std::uint16_t &next, Sample &sample,
                  AttentionSample &attention) {
    const auto hits_before = xip_ctrl_hw->ctr_hit;
    const auto accesses_before = xip_ctrl_hw->ctr_acc;
    const auto started = call(MK61_SERVICE_MICROS);
    status = model.forward(id, output, next, service, this, Arithmetic::INT8);
    sample.forward_us += call(MK61_SERVICE_MICROS) - started;
    const auto accesses = xip_ctrl_hw->ctr_acc - accesses_before;
    const auto hits = xip_ctrl_hw->ctr_hit - hits_before;
    sample.xip_accesses += accesses;
    sample.xip_misses += accesses - hits;
    const auto &metrics = model.compute_metrics();
    sample.softmax_jobs += metrics.softmax_worker_jobs;
    sample.layers_us += metrics.layers_us;
    sample.classifier_us += metrics.classifier_us;
    sample.service_us += metrics.service_us;
    sample.read_us += metrics.read_us;
    sample.matmul_us += metrics.matmul_us;
    sample.wait_us += metrics.wait_us;
    sample.prefetches += metrics.prefetches;
    sample.prefetched_bytes += metrics.prefetched_bytes;
    attention.attention_us += metrics.attention_us;
    attention.io_us += metrics.attention_io_us;
    return status == ModelStatus::OK;
  };
  auto kv_hash = [&](unsigned position, u32 &result) {
    u8 row[row_bytes];
    result = 2166136261U;
    for (unsigned layer = 0; layer < cfg.layers; ++layer) {
      if (!cache.read((layer * cfg.context + position) * row_bytes, row, sizeof(row))) return false;
      result = hash(result, row, sizeof(row));
    }
    return true;
  };
  auto measure_long = [&](unsigned index, unsigned mode, unsigned round) {
    auto &result = report.long_cases[index];
    auto &sample = result.samples[mode][round];
    auto &attention = report_data.attention[index + 1][mode][round];
    const unsigned position = result.context - 1;
    std::uint16_t next = 0;
    u32 row_hash = 0;
    if (!select_mode(mode != 0) || !model.diagnostic_position(position) ||
        !step(input(ids, count, position), true, next, sample, attention) || !kv_hash(position, row_hash)) return false;
    const auto digest = model.compute_metrics().checksum;
    if (!mode && !round) {
      result.token = next;
      result.logits = digest;
      result.kv = row_hash;
    }
    return result.token == next && result.logits == digest && result.kv == row_hash &&
        sample.softmax_jobs == (overlap_only || mode ? cfg.layers * cfg.kv_heads : 0U);
  };
  auto measure_short = [&](unsigned mode, unsigned round) {
    if (!select_mode(mode != 0)) return false;
    model.reset();
    for (unsigned i = 0; i < 4; ++i) {
      std::uint16_t next = 0;
      Sample prefill;
      AttentionSample prefill_attention;
      auto &sample = i < 2 ? prefill : report.short_samples[mode][round];
      auto &attention = i < 2 ? prefill_attention : report_data.attention[0][mode][round];
      if (!step(tokens[i], i != 0, next, sample, attention)) return false;
      const auto digest = model.compute_metrics().checksum;
      if (next != word(reference, 20 + i * 8) || digest != word(reference, 24 + i * 8)) return false;
      report.short_tokens[i] = next;
      report.short_checksums[i] = digest;
      ++report.verified_steps;
    }
    return report.short_samples[mode][round].softmax_jobs == 0;
  };
  auto measure_prefill=[&](unsigned mode,unsigned round) {
    auto &result=trial.prefill[mode][round];
    auto e=production;
    e.overlap_kv=e.parallel_softmax=true;
    e.attention_kernel=AttentionKernel(trial.kernel);
    model.execution(e);
    if(!model.diagnostic_position(trial.prefill_start)) return false;
    const auto required=model.prefill_pair_workspace_bytes(Arithmetic::INT8);
    trial.extra_bytes=required;
    std::unique_ptr<float[]> extra(mode && required?new (std::nothrow) float[required/sizeof(float)]:nullptr);
    if(!required || (mode && !extra)) {status=ModelStatus::MEMORY;return false;}
    for(unsigned i=0;i<trial.prefill_count;) {
      const auto started=call(MK61_SERVICE_MICROS);
      u32 digest[2]{};
      const unsigned used=mode?2:1;
      const unsigned position=trial.prefill_start+i;
      const std::uint16_t a=input(ids,count,position);
      if(mode) {
        const std::uint16_t pair[]{a,input(ids,count,position+1)};
        status=model.prefill_pair(pair,extra.get(),required,Arithmetic::INT8,service,this,digest);
      } else {
        std::uint16_t unused=0;
        status=model.forward(a,false,unused,service,this,Arithmetic::INT8);
        digest[0]=model.compute_metrics().checksum;
      }
      result.us+=call(MK61_SERVICE_MICROS)-started;
      if(status!=ModelStatus::OK || model.position()!=position+used) return false;
      const auto &m=model.compute_metrics();
      result.kv_bytes+=m.attention_read_bytes;
      result.kv_reads+=m.attention_read_transactions;
      result.weight_prefetch_bytes+=m.prefetched_bytes;
      result.weight_io_us+=m.read_us+m.wait_us;
      result.softmax_jobs+=m.softmax_worker_jobs;
      for(unsigned j=0;j<used;++j) {
        u32 row=0;
        if(!kv_hash(position+j,row))return false;
        if(!mode && !round) {
          trial.prompt_digest[i+j]=digest[j];
          trial.prompt_kv[i+j]=row;
        } else if(trial.prompt_digest[i+j]!=digest[j] || trial.prompt_kv[i+j]!=row) return false;
      }
      i+=used;
    }
    return result.softmax_jobs==trial.prefill_count*cfg.layers*cfg.kv_heads;
  };

  // Longest first so every shorter pair still sees the original KV prefix.
  if(ok && attention_trial)ok=micro();
  const unsigned variants=attention_trial?trial.variants:2;
  const unsigned full_rounds=attention_trial?2:rounds;
  for (unsigned remaining = 3; ok && remaining; --remaining) {
    auto &result = report.long_cases[remaining - 1];
    report.stage = result.context;
    std::snprintf(s.feedback, sizeof(s.feedback), "Context %u; Esc: stop", unsigned(result.context));
    dirty = true;
    for (unsigned round = 0; ok && round < full_rounds; ++round)
      for(unsigned side=0;ok && side<variants;++side)
        ok = measure_long(remaining - 1, variants==2?side^(round&1U):0U, round);
    if(attention_trial)break;
  }
  if (ok) report.stage = 1;
  for (unsigned round = 0; ok && round < full_rounds; ++round)
    for(unsigned side=0;ok && side<variants;++side)
      ok = measure_short(variants==2?side^(round&1U):0U,round);
  if(ok && attention_trial) {
    trial.stage=3;
    if(ok)ok=measure_prefill(0,0) && measure_prefill(1,0) &&
             measure_prefill(1,1) && measure_prefill(0,1);
    if(ok)trial.stage=4;
  }
  if (ok) report.stage = 2;

  report.divider256 = psram::diagnostic_clock_divider256();
  const auto ram_after = psram::statistics();
  const auto io_after = io_worker::statistics();
  const bool restored = ai_clock::restore(clock);
  report.restored_hz = ai_clock::hz();
  report.status = unsigned(status);
  sample_memory();
  report.heap_peak = heap_peak;
  report.heap_capacity = heap_capacity;
  report.ok = ok && restored && !cancel && report.hz == 270000000 && report.divider256 == 346 &&
      freeze_count == thaw_count && !freeze_violations && ram_before.errors == ram_after.errors &&
      ram_before.burst_retries == ram_after.burst_retries && io_before.i2c_timeouts == io_after.i2c_timeouts &&
      io_before.i2c_aborts == io_after.i2c_aborts;
  workspace.reset();
  const bool saved = files::write_range(result_path, 0, reinterpret_cast<const u8 *>(&report_data), report.bytes);
  return report.ok && saved ? 0 : 3;
}
