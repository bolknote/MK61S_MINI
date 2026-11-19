AI_COLD_CODE unsigned UI::request_perf(const char *directory, bool fast_request) {
  if (!host.diagnostic_directory) return 3;
  char path[160], text[1025];
  auto read_text = [&](const char *leaf) {
    const int size = std::snprintf(path, sizeof(path), "%s/%s", directory, leaf);
    unsigned n = 0;
    if (size < 0 || unsigned(size) >= sizeof(path) ||
        !store_read(nullptr, path, text, sizeof(text) - 1, n) || std::memchr(text, 0, n))
      return false;
    text[n] = 0;
    return true;
  };
  s.id = 1;
  s.attempt_limit = 1;
  Example example;
  if (!read_text("TASK.TXT") || !set_task(s, text, false) ||
      !read_text("CHECK.TXT") || !parse_example(text, example) || !set_example(s, 0, example))
    return 3;
  agent.default_angle(example.angle);
  cancel = false;
  std::snprintf(path, sizeof(path), "%s/PREFIX.ON", directory);
  cache_prefix = files::exists(path);

  // The divider at clock entry belongs to the idle PIO program. Exercise
  // the aligned burst reader before checking the divider for inference.
  ai_clock::State clock{};
  const bool entered = ai_clock::begin(270, clock);
  const unsigned hz = ai_clock::hz();
  const auto ram_before = psram::statistics();
  const auto io_before = io_worker::statistics();
  const bool clock_ok = entered && hz == 270000000 && ram_before.ready && ram_before.qpi;
  const auto started = call(MK61_SERVICE_MICROS);
  alignas(4) u8 header[64];
  const bool loaded = clock_ok && ensure_model();
  const unsigned divider = loaded && package.read(0, header, sizeof(header)) ?
      psram::diagnostic_clock_divider256() : 0;
  const unsigned read_hz = divider ? psram::statistics().hz : 0;
  bool began = false;
  if (divider == 346 && read_hz == 33294797) {
    configure_execution(fast_request);
    agent.arithmetic(arithmetic);
    began = agent.start(prefix[0] ? prefix : nullptr);
  }
  unsigned progress = 32;
  for (unsigned tick = 0; agent.active() && tick < 2200; ++tick) {
    agent.tick(service, this);
    const auto &metrics = agent.metrics();
    if (metrics.prefill_tokens + metrics.decode_tokens >= progress) {
      progress += 32;
      char line[112];
      const int n = std::snprintf(line, sizeof(line), "AI_PERF request input=%lu decode=%lu hz=%u psram_hz=%lu\r\n",
          (unsigned long)metrics.prefill_tokens, (unsigned long)metrics.decode_tokens,
          hz, (unsigned long)read_hz);
      if (n > 0 && unsigned(n) < sizeof(line)) debug_write(line, unsigned(n));
    }
  }
  const auto elapsed = call(MK61_SERVICE_MICROS) - started;
  const unsigned end_hz = ai_clock::hz();
  const unsigned end_divider = divider && package.read(0, header, sizeof(header)) ?
      psram::diagnostic_clock_divider256() : 0;
  const auto ram_after = psram::statistics();
  const auto io_after = io_worker::statistics();
  const auto psram_faults = ram_after.errors - ram_before.errors;
  const auto burst_retries = ram_after.burst_retries - ram_before.burst_retries;
  const auto tail_timeouts = ram_after.tail_timeouts - ram_before.tail_timeouts;
  const auto i2c_timeouts = io_after.i2c_timeouts - io_before.i2c_timeouts;
  const auto i2c_aborts = io_after.i2c_aborts - io_before.i2c_aborts;
  const bool restored = ai_clock::restore(clock);
  const unsigned idle_hz = ai_clock::hz();
  const bool passed = began && !agent.active() && s.state == RunState::FINISHED && all_passed(s);
  const bool stable = clock_ok && divider == 346 && restored && idle_hz == 125000000 &&
      end_hz == hz && end_divider == divider && ram_after.ready && ram_after.qpi &&
      !psram_faults && !burst_retries && !tail_timeouts && !i2c_timeouts && !i2c_aborts &&
      freeze_count == thaw_count && !freeze_violations;
  sample_memory();
  std::snprintf(path, sizeof(path), "%s/METRICS.JSON", directory);
  if (!write_metrics(path)) return 3;
  const int size = std::snprintf(text, sizeof(text),
      "{\"version\":2,\"began\":%s,\"passed\":%s,\"stable\":%s,\"state\":%u,\"elapsed_us\":%lu,"
      "\"attention_kernel\":%u,\"pair_prefill\":%s,"
      "\"hz\":%u,\"end_hz\":%u,\"psram_hz\":%lu,\"divider256\":%u,\"end_divider256\":%u,\"idle_hz\":%u,"
      "\"psram_errors\":%lu,\"burst_retries\":%lu,\"tail_timeouts\":%lu,\"i2c_timeouts\":%lu,\"i2c_aborts\":%lu,"
      "\"commands\":%u,\"program_crc\":%lu,\"x\":%.12g,\"model\":\"%s\",\"weights_psram\":%lu,\"kv_psram\":%lu}\n",
      began ? "true" : "false", passed ? "true" : "false", stable ? "true" : "false", unsigned(s.state),
      (unsigned long)elapsed, unsigned(model.execution().attention_kernel),
      model.execution().pair_prefill?"true":"false", hz, end_hz,
      (unsigned long)read_hz, divider, end_divider, idle_hz,
      (unsigned long)psram_faults, (unsigned long)burst_retries, (unsigned long)tail_timeouts,
      (unsigned long)i2c_timeouts, (unsigned long)i2c_aborts,
      unsigned(s.program.size), (unsigned long)program_fingerprint(s.program), agent.last_result().x, model_tag,
      (unsigned long)package.size(), (unsigned long)cache.size());
  std::snprintf(path, sizeof(path), "%s/REQUEST.JSON", directory);
  if (size < 0 || unsigned(size) >= sizeof(text) ||
      !files::write(path, reinterpret_cast<const u8 *>(text), unsigned(size))) return 3;
  return passed && stable ? 0 : 3;
}
