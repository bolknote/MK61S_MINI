AI_COLD_CODE unsigned UI::parameter_perf(const char *directory) {
  using namespace mk61ai::long_bench;
  constexpr unsigned rounds = 4;
  constexpr unsigned lengths[] = {128, 256, 512};
  constexpr unsigned seed_rows = 16, row_bytes = 512;
  if (!ensure_model() || !parameter_cache) return 3;
  const auto &cfg = model.config();
  if (cfg.layers != 10 || cfg.hidden != 128 || cfg.head_dim != 32 ||
      cfg.vocab != 8192 || cfg.kv_heads * cfg.head_dim * 8 != row_bytes || cfg.context < 512)
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
  } report;
  static_assert(sizeof(Result) == 1664);
  for (unsigned i = 0; i < 3; ++i) report.long_cases[i].context = lengths[i];

  char result_path[128];
  const int path_length = std::snprintf(result_path, sizeof(result_path), "%s/READ.BIN", directory);
  if (path_length < 0 || unsigned(path_length) >= sizeof(result_path) ||
      !files::write(result_path, reinterpret_cast<const u8 *>(&report), sizeof(report))) return 3;

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

  auto select_mode = [&](bool enabled) {
    auto execution = production;
    execution.parallel_softmax = enabled;
    model.execution(execution);
    if (!enabled) {
      model.clear_parameter_cache();
      return true;
    }
    status = model.cache_parameters(parameter_cache.get(), cache_bytes);
    return status == ModelStatus::OK;
  };
  auto step = [&](std::uint16_t id, bool output, std::uint16_t &next, Sample &sample) {
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
  auto measure_long = [&](LongCase &result, unsigned mode, unsigned round) {
    auto &sample = result.samples[mode][round];
    const unsigned position = result.context - 1;
    std::uint16_t next = 0;
    u32 row_hash = 0;
    if (!select_mode(mode != 0) || !model.diagnostic_position(position) ||
        !step(input(ids, count, position), true, next, sample) || !kv_hash(position, row_hash)) return false;
    const auto digest = model.compute_metrics().checksum;
    if (!mode && !round) {
      result.token = next;
      result.logits = digest;
      result.kv = row_hash;
    }
    return result.token == next && result.logits == digest && result.kv == row_hash &&
        sample.softmax_jobs == (mode ? cfg.layers * cfg.kv_heads : 0U);
  };
  auto measure_short = [&](unsigned mode, unsigned round) {
    if (!select_mode(mode != 0)) return false;
    model.reset();
    for (unsigned i = 0; i < 4; ++i) {
      std::uint16_t next = 0;
      Sample prefill;
      auto &sample = i < 2 ? prefill : report.short_samples[mode][round];
      if (!step(tokens[i], i != 0, next, sample)) return false;
      const auto digest = model.compute_metrics().checksum;
      if (next != word(reference, 20 + i * 8) || digest != word(reference, 24 + i * 8)) return false;
      report.short_tokens[i] = next;
      report.short_checksums[i] = digest;
      ++report.verified_steps;
    }
    return report.short_samples[mode][round].softmax_jobs == 0;
  };

  // Longest first so every shorter pair still sees the original KV prefix.
  for (unsigned remaining = 3; ok && remaining; --remaining) {
    auto &result = report.long_cases[remaining - 1];
    report.stage = result.context;
    std::snprintf(s.feedback, sizeof(s.feedback), "Context %u; Esc: stop", unsigned(result.context));
    dirty = true;
    for (unsigned round = 0; ok && round < rounds; ++round) {
      const unsigned first = round & 1U;
      ok = measure_long(result, first, round) && measure_long(result, first ^ 1U, round);
    }
  }
  if (ok) report.stage = 1;
  for (unsigned round = 0; ok && round < rounds; ++round) {
    const unsigned first = round & 1U;
    ok = measure_short(first, round) && measure_short(first ^ 1U, round);
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
  const bool saved = files::write_range(result_path, 0, reinterpret_cast<const u8 *>(&report), sizeof(report));
  return report.ok && saved ? 0 : 3;
}
